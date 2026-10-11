"""Tree-search agent and its controls."""
import random

import pytest

from wingsim.agents.base import Objective
from wingsim.agents.mcts import MCTSAgent
from wingsim.agents.random import RandomAgent
from wingsim.analysis import controls
from wingsim.engine import api, rules
from wingsim.engine.state import state_hash
from wingsim.game import play_game

from .helpers import feeder, fresh, pick, put, set_turn


def agent(cfg, player=0, w=0.0, **kw):
    a = MCTSAgent(**kw)
    a.start(cfg, player, Objective(w, cfg.n))
    return a


def decide(s, a):
    d = api.pending_decision(s)
    return a.choose(api.observe(s, d.player), d)


def last_turn_position():
    s = fresh(2)
    put(s, 0, pick(lambda b: b.egg_limit >= 4 and b.timing is None, 1)[0], "grassland")
    s.round, s.actions_left = 4, [1, 0]
    feeder(s, "fish", "seed", "fruit")
    set_turn(s, 0)
    return s


def test_finds_the_only_scoring_move_on_the_last_turn():
    s = last_turn_position()
    before = state_hash(s)
    a = agent(s.cfg, iterations=90)
    assert decide(s, a) == ("eggs",)          # food and cards score nothing; 2 eggs score 2
    assert state_hash(s) == before            # searching never touches the real game
    info = a.info()
    assert info["iterations"] == 90 and info["top"][0][0] == ("eggs",)
    assert info["top"][0][1] > info["top"][1][1]      # most visits went to the best move
    # Nothing after this move is random for player 0's score, so the values are exact final scores:
    # laying 2 eggs is worth at least 2 points more than gaining food or drawing a card.
    assert info["top"][0][2] - info["top"][1][2] >= 2.0


def test_same_seed_gives_the_same_choice():
    s = api.new_game(api.GameConfig(3, {"coop_goals": {}}), 4)
    a = decide(s, agent(s.cfg, s.pend[0], iterations=60, seed=5))
    b = decide(s, agent(s.cfg, s.pend[0], iterations=60, seed=5))
    assert a == b and a in s.pend[2]


def test_minor_decisions_use_the_smaller_budget():
    s = last_turn_position()
    a = agent(s.cfg, iterations=40, minor_iterations=6)
    decide(s, a)
    assert a.info()["iterations"] == 40
    s2 = fresh(2)
    feeder(s2, "fish", "seed", "fruit")
    set_turn(s2, 0)
    rules.resume(s2, ("food",))
    assert s2.pend[1] == "take_die"
    decide(s2, a)
    assert a.info()["iterations"] == 6


def test_time_budget_and_greedy_rollouts():
    s = last_turn_position()
    a = agent(s.cfg, ms=30)
    assert decide(s, a) in s.pend[2] and a.info()["iterations"] >= 3
    g = agent(s.cfg, iterations=6, rollout="greedy")
    assert decide(s, g) in s.pend[2]
    with pytest.raises(ValueError):
        MCTSAgent(rollout="heuristic")


def test_utilities_follow_the_objective():
    s = last_turn_position()
    totals = api.totals(s)
    assert agent(s.cfg, w=0.0).utilities(s) == totals
    team = agent(s.cfg, w=1.0).utilities(s)
    assert team[0] == team[1] == pytest.approx(sum(totals) / 2)


def test_plays_a_full_game_with_closed_hands_and_beats_random():
    cfg = api.GameConfig(2, {"coop_goals": {}}, open_hands=False)
    from wingsim.agents import group_policies
    policy = group_policies.parse("fixed(1)")
    policy.start(cfg)
    agents = [MCTSAgent(iterations=30, minor_iterations=8, seed=1), RandomAgent(3)]
    for i, a in enumerate(agents):
        a.start(cfg, i, Objective(0.0, 2))
    s = play_game(cfg, 2, agents, policy)
    totals = api.totals(s)
    assert api.is_over(s) and totals[0] > totals[1] + 10


# ---------------------------------------------------------------- controls

def row(seed, w, shared_chosen, condition="coop"):
    return {"condition": condition, "players": 5, "seed": seed, "probe": 0, "round": 1, "turn_no": 1,
            "player": 0, "w": w, "choice": "play", "chose_shared": shared_chosen,
            "chose_other_bird": not shared_chosen,
            "offers": [[1, True, 1, "3-4", "brown", shared_chosen], [2, False, 1, "3-4", "brown", not shared_chosen],
                       [3, False, 3, "7+", "white", False]]}


def test_pick_rates_match_on_strata():
    rows = [row(i, 0.0, i % 4 == 0) for i in range(40)]
    shared, other, offers, covered = controls.pick_rates(rows, ("cost", "vp"))
    assert shared == 0.25 and other == 0.75 and offers == 40 and covered == 1.0   # the 7+ bird is not a match


def test_control_verdicts():
    rows = []
    for i in range(60):
        rows += [row(i, 0.0, i % 4 == 0), row(i, 1.0, i % 4 != 3)]                 # coop: 25% -> 75%
        rows += [row(i, 0.0, i % 2 == 0, "baseline"), row(i, 1.0, i % 2 == 0, "baseline")]   # baseline: 50/50
    result = controls.analyse(rows)
    assert result["coop"]["paired"]["diff"] == pytest.approx(0.5) and result["positive_pass"]
    assert result["baseline"]["arms"][0.0]["cost_points"]["gap"] == pytest.approx(0.0)
    assert result["negative_pass"] and not result["negative_avoids"]
    # No effect of w: the positive control is not shown.
    flat = [r for i in range(60) for r in (row(i, 0.0, i % 2 == 0), row(i, 1.0, i % 2 == 0),
                                           row(i, 0.0, True, "baseline"))]
    result = controls.analyse(flat)
    assert not result["positive_pass"]
    assert not result["negative_pass"]            # selfish baseline bots always took the shared bird


def test_probe_game_pairs_arms_on_the_same_positions(tmp_path):
    rows = controls.probe_game(("coop", 3, 11, 2, (0.0, 1.0), {"iterations": 20, "minor_iterations": None, "c": 0.7}))
    assert rows and len(rows) % 2 == 0
    by = {}
    for r in rows:
        by.setdefault((r["seed"], r["probe"]), []).append(r)
    for pair in by.values():
        assert [r["w"] for r in pair] == [0.0, 1.0]
        assert pair[0]["turn_no"] == pair[1]["turn_no"]
        cards = [[o[:5] for o in r["offers"]] for r in pair]
        assert cards[0] == cards[1]
        flags = {o[1] for o in pair[0]["offers"]}
        assert flags == {True, False}             # a shared-benefit bird and another bird were both playable
    result = controls.analyse(rows + [dict(r, condition="baseline") for r in rows])
    path = controls.write_report(result, {"pilot": True}, tmp_path / "controls.md")
    assert "## Positive control" in path.read_text() and "## Negative control" in path.read_text()
