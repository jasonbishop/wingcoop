"""Plugin tests: coop_goals, open_hands, the hooks and group policies."""
import pytest

from wingsim.agents import group_policies
from wingsim.agents.random import RandomAgent
from wingsim.engine import api, rules, scoring
from wingsim.engine.observe import HIDDEN
from wingsim.game import play_game
from wingsim.plugins import Plugin
from wingsim.plugins.coop_goals import CoopGoals

from .helpers import fresh, pick, put


def coop_state(n=4, **settings):
    s = fresh(n, plugins={"coop_goals": settings})
    return s, s.cfg.plugins[0]


def test_worked_example_from_the_spec():
    s, plugin = coop_state(4)
    s.variant["coop.d"] = 3
    assert plugin.round_end_scoring(s, (5, 4, 3, 3)) == ([0.0] * 4, 11.25, ("coop", 3, True))
    assert plugin.round_end_scoring(s, (5, 4, 3, 2)) == ([0.0] * 4, -10.5, ("coop", 3, False))


def test_counts_are_capped_at_five_and_no_individual_goal_points():
    s, plugin = coop_state(2)
    s.variant["coop.d"] = 5
    ind, delta, info = plugin.round_end_scoring(s, (9, 5))
    assert ind == [0.0, 0.0] and delta == 25.0 and info == ("coop", 5, True)
    assert plugin.round_end_scoring(s, (9, 4))[1] == -22.5


@pytest.mark.parametrize("penalty,expected", [("avg_x_d", -10.5), ("d_x_d", -9.0), ("flat:4", -4.0)])
def test_penalty_options(penalty, expected):
    s, plugin = coop_state(4, penalty=penalty)
    s.variant["coop.d"] = 3
    assert plugin.round_end_scoring(s, (5, 4, 3, 2))[1] == expected
    assert plugin.round_end_scoring(s, (5, 4, 3, 3))[1] == 11.25      # success is unaffected


def test_unknown_penalty_and_bad_range_are_rejected():
    with pytest.raises(ValueError):
        CoopGoals(penalty="double")
    with pytest.raises(ValueError):
        CoopGoals(difficulty_range=(0, 5))


def difficulty_options(s):
    assert s.pend[0] == api.GROUP and s.pend[1] == "set_difficulty"
    return [o[1] for o in s.pend[2]]


def start_round(s, r):
    s.round = r
    s.phase = 1
    s.pend = None
    s.stack = [("main",)]
    rules.run(s)


def test_group_sets_difficulty_after_setup_from_the_full_range():
    cfg = api.GameConfig(3, {"coop_goals": {}})
    s = api.new_game(cfg, 1)
    while s.pend[0] != api.GROUP:
        assert s.phase == 0                                  # still in setup: all four goals are visible
        rules.resume(s, s.pend[2][0])
    assert difficulty_options(s) == [1, 2, 3, 4, 5] and len(s.goals) == 4
    rules.resume(s, ("difficulty", 4))
    assert s.variant["coop.d"] == 4 and s.pend[1] == "action"


@pytest.mark.parametrize("changes,d,expected", [
    ((0, 1), 2, [2, 3]), ((0, 1), 5, [5]), ((-1, 0, 1), 3, [2, 3, 4]), ((-1, 0, 1), 1, [1, 2]),
    ((-1, 0, 1), 5, [4, 5]),
])
def test_allowed_changes_stay_within_one_to_five(changes, d, expected):
    s, plugin = coop_state(2, allowed_changes=changes)
    s.variant["coop.d"] = d
    start_round(s, 2)
    if len(expected) == 1:                                    # a forced choice is not asked
        assert s.pend[0] != api.GROUP and s.variant["coop.d"] == expected[0]
    else:
        assert difficulty_options(s) == expected


def test_difficulty_range_limits_the_first_choice():
    cfg = api.GameConfig(2, {"coop_goals": {"difficulty_range": [2, 4]}})
    s = api.new_game(cfg, 1)
    while s.pend[0] != api.GROUP:
        rules.resume(s, s.pend[2][0])
    assert difficulty_options(s) == [2, 3, 4]


def test_round_end_changes_group_score_not_individual_scores():
    s, plugin = coop_state(2)
    s.variant["coop.d"] = 1
    goal = s.cfg.db.goals[s.goals[0]]
    names = pick(lambda b: b.egg_limit >= 2, 12)
    for p in range(2):
        for h in ("forest", "grassland", "wetland"):
            put(s, p, names.pop(), h, eggs=2)
    counts = [min(5, scoring.goal_count(s, p, goal)) for p in range(2)]
    assert min(counts) >= 1
    s.actions_left = [0, 0]
    s.pend = None
    s.stack = [("main",)]
    rules.run(s)
    assert s.goal_points == [0.0, 0.0]
    assert s.group_score == sum(counts) / 2 * 1
    assert s.goal_log[-1][4] == ("coop", 1, True)
    result = api.scores(s)
    assert result["group"] == s.group_score
    assert result["team_total"] == sum(p["total"] for p in result["players"]) + s.group_score
    assert all(p["goals"] == 0 for p in result["players"])


def test_baseline_scores_goals_individually_with_no_group_score():
    s = fresh(3)
    assert api.score_goal_counts(s, (7, 3, 0)) == ([5.0, 3.0, 0.0], 0.0, None)


@pytest.mark.parametrize("flag", [True, False])
def test_open_hands_observation_contents(flag):
    for where in ({"open_hands": flag}, {"plugins": {"open_hands": flag}}):
        cfg = api.GameConfig(3, **where)
        assert cfg.open_hands is flag
        s = api.new_game(cfg, 3)
        o = api.observe(s, 0).state
        assert o.players[0].hand == s.players[0].hand and o.players[0].bonus == s.players[0].bonus
        for j in (1, 2):
            if flag:
                assert o.players[j].hand == s.players[j].hand and o.players[j].bonus == s.players[j].bonus
            else:
                assert o.players[j].hand == [HIDDEN] * 5 and o.players[j].bonus == [HIDDEN] * 2
        assert set(o.deck) == {HIDDEN}                        # the deck order stays hidden either way
    assert api.GameConfig(3).open_hands is True               # on by default


class GiftPlugin(Plugin):
    """Test plugin for the extra_options and on_event hooks: once per turn, take 1 fish for free."""
    name = "gift"
    option_tags = ("gift",)

    def on_setup(self, s):
        s.variant["gift.used"] = -1
        s.variant["gift.plays"] = 0

    def extra_options(self, s, p, when):
        if when == "turn_start" and s.variant["gift.used"] != s.turn_no:
            return [("gift", 2)]
        return []

    def apply_option(self, s, p, option):
        s.players[p].food[option[1]] += 1
        s.variant["gift.used"] = s.turn_no

    def on_event(self, s, kind, data):
        if kind == "bird_played":
            s.variant["gift.plays"] += 1

    def final_scoring(self, s, result):
        result["group"] += 100


def test_extra_options_on_event_and_final_scoring_hooks():
    cfg = api.GameConfig(2)
    cfg.plugins = (GiftPlugin(),)
    cfg.option_plugins = cfg.event_plugins = cfg.final_plugins = cfg.plugins
    cfg.plugin_tags = {"gift": cfg.plugins[0]}
    s = api.new_game(cfg, 2)
    while s.pend[1] != "action":
        rules.resume(s, s.pend[2][0])
    p = s.pend[0]
    assert ("gift", 2) in s.pend[2]
    fish = s.players[p].food[2]
    rules.resume(s, ("gift", 2))
    assert s.players[p].food[2] == fish + 1
    assert s.pend[1] == "action" and s.pend[0] == p and ("gift", 2) not in s.pend[2]   # free action, once
    plays = 0
    while s.pend is not None:
        choice = next((o for o in s.pend[2] if o[0] == "play"), s.pend[2][-1])
        plays += choice[0] in ("play",)
        rules.resume(s, choice)
    assert s.variant["gift.plays"] >= plays > 0               # on_event saw every bird played
    assert api.scores(s)["group"] == 100                      # final_scoring adds to the group score
    assert api.totals(s) == [x["total"] for x in api.scores(s)["players"]]


# ---------------------------------------------------------------- group policies

def group_decision(d, history=()):
    s, plugin = coop_state(3, allowed_changes=(-1, 0, 1))
    s.variant["coop.d"] = d
    s.goal_log = tuple((i + 1, (0, 0, 0), (0.0,) * 3, 0.0, ("coop", d, ok)) for i, ok in enumerate(history))
    if d is None:
        s.stack = [("main",)]
        rules.push_group_decision(s, plugin, "set_difficulty", [("difficulty", x) for x in range(1, 6)])
        s.pend = None
        rules.run(s)
    else:
        start_round(s, len(history) + 1)
    return api.observe(s, api.GROUP), api.pending_decision(s)


def test_parse_policies():
    assert group_policies.parse("fixed(2)").label == "fixed(2)"
    assert group_policies.parse("ladder(2,+1,0)").label == "ladder(2,+1,+0)"
    assert group_policies.parse("ladder(3, +1, -1)").on_fail == -1
    assert group_policies.parse("estimate").rollouts == 2
    with pytest.raises(ValueError):
        group_policies.parse("always(5)")


def test_fixed_policy():
    assert group_policies.parse("fixed(3)").choose(*group_decision(None)) == ("difficulty", 3)
    # Later rounds: 3 is within reach of the allowed changes from 2, 3 and 4 only.
    assert group_policies.parse("fixed(3)").choose(*group_decision(2, [True])) == ("difficulty", 3)
    assert group_policies.parse("fixed(5)").choose(*group_decision(2, [True])) == ("difficulty", 3)


def test_ladder_policy():
    ladder = group_policies.parse("ladder(2,+1,-1)")
    assert ladder.choose(*group_decision(None)) == ("difficulty", 2)
    assert ladder.choose(*group_decision(2, [True])) == ("difficulty", 3)
    assert ladder.choose(*group_decision(3, [True, False])) == ("difficulty", 2)
    hold = group_policies.parse("ladder(2,+1,0)")
    assert hold.choose(*group_decision(3, [True, False])) == ("difficulty", 3)
    assert hold.choose(*group_decision(5, [True, True])) == ("difficulty", 5)


def test_full_coop_game_with_ladder_policy():
    cfg = api.GameConfig(3, {"coop_goals": {}})
    policy = group_policies.parse("ladder(1,+1,0)")
    policy.start(cfg)
    s = play_game(cfg, 5, [RandomAgent(i) for i in range(3)], policy)
    ds = [entry[4][1] for entry in s.goal_log]
    assert len(ds) == 4 and ds[0] == 1 and all(b - a in (0, 1) for a, b in zip(ds, ds[1:]))
    for (_, counts, ind, delta, (_, d, ok)), nxt in zip(s.goal_log, ds[1:] + [None]):
        assert ok == (min(min(c, 5) for c in counts) >= d)
        assert (delta > 0) == (ok and sum(counts) > 0) or delta == 0
        if nxt is not None:
            assert nxt == d + (1 if ok else 0)
    assert api.final_scores(s)["group"] == sum(entry[3] for entry in s.goal_log)
