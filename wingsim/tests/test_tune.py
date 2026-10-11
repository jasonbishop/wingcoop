"""Per-condition weight tuning."""
import random

from wingsim import runner, tune
from wingsim.agents.greedy import DEFAULT_WEIGHTS, GreedyAgent
from wingsim.engine import api

from .test_runner import EXP


def test_cells_and_seed_assignment_are_fixed():
    exp = dict(EXP, agents={"type": "greedy"}, group_policy=["fixed(2)", "estimate"])
    coop = tune.cells_for(exp, "coop")
    assert coop and all(c["policy"] == "fixed(2)" for c in coop)          # estimate is left out
    assert {c["w"] for c in coop} == {0.0, 1.0} and {c["group_share"] for c in coop} == {False, True}
    assert tune.assign_cell(coop, 5) is tune.assign_cell(coop, 5)
    assert len({id(tune.assign_cell(coop, s)) for s in range(60)}) == len(coop)   # every cell gets seeds


def test_perturb_changes_a_few_weights_within_limits():
    rng = random.Random(3)
    w = dict(DEFAULT_WEIGHTS)
    for _ in range(300):
        cand = tune.perturb(w, rng)
        assert set(cand) == set(w)
        assert 1 <= sum(cand[k] != w[k] for k in w) <= 3 or cand == w
        for k, (lo, hi) in tune.LIMITS.items():
            assert lo <= cand[k] <= hi
        GreedyAgent(cand)                                # still a valid set of weights
        w = cand


def test_mean_utility_matches_the_objective():
    exp = dict(EXP, agents={"type": "greedy"})
    cell = next(c for c in tune.cells_for(exp, "coop") if c["w"] == 1.0 and c["players"] == 2)
    s, _, _ = runner.play_cell_game(dict(cell, weights=None), 3)
    fs = api.final_scores(s)
    assert tune.mean_utility(cell, s) == fs["team_total"] / 2      # w = 1: everyone gets team total / n
    selfish = dict(cell, w=0.0, group_share=False)
    assert tune.mean_utility(selfish, s) == sum(p["total"] for p in fs["players"]) / 2


def test_evaluate_is_reproducible_and_hill_climb_only_keeps_confirmed_gains():
    exp = dict(EXP, agents={"type": "greedy"}, players=[2])
    cells = tune.cells_for(exp, "baseline")
    a = tune.evaluate(None, cells, dict(DEFAULT_WEIGHTS), [1, 2])
    assert a == tune.evaluate(None, cells, dict(DEFAULT_WEIGHTS), [1, 2]) and len(a) == 2
    best, history, counts = tune.hill_climb(None, cells, DEFAULT_WEIGHTS, [1, 2], [3, 4], 4, random.Random(1),
                                            log=lambda m: None)
    assert counts["accepted"] == len(history) - 1 <= counts["confirmation_runs"] <= counts["candidates"]
    for before, after in zip(history, history[1:]):
        assert after["tune"] > before["tune"] and after["confirm"] > before["confirm"]
    assert best == history[-1]["weights"]
