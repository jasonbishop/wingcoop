"""Experiment runner: one YAML file defines a grid of conditions, every cell is
played on the same list of seeds, and the results go to Parquet tables.

Usage: python -m wingsim.runner wingsim/experiments/coop-goals-small.yaml [--workers 4] [--seeds N]
"""
import argparse
import hashlib
import json
import pathlib
import time
from multiprocessing import Pool

from .agents import group_policies
from .agents.base import Objective
from .agents.greedy import GreedyAgent
from .agents.mcts import MCTSAgent
from .agents.random import RandomAgent
from .agents.talk import TableTalk
from .analysis.metrics import DecisionTally
from .engine import api
from .engine.log import GameLog
from .game import play_game
from .plugins import open_hands as open_hands_setting

MAX_PLAYERS = 5


def as_list(x):
    return list(x) if isinstance(x, (list, tuple)) else [x]


def expand(exp, base_dir="."):
    """Turn an experiment definition into its grid cells.

    A condition with a group score (one that uses coop_goals) is crossed with
    every group policy and every `group_share` setting; other conditions run
    once per player count and motivation. A condition's own `motivation` list
    replaces the experiment's.
    """
    cells = []
    policies = as_list(exp.get("group_policy", "fixed(2)"))
    shares = as_list(exp.get("group_share", False))
    for cname, cond in exp["conditions"].items():
        cond = cond or {}
        plugins = dict(cond.get("plugins") or {})
        open_hands = open_hands_setting.resolve({"plugins": plugins, **{k: v for k, v in cond.items()
                                                                     if k == "open_hands"}})
        plugins.pop("open_hands", None)
        has_group = "coop_goals" in plugins
        agent = cond.get("agents") or exp.get("agents") or {"type": "greedy"}
        # A list gives one agent per seat (repeating if shorter than the table), e.g. [llm, greedy].
        agent = [dict(a) for a in agent] if isinstance(agent, list) else dict(agent)
        weights = None
        for spec in (agent if isinstance(agent, list) else [agent]):
            if spec.get("weights"):       # greedy value-function weights, shared by the greedy seats
                path = pathlib.Path(base_dir) / str(spec["weights"]).format(condition=cname)
                if path.exists():
                    weights = json.loads(path.read_text())
                    weights = weights.get("weights", weights)
                spec["weights_file"] = str(path) if path.exists() else None
        for n in as_list(exp["players"]):
            for w in as_list(cond.get("motivation", exp.get("motivation", 0.0))):   # a condition may set its own
                for policy in (policies if has_group else [None]):
                    for share in (shares if has_group else [False]):
                        cells.append({
                            "experiment": exp["name"], "condition": cname, "players": n, "w": w,
                            "policy": policy, "group_share": bool(share), "plugins": plugins,
                            "open_hands": open_hands, "win_condition": cond.get("win_condition", "individual"),
                            "team_target": cond.get("team_target"), "agent": agent, "weights": weights,
                            "snapshots": (exp.get("logging") or {}).get("snapshots", "turn"),
                        })
    return cells


def cell_tag(cell):
    tag = f"w{cell['w']}"
    if cell["policy"]:
        tag += "-" + str(cell["policy"]).replace("(", "_").replace(")", "").replace(",", "_").replace("+", "p")
    if cell["group_share"]:
        tag += "-share"
    return tag


class Table:
    """Builds the agents for one cell; group policies use it to get fresh copies for rollouts."""

    def __init__(self, cell, cfg):
        self.cell = cell
        self.cfg = cfg
        w = cell["w"]
        self.ws = list(w) if isinstance(w, (list, tuple)) else [w] * cfg.n
        if len(self.ws) != cfg.n:
            raise ValueError("a per-player motivation list must have one entry per player")

    def seat_specs(self):
        """One agent spec per seat. A list in the experiment file is dealt out in seat order (and repeats)."""
        spec = self.cell["agent"]
        specs = spec if isinstance(spec, list) else [spec]
        return [specs[i % len(specs)] for i in range(self.cfg.n)]

    def make_agents(self, seed):
        cfg = self.cfg
        agents = []
        for i, spec in enumerate(self.seat_specs()):
            kind = spec.get("type", "greedy")
            if kind == "greedy":
                a = GreedyAgent(self.cell["weights"], seed)
            elif kind == "mcts":
                opts = {k: spec[k] for k in ("iterations", "ms", "minor_iterations", "c", "rollout") if k in spec}
                a = MCTSAgent(seed=seed, greedy_weights=self.cell["weights"], **opts)
            elif kind == "llm":
                from .agents.llm import LLMAgent
                opts = {k: v for k, v in spec.items() if k not in ("type", "weights", "weights_file")}
                a = LLMAgent(seed=seed, **opts)
            elif kind == "random":
                a = RandomAgent(seed * 131 + i)
            else:
                raise ValueError(f"unknown agent type {kind!r}")
            a.start(cfg, i, Objective(self.ws[i], cfg.n, self.cell["group_share"]))
            agents.append(a)
        return agents


def play_cell_game(cell, seed, full_log=False):
    """Play one game of a cell. Returns (final state, tally, log or None)."""
    cfg = api.GameConfig(cell["players"], cell["plugins"], cell["open_hands"], cell["win_condition"],
                         cell["team_target"], record_events=full_log)
    table = Table(cell, cfg)
    agents = table.make_agents(seed)
    talkers = [a for a in agents if getattr(a, "talk", False)]
    if talkers:     # the seats that talk share one table
        talk = TableTalk([a.player for a in talkers])
        for a in talkers:
            a.table = talk
    policy = None
    if cell["policy"]:
        policy = group_policies.parse(cell["policy"])
        policy.start(cfg, table, seed)
    log = None
    if full_log:
        seats = [{"type": a.type, "settings": a.settings(), "w": a.objective.w,
                  "group_share": a.objective.group_share} for a in agents]
        log = GameLog(cfg, seed, seats, cell["policy"], cell["experiment"], cell["condition"],
                      snapshots=cell.get("snapshots", "turn"))
    tally = DecisionTally(cfg.db)
    tally.agents = agents
    s = play_game(cfg, seed, agents, policy, log=log, tally=tally)
    return s, tally, log


def agent_label(spec):
    specs = spec if isinstance(spec, list) else [spec]
    return "+".join(a.get("type", "greedy") + (":" + a["model"] if a.get("model") else "") for a in specs)


def game_row(cell, seed, s, tally, seconds, agents=()):
    n = cell["players"]
    fs = api.final_scores(s)
    row = {
        "experiment": cell["experiment"], "condition": cell["condition"], "players": n, "seed": seed,
        "agent": agent_label(cell["agent"]),
        "w": cell["w"] if not isinstance(cell["w"], (list, tuple)) else -1.0,
        "w_list": json.dumps(cell["w"]) if isinstance(cell["w"], (list, tuple)) else None,
        "policy": cell["policy"] or "none", "group_share": cell["group_share"],
        "open_hands": cell["open_hands"], "win_condition": cell["win_condition"],
        "group_score": fs["group"], "team_total": fs["team_total"],
        "first_player": (s.first - 4) % n,   # the token has passed four times by the end
        "winners": ";".join(map(str, fs["winners"])), "seconds": seconds,
    }
    totals = [p["total"] for p in fs["players"]]
    row["individual_mean"] = sum(totals) / n
    row["spread"] = max(totals) - min(totals)
    mean = row["individual_mean"]
    row["score_sd"] = (sum((t - mean) ** 2 for t in totals) / n) ** 0.5
    if cell["team_target"] is not None:
        row["team_win"] = fs["team_total"] >= cell["team_target"]
    for j in range(MAX_PLAYERS):
        for cat in ("birds", "bonus", "eggs", "cached", "tucked", "goals", "total"):
            row[f"p{j}_{cat}"] = float(fs["players"][j][cat]) if j < n else None
        row[f"p{j}_food_left"] = fs["leftover_food"][j] if j < n else None
    fails = 0
    for r in range(4):
        _, counts, ind, delta, info = s.goal_log[r]
        row[f"r{r + 1}_goal"] = s.goals[r]
        row[f"r{r + 1}_delta"] = delta
        d = info[1] if info else None
        ok = info[2] if info else None
        row[f"r{r + 1}_d"] = d
        row[f"r{r + 1}_success"] = ok
        row[f"r{r + 1}_missed"] = (";".join(str(j) for j in range(n) if min(counts[j], 5) < d)
                                   if d is not None else None)
        row[f"r{r + 1}_shortfall"] = (max(d - min(c, 5) for c in counts) if d is not None else None)
        for j in range(MAX_PLAYERS):
            row[f"r{r + 1}_c{j}"] = counts[j] if j < n else None
        fails += ok is False
    row["rounds_failed"] = fails if cell["policy"] else None
    for k, v in tally.counts.items():
        row[k] = v
    llm = [a.stats for a in agents if getattr(a, "type", "") == "llm"]
    if llm:
        for key in ("calls", "retries", "fallbacks", "prompt_tokens", "completion_tokens", "cost_usd"):
            row["llm_" + key] = sum(st[key] for st in llm)
    for j, a in enumerate(agents):
        row[f"p{j}_agent"] = a.type
    return row


def wants_full_log(cell, seed, logging):
    frac = float(logging.get("full_sample", 0) or 0)
    if logging.get("level") == "full":
        return True
    if frac <= 0:
        return False
    key = f"{cell['experiment']}|{cell['condition']}|{cell['players']}|{cell_tag(cell)}|{seed}".encode()
    return int(hashlib.sha1(key).hexdigest()[:8], 16) / 0xFFFFFFFF < frac


def flagged(row, conditions):
    for c in conditions or ():
        if c == "group_fail_round_4" and row.get("r4_success") is False:
            return c
        if c.startswith("spread_gt_") and row["spread"] > float(c.rsplit("_", 1)[1]):
            return c
    return None


def run_task(task):
    cell, seed, logging, log_root = task
    t0 = time.time()
    full = wants_full_log(cell, seed, logging)
    s, tally, log = play_cell_game(cell, seed, full)
    row = game_row(cell, seed, s, tally, time.time() - t0, tally.agents)
    reason = "sample" if full else flagged(row, logging.get("full_if"))
    paid = any(a.type == "llm" for a in tally.agents)
    if reason and log is None and paid:
        reason = None      # never replay a game that costs money just to log it; use `level: full` instead
    if reason and log is None:
        # Re-run the same game with full logging; it must come out identical.
        s2, _, log = play_cell_game(cell, seed, True)
        if api.final_scores(s2) != api.final_scores(s):
            raise RuntimeError(f"re-run of seed {seed} differs: the game is not deterministic")
    row["task_key"] = task_key(cell, seed)
    row["log"] = None
    row["log_reason"] = reason
    if log is not None:
        path = (pathlib.Path(log_root) / cell["experiment"] / cell["condition"] /
                f"{seed}-{cell['players']}p-{cell_tag(cell)}.jsonl.gz")
        log.write(path)
        row["log"] = str(path)
    offers = [{"condition": cell["condition"], "players": cell["players"], "w": row["w"],
               "policy": row["policy"], "group_share": cell["group_share"], "where": k[0],
               "shares_benefit": k[1], "cost": k[2], "vp": k[3], "offered": v[0], "chosen": v[1]}
              for k, v in tally.offers.items()]
    return row, offers


def task_key(cell, seed):
    return f"{cell['condition']}|{cell['players']}|{cell['w']}|{cell['policy']}|{cell['group_share']}|{seed}"


def run_experiment(exp, base_dir=".", workers=4, out_root="results", log_root="logs", seeds=None,
                   progress=True, resume=False):
    """Play every game of an experiment. Each finished game is also appended to `rows.jsonl` in the output
    folder as it finishes; with `resume`, games already there are not played again."""
    import pandas as pd

    cells = expand(exp, base_dir)
    start = exp["seeds"]["start"]
    count = seeds if seeds is not None else exp["seeds"]["count"]
    logging = exp.get("logging") or {"level": "summary"}
    tasks = []
    # Seed by seed, so that a run stopped part way has the same seeds in every cell.
    for i in range(count):
        for cell in cells:
            per_policy = (exp.get("seed_limits") or {}).get(str(cell["policy"]))
            if per_policy is None or i < per_policy:
                tasks.append((cell, start + i, logging, log_root))
    out = pathlib.Path(out_root) / exp["name"]
    out.mkdir(parents=True, exist_ok=True)
    partial = out / "rows.jsonl"
    rows, offers = [], []
    if resume and partial.exists():
        for line in partial.read_text().splitlines():
            done = json.loads(line)
            rows.append(done["row"])
            offers.extend(done["offers"])
        finished = {r["task_key"] for r in rows}
        tasks = [tk for tk in tasks if task_key(tk[0], tk[1]) not in finished]
        if progress:
            print(f"  resuming: {len(rows)} games already played, {len(tasks)} to go", flush=True)
    elif partial.exists():
        partial.unlink()
    # Longest games first so the pool stays busy; the result order does not matter.
    tasks.sort(key=lambda t: (str(t[0]["policy"]).startswith("estimate"), t[0]["players"]), reverse=True)
    t0 = time.time()
    if workers <= 1:
        results = map(run_task, tasks)
    else:
        pool = Pool(workers)
        results = pool.imap_unordered(run_task, tasks, chunksize=1)
    for i, (row, off) in enumerate(results, 1):
        rows.append(row)
        offers.extend(off)
        with open(partial, "a") as f:
            f.write(json.dumps({"row": row, "offers": off}, default=str) + "\n")
        if progress and len(tasks) <= 50:        # small (language-model) runs: report every game
            scores = " ".join(f"{row[f'p{j}_total']:g}" for j in range(row["players"]))
            extra = f", {row['llm_calls']} model calls" if "llm_calls" in row else ""
            print(f"  {i}/{len(tasks)} {row['condition']} seed {row['seed']}: scores {scores} "
                  f"({row['seconds']:.0f}s{extra}), {time.time() - t0:.0f}s so far", flush=True)
        elif progress and (i % 200 == 0 or i == len(tasks)):
            print(f"  {i}/{len(tasks)} games, {time.time() - t0:.0f}s", flush=True)
    if workers > 1:
        pool.close()
        pool.join()
    games = pd.DataFrame(rows).sort_values(["condition", "players", "w", "policy", "group_share", "seed"])
    games.to_parquet(out / "games.parquet", index=False)
    off = pd.DataFrame(offers)
    if len(off):
        keys = ["condition", "players", "w", "policy", "group_share", "where", "shares_benefit", "cost", "vp"]
        off = off.groupby(keys, as_index=False)[["offered", "chosen"]].sum()
    off.to_parquet(out / "offers.parquet", index=False)
    (out / "experiment.json").write_text(json.dumps(
        {"experiment": exp, "cells": len(cells), "games": len(rows), "seconds": round(time.time() - t0, 1),
         "engine_git": __import__("wingsim.engine.log", fromlist=["x"]).engine_git_hash()}, indent=1))
    return games, off, out


def load_experiment(path):
    import yaml
    return yaml.safe_load(pathlib.Path(path).read_text())


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("experiment")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--seeds", type=int, default=None, help="override the number of seeds")
    ap.add_argument("--out", default="results")
    ap.add_argument("--logs", default="logs")
    ap.add_argument("--no-report", action="store_true")
    ap.add_argument("--resume", action="store_true", help="keep the games already in rows.jsonl and play the rest")
    args = ap.parse_args(argv)
    path = pathlib.Path(args.experiment)
    exp = load_experiment(path)
    cells = expand(exp, path.parent)
    print(f"{exp['name']}: {len(cells)} cells")
    games, offers, out = run_experiment(exp, path.parent, args.workers, args.out, args.logs, args.seeds,
                                        resume=args.resume)
    print(f"wrote {len(games)} games to {out / 'games.parquet'}")
    if not args.no_report:
        from .analysis.report import write_report
        print("report:", write_report(out))


if __name__ == "__main__":
    main()
