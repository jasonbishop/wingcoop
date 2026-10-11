"""Positive and negative controls for the tree-search agent.

Before a "no effect" result from an agent is trusted, the agent must show that
it can detect an effect that should be there (positive control) and does not
invent one that should not be (negative control).

Positive control: fully team-minded (w = 1) tree-search bots in 5-player
co-op games pick shared-benefit birds more often, when available, than
selfish (w = 0) bots do.

Negative control: selfish bots in the baseline show no special preference for
shared-benefit birds over other birds of similar points and cost.

Method (probes). Greedy bots play games in each condition. At "play a bird"
decisions where at least one shared-benefit bird and at least one other bird
are both playable, the position is handed to a tree-search agent once per
motivation level, with the same random seed, and its choice is recorded. Every
position is therefore answered by both a selfish and a team-minded searcher,
which makes the comparison paired. Full games played by tree-search bots can be
run through the experiment runner (see experiments/controls-mcts.yaml).

Usage: python -m wingsim.analysis.controls --positions 300 --iterations 1000 --workers 8
"""
import argparse
import json
import pathlib
import random
import time
from multiprocessing import Pool

from ..agents import group_policies
from ..agents.base import Objective
from ..agents.greedy import GreedyAgent
from ..agents.mcts import MCTSAgent
from ..engine import api
from ..game import play_game
from .metrics import vp_bucket
from .tags import all_tags

CONDITIONS = {
    "coop": {"coop_goals": {"penalty": "avg_x_d", "allowed_changes": [0, 1]}},
    "baseline": {},
}


class ProbePicker:
    """Tally hook: keeps a random sample of qualifying decisions from one game."""

    def __init__(self, db, rng, per_game):
        self.db, self.rng, self.per_game = db, rng, per_game
        self.tags = all_tags()
        self.seen = 0
        self.kept = []

    def record(self, s, d, choice):
        if d.kind != "action":
            return
        cards = {o[1] for o in d.options if o[0] == "play"}
        shared = sum("shares_benefit" in self.tags[c] for c in cards)
        if shared == 0 or shared == len(cards):
            return
        self.seen += 1
        item = (s.copy(), d, choice)
        if len(self.kept) < self.per_game:      # reservoir sampling
            self.kept.append(item)
        else:
            k = self.rng.randrange(self.seen)
            if k < self.per_game:
                self.kept[k] = item


def probe_game(task):
    """Play one greedy game, then ask the tree-search agent about the sampled positions."""
    condition, players, seed, per_game, arms, mcts = task
    cfg = api.GameConfig(players, CONDITIONS[condition])
    agents = [GreedyAgent(None, seed) for _ in range(players)]
    for i, a in enumerate(agents):
        a.start(cfg, i, Objective(0.5, players))
    policy = None
    if cfg.plugins:
        policy = group_policies.parse("fixed(2)")
        policy.start(cfg)
    picker = ProbePicker(cfg.db, random.Random(seed * 977 + 1), per_game)
    play_game(cfg, seed, agents, policy, tally=picker)
    tags = all_tags()
    rows = []
    for k, (s, d, greedy_choice) in enumerate(picker.kept):
        p = d.player
        obs = api.observe(s, p)
        cards = sorted({o[1] for o in d.options if o[0] == "play"})
        for w in arms:
            agent = MCTSAgent(seed=seed * 31 + k, **mcts)     # the same seed for every arm: paired
            agent.start(cfg, p, Objective(w, players))
            choice = agent.choose(obs, d)
            played = choice[1] if choice[0] == "play" else None
            rows.append({
                "condition": condition, "players": players, "seed": seed, "probe": k, "round": s.round,
                "turn_no": s.turn_no, "player": p, "w": w, "choice": choice[0],
                "chose_shared": bool(played is not None and "shares_benefit" in tags[played]),
                "chose_other_bird": bool(played is not None and "shares_benefit" not in tags[played]),
                "offers": [[c, "shares_benefit" in tags[c], cfg.db.birds[c].total_cost,
                            vp_bucket(cfg.db.birds[c].vp), cfg.db.birds[c].timing or "none", c == played]
                           for c in cards],
            })
    return rows


def run_probes(positions=300, iterations=1000, minor=None, players=5, per_game=2, workers=8, c=0.7,
               start_seed=5000, arms=(0.0, 1.0), progress=True):
    mcts = {"iterations": iterations, "minor_iterations": minor, "c": c}
    rows = []
    t0 = time.time()
    with Pool(workers) as pool:
        for condition in CONDITIONS:
            got = 0
            seed = start_seed
            batch = max(workers, positions // per_game // 2)
            while got < positions:
                tasks = [(condition, players, seed + i, per_game, arms, mcts) for i in range(batch)]
                seed += batch
                for out in pool.imap_unordered(probe_game, tasks):
                    if got < positions:
                        keep = [r for r in out if got + r["probe"] < positions]
                        rows.extend(keep)
                        got += len({r["probe"] for r in keep})
                if progress:
                    print(f"  {condition}: {got}/{positions} positions, {time.time() - t0:.0f}s", flush=True)
                batch = max(workers, (positions - got) // per_game + 1)
    return rows


# ---------------------------------------------------------------- statistics

def _mean_ci(xs):
    n = len(xs)
    m = sum(xs) / n
    if n < 2:
        return m, float("nan")
    var = sum((x - m) ** 2 for x in xs) / (n - 1)
    return m, 1.96 * (var / n) ** 0.5


def pick_rates(rows, strata):
    """Shared-benefit pick rate, and the other birds' pick rate re-weighted to the shared birds' strata."""
    shared = [0, 0]
    other = {}
    weight = {}
    for r in rows:
        for cid, is_shared, cost, vp, timing, chosen in r["offers"]:
            key = tuple({"cost": cost, "vp": vp, "timing": timing}[k] for k in strata)
            if is_shared:
                shared[0] += 1
                shared[1] += chosen
                weight[key] = weight.get(key, 0) + 1
            else:
                cell = other.setdefault(key, [0, 0])
                cell[0] += 1
                cell[1] += chosen
    num = den = 0.0
    for key, wgt in weight.items():
        if key in other and other[key][0]:
            num += wgt * other[key][1] / other[key][0]
            den += wgt
    return (shared[1] / shared[0] if shared[0] else float("nan"), num / den if den else float("nan"),
            shared[0], den / shared[0] if shared[0] else 0.0)


def bootstrap_gap(rows, strata, reps=1000, seed=1):
    """95% interval for (shared pick rate - matched other pick rate), resampling positions."""
    rng = random.Random(seed)
    n = len(rows)
    gaps = []
    for _ in range(reps):
        sample = [rows[rng.randrange(n)] for _ in range(n)]
        s, o, _, _ = pick_rates(sample, strata)
        if s == s and o == o:
            gaps.append(s - o)
    if not gaps:      # no stratum holds both kinds of bird, so there is nothing to compare
        return float("nan"), float("nan")
    gaps.sort()
    return gaps[int(0.025 * len(gaps))], gaps[int(0.975 * len(gaps)) - 1]


def analyse(rows):
    out = {}
    for condition in CONDITIONS:
        part = [r for r in rows if r["condition"] == condition]
        by_w = {}
        for r in part:
            by_w.setdefault(r["w"], {})[(r["seed"], r["probe"])] = r
        res = {"positions": len(next(iter(by_w.values()))) if by_w else 0, "arms": {}}
        for w, d in sorted(by_w.items()):
            rs = list(d.values())
            arm = {"chose_shared": sum(r["chose_shared"] for r in rs) / len(rs),
                   "chose_other_bird": sum(r["chose_other_bird"] for r in rs) / len(rs),
                   "did_not_play": sum(r["choice"] != "play" for r in rs) / len(rs)}
            for name, strata in (("cost_points", ("cost", "vp")), ("cost_points_colour", ("cost", "vp", "timing"))):
                s, o, offers, covered = pick_rates(rs, strata)
                lo, hi = bootstrap_gap(rs, strata)
                arm[name] = {"shared": s, "matched_other": o, "gap": s - o, "gap_lo": lo, "gap_hi": hi,
                             "shared_offers": offers, "matched_share": covered}
            res["arms"][w] = arm
        if 0.0 in by_w and 1.0 in by_w:
            keys = sorted(set(by_w[0.0]) & set(by_w[1.0]))
            diffs = [by_w[1.0][k]["chose_shared"] - by_w[0.0][k]["chose_shared"] for k in keys]
            m, half = _mean_ci(diffs)
            res["paired"] = {"n": len(keys), "diff": m, "half": half,
                             "switched_to_shared": sum(d > 0 for d in diffs),
                             "switched_away": sum(d < 0 for d in diffs)}
        out[condition] = res
    pos = out["coop"].get("paired")
    neg = out["baseline"]["arms"].get(0.0)
    out["positive_pass"] = bool(pos and pos["diff"] - pos["half"] > 0)
    # The negative control fails only on a preference FOR shared-benefit birds: the whole interval above zero.
    out["negative_pass"] = bool(neg and neg["cost_points"]["gap_lo"] <= 0)
    out["negative_pass_colour"] = bool(neg and neg["cost_points_colour"]["gap_lo"] <= 0)
    out["negative_avoids"] = bool(neg and neg["cost_points"]["gap_hi"] < 0)
    return out


def write_report(result, settings, path):
    L = ["# Tree-search agent: positive and negative controls", "",
         f"Settings: {json.dumps(settings)}", "",
         "Positions come from games played by greedy bots (w = 0.5). Each position is a \"play a bird\" decision "
         "where a shared-benefit bird and at least one other bird were both playable. The tree-search agent "
         "answered every position once per motivation level with the same random seed.", ""]
    pos = result["coop"].get("paired")
    L += ["## Positive control", "",
          "Team-minded (w = 1) searchers should play a shared-benefit bird more often than selfish (w = 0) "
          "searchers in the same 5-player co-op positions.", ""]
    if pos:
        a0, a1 = result["coop"]["arms"][0.0], result["coop"]["arms"][1.0]
        L += ["| | w = 0 | w = 1 |", "| --- | --- | --- |",
              f"| Played a shared-benefit bird | {a0['chose_shared']:.1%} | {a1['chose_shared']:.1%} |",
              f"| Played another bird | {a0['chose_other_bird']:.1%} | {a1['chose_other_bird']:.1%} |",
              f"| Did not play a bird | {a0['did_not_play']:.1%} | {a1['did_not_play']:.1%} |", "",
              f"Paired difference over {pos['n']} positions: {pos['diff']:+.1%} ± {pos['half']:.1%} (95%). "
              f"{pos['switched_to_shared']} positions switched to a shared-benefit bird at w = 1 and "
              f"{pos['switched_away']} switched away.", "",
              f"**Result: {'PASS' if result['positive_pass'] else 'NOT SHOWN'}** "
              "(pass = the 95% interval is entirely above zero).", ""]
    L += ["## Negative control", "",
          "Selfish (w = 0) searchers in the baseline should pick shared-benefit birds about as often as other "
          "birds of similar points and cost. The second row also matches on power colour, because nearly "
          "every shared-benefit bird has a repeating (brown) power that also pays its owner.", "",
          "| Matched on | Shared-benefit pick rate | Matched other birds | Gap | 95% interval | Result |",
          "| --- | --- | --- | --- | --- | --- |"]
    neg = result["baseline"]["arms"].get(0.0)
    if neg:
        for name, label, key in (("cost_points", "cost and points (the spec's test)", "negative_pass"),
                                 ("cost_points_colour", "cost, points and power colour", "negative_pass_colour")):
            x = neg[name]
            L.append(f"| {label} | {x['shared']:.1%} | {x['matched_other']:.1%} | {x['gap']:+.1%} | "
                     f"{x['gap_lo']:+.1%} to {x['gap_hi']:+.1%} | {'PASS' if result[key] else 'FAIL'} |")
        L += ["", "Pass = no preference for shared-benefit birds: the interval is not entirely above zero.", ""]
        if result.get("negative_avoids"):
            L += ["Selfish searchers picked shared-benefit birds less often than matched other birds (the "
                  "interval is entirely below zero). That is not a preference for them, so the control passes, "
                  "but it is a bias worth knowing about when reading pick rates.", ""]
    L += ["## All arms", "",
          "| Condition | w | Positions | Shared pick rate | Other, matched on cost and points | Gap | "
          "Other, also matched on colour | Gap |", "| --- | --- | --- | --- | --- | --- | --- | --- |"]
    for condition in CONDITIONS:
        for w, arm in sorted(result[condition]["arms"].items()):
            a, b = arm["cost_points"], arm["cost_points_colour"]
            L.append(f"| {condition} | {w:g} | {result[condition]['positions']} | {a['shared']:.1%} | "
                     f"{a['matched_other']:.1%} | {a['gap']:+.1%} | {b['matched_other']:.1%} | {b['gap']:+.1%} |")
    for condition in CONDITIONS:
        p = result[condition].get("paired")
        if p:
            L += ["", f"{condition}: paired change in playing a shared-benefit bird, w = 1 minus w = 0: "
                  f"{p['diff']:+.1%} ± {p['half']:.1%} over {p['n']} positions."]
    L.append("")
    pathlib.Path(path).write_text("\n".join(L))
    return path


def main(argv=None):
    ap = argparse.ArgumentParser(description="Positive and negative controls for the tree-search agent")
    ap.add_argument("--positions", type=int, default=300)
    ap.add_argument("--iterations", type=int, default=1000)
    ap.add_argument("--players", type=int, default=5)
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--c", type=float, default=0.7)
    ap.add_argument("--out", default="results/controls")
    ap.add_argument("--reanalyse", action="store_true", help="rebuild the report from an existing probes.json")
    args = ap.parse_args(argv)
    settings = {"positions": args.positions, "iterations": args.iterations, "players": args.players,
                "c": args.c, "rollout": "random", "arms": [0.0, 1.0]}
    out = pathlib.Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    if args.reanalyse:
        rows = json.loads((out / "probes.json").read_text())
        settings = json.loads((out / "settings.json").read_text())
    else:
        rows = run_probes(args.positions, args.iterations, None, args.players, workers=args.workers, c=args.c)
        (out / "probes.json").write_text(json.dumps(rows))
        (out / "settings.json").write_text(json.dumps(settings))
    result = analyse(rows)
    (out / "controls.json").write_text(json.dumps(result, indent=1))
    print("positive control:", "PASS" if result["positive_pass"] else "NOT SHOWN",
          "| negative control:", "PASS" if result["negative_pass"] else "FAIL",
          "| with colour matching:", "PASS" if result["negative_pass_colour"] else "FAIL")
    print("report:", write_report(result, settings, out / "controls.md"))


if __name__ == "__main__":
    main()
