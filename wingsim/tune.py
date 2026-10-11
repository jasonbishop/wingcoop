"""Tune the greedy bot's value-function weights by self-play, separately for each condition.

Usage: python -m wingsim.tune wingsim/experiments/coop-goals-small.yaml --minutes 18 --workers 8

For each condition in the experiment file, a hill-climb perturbs the weights and
keeps a change only if it helps twice: on a tuning set of seeds and then on a
separate confirmation set. The result is saved where the experiment file's
`agents.weights` template points (for example experiments/tuned/coop.json), so
the runner picks it up. A third, held-out set of seeds gives an honest score;
weights that do not beat the starting point there are not adopted.

What is maximized: the players' own objective, averaged over the seats. Every
seat uses the candidate weights. Each seed is assigned one cell of the
experiment's grid (player count, motivation, group policy, group_share), so the
weights are tuned across the whole grid rather than for one corner of it.
"""
import argparse
import json
import pathlib
import random
import time
from multiprocessing import Pool

from . import runner
from .agents.base import Objective
from .agents.greedy import DEFAULT_WEIGHTS
from .engine import api

FACTORS = (0.6, 0.75, 0.87, 1.15, 1.33, 1.6)
LIMITS = {"food_decay": (0.3, 0.97), "card_decay": (0.3, 0.97), "goal_rate": (0.02, 0.95), "horizon": (1.0, 26.0)}


def cells_for(exp, condition, base_dir="."):
    """The grid cells of one condition that tuning plays (the slow `estimate` policy is left out)."""
    cells = [c for c in runner.expand(exp, base_dir)
             if c["condition"] == condition and not str(c["policy"]).startswith("estimate")]
    if not cells:
        raise ValueError(f"no cells for condition {condition!r}")
    return cells


def assign_cell(cells, seed):
    """Each seed always gets the same cell, whatever the weights."""
    return cells[random.Random(seed * 7919 + 13).randrange(len(cells))]


def mean_utility(cell, s):
    n = cell["players"]
    totals = api.totals(s)
    group = s.group_score
    team = sum(totals) + group
    objective = Objective(cell["w"], n, cell["group_share"])
    return sum(objective.utility(x, team, group) for x in totals) / n


def play(task):
    cell, weights, seed = task
    cell = dict(cell, weights=weights, agent=dict(cell["agent"], type="greedy"))
    s, _, _ = runner.play_cell_game(cell, seed)
    return mean_utility(cell, s)


def evaluate(pool, cells, weights, seeds):
    """Per-seed scores for one set of weights."""
    tasks = [(assign_cell(cells, seed), weights, seed) for seed in seeds]
    return pool.map(play, tasks) if pool is not None else [play(t) for t in tasks]


def perturb(weights, rng):
    cand = dict(weights)
    for k in rng.sample(sorted(cand), rng.choice((1, 1, 2, 3))):
        v = cand[k] * rng.choice(FACTORS)
        lo, hi = LIMITS.get(k, (0.0, float("inf")))
        cand[k] = round(min(hi, max(lo, v)), 4)
    return cand


def mean(xs):
    return sum(xs) / len(xs)


def hill_climb(pool, cells, start, tune_seeds, confirm_seeds, seconds, rng, min_gain=0.25, log=print):
    best = dict(start)
    best_tune = evaluate(pool, cells, best, tune_seeds)
    best_confirm = evaluate(pool, cells, best, confirm_seeds)
    history = [{"step": 0, "tune": mean(best_tune), "confirm": mean(best_confirm), "weights": dict(best)}]
    log(f"  start: tune {mean(best_tune):.2f}, confirm {mean(best_confirm):.2f}")
    t0 = time.time()
    step = tried_confirm = 0
    while time.time() - t0 < seconds:
        step += 1
        cand = perturb(best, rng)
        if cand == best:
            continue
        tune = evaluate(pool, cells, cand, tune_seeds)
        if mean(tune) - mean(best_tune) <= min_gain:
            continue
        tried_confirm += 1
        confirm = evaluate(pool, cells, cand, confirm_seeds)       # a second opinion on fresh seeds
        if mean(confirm) <= mean(best_confirm):
            continue
        changed = {k: [best[k], cand[k]] for k in cand if cand[k] != best[k]}
        best, best_tune, best_confirm = cand, tune, confirm
        history.append({"step": step, "tune": mean(tune), "confirm": mean(confirm), "changed": changed,
                        "weights": dict(best)})
        log(f"  step {step}: tune {mean(tune):.2f}, confirm {mean(confirm):.2f}  {changed}")
    log(f"  {step} candidates tried, {tried_confirm} reached the confirmation set, "
        f"{len(history) - 1} accepted, {time.time() - t0:.0f}s")
    return best, history, {"candidates": step, "confirmation_runs": tried_confirm, "accepted": len(history) - 1}


def weights_path(exp, condition, base_dir):
    template = (exp.get("agents") or {}).get("weights") or "tuned/{condition}.json"
    return pathlib.Path(base_dir) / str(template).format(condition=condition)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Tune greedy weights per condition by self-play")
    ap.add_argument("experiment")
    ap.add_argument("--condition", action="append", help="tune only this condition (repeatable)")
    ap.add_argument("--minutes", type=float, default=18.0, help="search time per condition")
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--tune-seeds", type=int, default=40)
    ap.add_argument("--confirm-seeds", type=int, default=40)
    ap.add_argument("--holdout-seeds", type=int, default=160)
    ap.add_argument("--seed", type=int, default=1)
    args = ap.parse_args(argv)
    path = pathlib.Path(args.experiment)
    import yaml
    exp = yaml.safe_load(path.read_text())
    base = path.parent
    conditions = args.condition or list(exp["conditions"])
    # Seeds well away from the experiment's own, so tuned weights are not fitted to the games they are used in.
    tune_seeds = list(range(700_000, 700_000 + args.tune_seeds))
    confirm_seeds = list(range(710_000, 710_000 + args.confirm_seeds))
    holdout = list(range(720_000, 720_000 + args.holdout_seeds))
    # Load the starting weights before any tuned file exists or changes.
    plain = dict(exp, agents={"type": "greedy"})
    results = {}
    with Pool(args.workers) as pool:
        for condition in conditions:
            print(f"{condition}:", flush=True)
            cells = cells_for(plain, condition, base)
            rng = random.Random(args.seed * 101 + len(condition))
            best, history, counts = hill_climb(pool, cells, DEFAULT_WEIGHTS, tune_seeds, confirm_seeds,
                                               args.minutes * 60, rng,
                                               log=lambda m: print(m, flush=True))
            results[condition] = {"weights": best, "history": history, "counts": counts}
        # Held-out scores: every set of weights in every condition.
        sets = {"default": dict(DEFAULT_WEIGHTS)}
        sets.update({f"tuned for {c}": results[c]["weights"] for c in conditions})
        table = {}
        for condition in conditions:
            cells = cells_for(plain, condition, base)
            table[condition] = {}
            for name, w in sets.items():
                scores = evaluate(pool, cells, w, holdout)
                m = mean(scores)
                sd = (sum((x - m) ** 2 for x in scores) / (len(scores) - 1)) ** 0.5
                table[condition][name] = {"mean": m, "half": 1.96 * sd / len(scores) ** 0.5, "scores": scores}
                print(f"  held-out, {condition} games, {name} weights: {m:.2f} ± {table[condition][name]['half']:.2f}",
                      flush=True)
    for condition in conditions:
        out = weights_path(exp, condition, base)
        out.parent.mkdir(parents=True, exist_ok=True)
        own = table[condition][f"tuned for {condition}"]
        default = table[condition]["default"]
        diffs = [a - b for a, b in zip(own["scores"], default["scores"])]
        md = mean(diffs)
        sd = (sum((x - md) ** 2 for x in diffs) / (len(diffs) - 1)) ** 0.5
        # Weights that do not beat the starting point on held-out seeds are not adopted.
        kept = md > 0
        out.write_text(json.dumps({
            "condition": condition, "experiment": exp["name"],
            "weights": results[condition]["weights"] if kept else dict(DEFAULT_WEIGHTS),
            "adopted": kept,
            "note": None if kept else "The search found no held-out improvement, so the starting weights are kept.",
            "searched_weights": results[condition]["weights"],
            "start": dict(DEFAULT_WEIGHTS), "counts": results[condition]["counts"],
            "settings": {"minutes": args.minutes, "tune_seeds": args.tune_seeds,
                         "confirm_seeds": args.confirm_seeds, "holdout_seeds": args.holdout_seeds,
                         "objective": "mean over seats of each player's own objective"},
            "holdout": {name: {"mean": round(v["mean"], 3), "half": round(v["half"], 3)}
                        for name, v in table[condition].items()},
            "holdout_gain_over_default": {"mean": round(md, 3), "half": round(1.96 * sd / len(diffs) ** 0.5, 3)},
            "history": results[condition]["history"],
        }, indent=1) + "\n")
        print(f"wrote {out}: held-out gain over default {md:+.2f} ± {1.96 * sd / len(diffs) ** 0.5:.2f}"
              + ("" if kept else " (not adopted; starting weights kept)"))


if __name__ == "__main__":
    main()
