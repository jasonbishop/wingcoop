"""Greedy agent and objective tests."""
import pytest

from wingsim.agents.base import Objective
from wingsim.agents.greedy import DEFAULT_WEIGHTS, GreedyAgent
from wingsim.agents.random import RandomAgent
from wingsim.engine import api, rules
from wingsim.engine.state import state_hash
from wingsim.game import play_game

from .helpers import F, bird, feeder, fresh, hand, pick, put, set_turn, slot


def started(cfg, w, share=False, seed=1, weights=None):
    agents = [GreedyAgent(weights, seed) for _ in range(cfg.n)]
    for i, a in enumerate(agents):
        a.start(cfg, i, Objective(w, cfg.n, share))
    return agents


def test_objective():
    assert Objective(0.0, 4).utility(30, 100, 8) == 30
    assert Objective(1.0, 4).utility(30, 100, 8) == 25
    assert Objective(0.5, 4).utility(30, 100, 8) == 27.5
    # With group_share, an equal share of the group score counts as the player's own.
    assert Objective(0.0, 4, True).utility(30, 100, 8) == 32
    assert Objective(1.0, 4, True).utility(30, 100, 8) == 25
    assert "own" in Objective(0, 3).describe() and "team" in Objective(1, 3).describe()


def test_unknown_weight_is_rejected():
    with pytest.raises(ValueError):
        GreedyAgent({"osprey_bonus": 3})
    assert GreedyAgent({"food": 1.5}).w["food"] == 1.5 and GreedyAgent().w == DEFAULT_WEIGHTS


@pytest.mark.parametrize("plugins", [None, {"coop_goals": {}}])
def test_greedy_games_are_reproducible(plugins):
    from wingsim.agents import group_policies

    def one():
        cfg = api.GameConfig(3, plugins)
        policy = group_policies.parse("fixed(2)")
        policy.start(cfg)
        return play_game(cfg, 6, started(cfg, 0.5), policy)

    a, b = one(), one()
    assert api.is_over(a) and state_hash(a) == state_hash(b)


def test_greedy_beats_random():
    cfg = api.GameConfig(2)
    greedy = wins = 0
    for seed in range(4):
        agents = [GreedyAgent(None, seed), RandomAgent(seed)]
        for i, a in enumerate(agents):
            a.start(cfg, i, Objective(0.0, 2))
        totals = api.totals(play_game(cfg, seed, agents))
        wins += totals[0] > totals[1]
        greedy += totals[0] - totals[1]
    assert wins == 4 and greedy / 4 > 10


def decide(s, agent):
    d = api.pending_decision(s)
    return agent.choose(api.observe(s, d.player), d), agent.info()


def test_greedy_takes_points_on_the_last_turn():
    s = fresh(2)
    put(s, 0, pick(lambda b: b.egg_limit >= 4 and b.timing is None, 1)[0], "grassland")
    s.round, s.actions_left = 4, [1, 0]
    feeder(s, "fish", "seed", "fruit")
    set_turn(s, 0)
    choice, info = decide(s, started(s.cfg, 0.0)[0])
    assert choice == ("eggs",)                      # food and cards are worth nothing after the last turn
    assert info["options"] == 3 and info["values"][0][0] == ("eggs",)


def test_goal_scoring_is_seen_through_the_engine_not_the_plugin():
    """The same agent code values goal progress under either rule set, via api.score_goal_counts."""
    for plugins in (None, {"coop_goals": {}}):
        s = fresh(2, plugins=plugins)
        if plugins:
            s.variant["coop.d"] = 2
        agent = started(s.cfg, 1.0)[0]
        agent.goal_cache = {}
        low = agent.project_goal(s, (1, 2), (0, 0))
        high = agent.project_goal(s, (2, 2), (0, 0))
        if plugins:
            assert low == ([0.0, 0.0], -3.0) and high == ([0.0, 0.0], 4.0)
        else:
            assert low == ([1.0, 2.0], 0.0) and high == ([2.0, 2.0], 0.0)


def test_shared_powers_reach_the_objective_through_measured_yields():
    """The mechanism the motivation weight works through. The agent measures what a row
    produces for every player by running it; a team-minded agent counts the other players'
    share and a selfish one does not. No agent code names the card."""
    def board(name):
        s = fresh(3)
        put(s, 0, name, "forest")
        set_turn(s, 0)
        return s

    shared, private = board("Red Crossbill"), board("Spotted Towhee")   # all gain 1 seed / gain 1 seed
    probe = started(shared.cfg, 0.5)[0]
    y_shared = probe.row_yield(shared, 0, 0, 0)
    y_private = probe.row_yield(private, 0, 0, 0)
    assert y_shared[1] > 0 and y_shared[2] > 0
    assert y_private[1] == y_private[2] == 0 and y_private[0] == pytest.approx(y_shared[0])

    def preference(w):       # how much better the shared board looks than the private one
        agent = started(shared.cfg, w)[0]
        agent.goal_cache = {}
        v = agent.value(shared)
        agent.goal_cache = {}
        return v - agent.value(private)

    # Own-side differences (points, egg room) scale by 1 for w = 0 and by 1/3 for w = 1, so
    # 3 x preference(1) - preference(0) isolates what the other two players receive.
    others = 3 * preference(1.0) - preference(0.0)
    turns = 26
    expected = DEFAULT_WEIGHTS["rate_forest"] * turns * (y_shared[1] + y_shared[2])
    assert others == pytest.approx(expected) and others > 1


def test_selfish_and_team_agents_differ_only_through_the_objective():
    s = fresh(3)
    put(s, 0, "Osprey", "wetland")
    set_turn(s, 0)
    a, b = started(s.cfg, 0.0)[0], started(s.cfg, 1.0)[0]
    assert a.w == b.w and a.yields == b.yields == {}
    a.goal_cache, b.goal_cache = {}, {}
    a.value(s), b.value(s)
    assert a.yields == b.yields                      # the same measurements of what each row produces
