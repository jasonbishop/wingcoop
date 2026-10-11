"""Base-game rule tests."""
import pytest

from wingsim.engine import api, rules, scoring
from wingsim.engine.cards import db as load_db
from wingsim.engine.state import SETUP, TURNS

from .helpers import (F, H, bird, drive, feeder, first_until, food, fresh, hand, opts, pick, put, set_turn,
                      slot, top, tray, turn)


def fake_bird(cost=(0, 0, 0, 0, 0), wild=0, either=False):
    class B:
        pass
    b = B()
    b.cost, b.wild, b.either = cost, wild, either
    b.total_cost = 1 if either else sum(cost) + wild
    return b


def test_setup_deal_and_choices():
    for n in (2, 3, 4, 5):
        s = api.new_game(api.GameConfig(n), 11)
        assert all(len(pl.hand) == 5 and len(pl.bonus) == 2 and pl.food == [1] * 5 for pl in s.players)
        assert len(s.tray) == 3 and len(s.feeder) == 5 and len(s.goals) == 4
        assert len(s.deck) == 180 - 5 * n - 3
        assert len({load_db().goals[g].tile for g in s.goals}) == 4     # four different tiles
        d = api.pending_decision(s)
        assert d.kind == "setup_keep_birds" and len(d.options) == 32 and d.player == s.first
    p = d.player
    keep = tuple(s.players[p].hand[:2])
    s = api.apply(s, d, ("keep", keep))
    d = api.pending_decision(s)
    assert d.kind == "setup_discard_food" and len(d.options) == 10     # pay 1 food per bird kept
    s = api.apply(s, d, d.options[0])
    assert sum(s.players[p].food) == 3 and s.players[p].hand == list(keep)
    d = api.pending_decision(s)
    assert d.kind == "setup_keep_bonus" and len(d.options) == 2
    s = api.apply(s, d, d.options[1])
    assert len(s.players[p].bonus) == 1 and len(s.bonus_discard) == 1


@pytest.mark.parametrize("column,cost", [(0, 0), (1, 1), (2, 1), (3, 2), (4, 2)])
def test_egg_cost_by_column(column, cost):
    s = fresh()
    fillers = pick(lambda b: True, column, exclude=["Mourning Dove", "Killdeer"])
    for name in fillers:
        put(s, 0, name, "forest")
    holder = put(s, 0, "Mourning Dove", "grassland", eggs=cost)
    newcomer, = pick(lambda b: 0 in b.habitats and b.timing != "white", exclude=fillers + ["Mourning Dove"])
    cid, = hand(s, 0, newcomer)
    s.players[0].food = [3, 3, 3, 3, 3]
    assert ("play", cid, H["forest"]) in rules.play_options(s, 0)
    if cost:
        slot(s, 0, "Mourning Dove")[1] = cost - 1                      # one egg short: not playable there
        assert ("play", cid, H["forest"]) not in rules.play_options(s, 0)
        slot(s, 0, "Mourning Dove")[1] = cost
    set_turn(s, 0)
    drive(s, ("play", cid, H["forest"]))
    first_until(s, "action", player=1)
    assert s.players[0].board[H["forest"]][column][0] == cid
    assert slot(s, 0, "Mourning Dove")[1] == 0
    assert sum(s.players[0].food) == 15 - load_db().by_name[newcomer].total_cost


def test_sixth_bird_does_not_fit():
    s = fresh()
    for name in pick(lambda b: True, 5, exclude=["Mourning Dove"]):
        put(s, 0, name, "forest", eggs=1)
    newcomer, = pick(lambda b: b.habitats == (0,), exclude=[x for x in ()])
    if bird(newcomer) in [x[0] for x in s.players[0].board[0]]:
        newcomer = pick(lambda b: b.habitats == (0,), 7)[-1]
    hand(s, 0, newcomer)
    s.players[0].food = [3, 3, 3, 3, 3]
    assert rules.play_options(s, 0) == []


def test_food_payments():
    pay = rules.payments
    # Exact foods: one way to pay.
    assert pay([1, 1, 0, 0, 0], fake_bird((1, 1, 0, 0, 0))) == [(1, 1, 0, 0, 0)]
    # A wild cost takes any one food.
    assert sorted(pay([1, 0, 2, 0, 0], fake_bird(wild=1))) == [(0, 0, 1, 0, 0), (1, 0, 0, 0, 0)]
    # Ruling 20200907: any 2 food stand in for 1 food you lack, as often as needed.
    assert pay([0, 2, 0, 0, 0], fake_bird((0, 0, 1, 0, 0))) == [(0, 2, 0, 0, 0)]
    assert pay([0, 4, 0, 0, 0], fake_bird((0, 0, 2, 0, 0))) == [(0, 4, 0, 0, 0)]
    assert not rules.can_afford([0, 3, 0, 0, 0], fake_bird((0, 0, 2, 0, 0)))
    assert not rules.can_afford([0, 1, 0, 0, 0], fake_bird((0, 0, 1, 0, 0)))
    # The exchange covers only what is missing: the fish held is spent as fish.
    assert pay([0, 2, 1, 0, 0], fake_bird((0, 0, 2, 0, 0))) == [(0, 2, 1, 0, 0)]
    # Either/or cost: any one of the listed foods, or 2 of anything when holding none of them.
    either = fake_bird((1, 1, 0, 0, 0), either=True)
    assert sorted(pay([1, 1, 1, 0, 0], either)) == [(0, 1, 0, 0, 0), (1, 0, 0, 0, 0)]
    assert pay([0, 0, 2, 0, 0], either) == [(0, 0, 2, 0, 0)]
    assert not rules.can_afford([0, 0, 1, 0, 0], either)
    assert pay([5, 5, 5, 5, 5], fake_bird()) == [(0, 0, 0, 0, 0)]
    # can_afford agrees with payments on every small holding.
    import itertools
    for b in (fake_bird((1, 0, 1, 0, 0)), fake_bird((0, 2, 0, 0, 0), wild=1), fake_bird(wild=2), either,
              fake_bird((0, 0, 0, 0, 3))):
        for have in itertools.product(range(3), repeat=5):
            options = pay(list(have), b)
            assert bool(options) == rules.can_afford(list(have), b), (have, b.cost, b.wild)
            for v in options:
                assert all(0 <= v[i] <= have[i] for i in range(5))


@pytest.mark.parametrize("habitat,birds,gain,trade", [
    ("forest", 0, 1, False), ("forest", 1, 1, True), ("forest", 2, 2, False), ("forest", 5, 3, True),
    ("grassland", 0, 2, False), ("grassland", 3, 3, True), ("grassland", 4, 4, False),
    ("wetland", 0, 1, False), ("wetland", 2, 2, False), ("wetland", 3, 2, True),
])
def test_action_strength_and_bonus_trade(habitat, birds, gain, trade):
    s = fresh()
    plain = pick(lambda b: b.timing is None or b.timing == "white", birds + 1, exclude=["Mourning Dove"])
    for name in plain[:birds]:
        put(s, 0, name, habitat)
    put(s, 0, "Mourning Dove", "forest" if habitat != "forest" else "grassland")
    slot(s, 0, "Mourning Dove")[1] = 0
    hand(s, 0, plain[birds])
    food(s, 0, fish=1)
    if habitat == "wetland" and trade:
        slot(s, 0, "Mourning Dove")[1] = 1
    feeder(s, "fish", "seed", "fruit", "rodent", "invertebrate")
    top(s, "Mallard", "Osprey", "Killdeer", "Canvasback")
    before = (sum(s.players[0].food), scoring.player_breakdown(s, 0)["eggs"], len(s.players[0].hand))
    set_turn(s, 0)
    drive(s, ({"forest": "food", "grassland": "eggs", "wetland": "cards"}[habitat],))
    seen_trade = False
    while s.pend is not None and s.turn == 0:
        if s.pend[1] == "bonus_trade":
            seen_trade = True
            assert opts(s)[0] == ("skip",) and len(opts(s)) > 1
        rules.resume(s, s.pend[2][0])                    # first option: always skips the trade
    after = (sum(s.players[0].food), scoring.player_breakdown(s, 0)["eggs"], len(s.players[0].hand))
    delta = [a - b for a, b in zip(after, before)]
    index = {"forest": 0, "grassland": 1, "wetland": 2}[habitat]
    capacity = sum(load_db().birds[x[0]].egg_limit for row in s.players[0].board for x in row)
    expected = min(gain, capacity) if habitat == "grassland" else gain
    assert delta[index] == expected
    assert seen_trade == trade


def test_bonus_trades_convert_resources():
    s = fresh()
    a, b = pick(lambda x: x.timing is None, 2)
    put(s, 0, a, "forest")
    c, = hand(s, 0, "Mallard")
    feeder(s, "fish", "seed", "fruit")
    set_turn(s, 0)
    drive(s, ("food",), ("die", F["fish"], F["fish"]), ("discard_card", c), ("die", F["seed"], F["seed"]))
    assert s.players[0].food == [0, 1, 1, 0, 0] and c in s.discard and s.turn == 1
    put(s, 0, b, "grassland")
    set_turn(s, 0)
    drive(s, ("eggs",))
    first_until(s, "bonus_trade")
    eggs = scoring.player_breakdown(s, 0)["eggs"]
    drive(s, ("discard_food", F["fish"]))
    first_until(s, "action", player=1)
    assert s.players[0].food == [0, 1, 0, 0, 0] and scoring.player_breakdown(s, 0)["eggs"] == eggs + 1


def test_birdfeeder_refills_when_empty_and_may_be_rerolled_when_all_dice_match():
    s = fresh()
    feeder(s, "fish")
    set_turn(s, 0)
    drive(s, ("food",))
    # One die left: all dice show the same face, so the player may reroll first.
    assert s.pend[1] == "reroll_feeder" and opts(s) == [("keep",), ("reroll",)]
    drive(s, ("keep",))                                   # the single fish is then the only choice
    assert s.players[0].food == [0, 0, 1, 0, 0]
    assert len(s.feeder) == 5                             # emptied, so all 5 dice were rolled back in
    feeder(s, "seed", "seed")
    set_turn(s, 0)
    drive(s, ("food",), ("reroll",))
    assert len(s.feeder) + sum(s.players[0].food) - 1 == 5
    feeder(s, "seed", "fish")
    set_turn(s, 0)
    drive(s, ("food",))
    assert s.pend[1] == "take_die"                        # different faces: no reroll offered


def test_tray_refills_only_at_end_of_turn():
    s = fresh()
    a, b, c = tray(s, "Mallard", "Osprey", "Killdeer")
    for name in pick(lambda x: x.timing is None, 2):
        put(s, 0, name, "wetland")                        # 2 birds: draw 2 cards
    set_turn(s, 0)
    drive(s, ("cards",), ("tray", a))
    assert s.tray == [b, c] and ("tray", a) not in opts(s)
    drive(s, ("tray", b))
    assert s.turn == 1 and len(s.tray) == 3 and c in s.tray
    assert s.players[0].hand == [a, b]


def test_round_structure_cubes_first_player_and_tray():
    cfg = api.GameConfig(3, record_events=True)
    s = api.new_game(cfg, 5)
    first0 = s.first
    seen = {}
    turns_in_round = {1: 0, 2: 0, 3: 0, 4: 0}
    last_turn_no = -1
    while s.pend is not None:
        if s.phase == TURNS and s.pend[1] == "action" and s.turn_no != last_turn_no:
            last_turn_no = s.turn_no
            turns_in_round[s.round] += 1
            seen.setdefault(s.round, (s.first, list(s.actions_left)))
        rules.resume(s, s.pend[2][0])
    # One action cube fewer each round: 8, 7, 6, 5 turns per player.
    assert turns_in_round == {1: 24, 2: 21, 3: 18, 4: 15}
    assert [seen[r][1] for r in (1, 2, 3, 4)] == [[8] * 3, [7] * 3, [6] * 3, [5] * 3]
    # The first-player token passes clockwise.
    assert [seen[r][0] for r in (1, 2, 3, 4)] == [(first0 + i) % 3 for i in range(4)]
    assert api.is_over(s) and len(s.goal_log) == 4
    ends = [e for e in s.events if e["e"] == "round_end"]
    assert [e["round"] for e in ends] == [1, 2, 3, 4]
    assert len(s.tray) == 3


def test_round_end_replaces_tray_and_scores_blue_side():
    s = fresh(2)
    old = tray(s, "Mallard", "Osprey", "Killdeer")
    goal = load_db().goals[s.goals[0]]
    s.actions_left = [0, 0]
    for name in pick(lambda b: True, 3):
        put(s, 0, name, "forest", eggs=1)
        put(s, 0, pick(lambda b: True, 12)[-1 - len(s.players[0].board[1])], "grassland", eggs=1)
    counts = [scoring.goal_count(s, j, goal) for j in range(2)]
    s.pend = None
    s.stack = [("main",)]
    s.phase = TURNS
    rules.run(s)
    assert s.round == 2 and all(c in s.discard for c in old) and len(s.tray) == 3
    assert s.goal_points == [float(min(c, 5)) for c in counts]
    assert s.first == 1 and s.actions_left == [7, 7] and s.group_score == 0


def test_goal_counts(db):
    s = fresh()
    by_kind = {}
    for g in db.goals.values():
        by_kind.setdefault((g.kind, g.param), g)
    bowl = pick(lambda b: b.nest == "bowl" and b.egg_limit >= 2, 2)
    star, = pick(lambda b: b.nest == "wild" and b.egg_limit >= 2)
    ground, = pick(lambda b: b.nest == "ground" and b.egg_limit >= 2)
    put(s, 0, bowl[0], "forest", eggs=2)
    put(s, 0, bowl[1], "forest", eggs=0)
    put(s, 0, star, "grassland", eggs=1)
    put(s, 0, ground, "wetland", eggs=2)
    count = lambda kind, prm=None: scoring.goal_count(s, 0, by_kind[(kind, prm)])
    assert count("birds_in_habitat", 0) == 2 and count("birds_in_habitat", 1) == 1
    assert count("eggs_in_habitat", 0) == 2 and count("eggs_in_habitat", 2) == 2
    assert count("total_birds") == 4
    assert count("egg_sets") == 1                          # eggs per habitat: 2, 1, 2
    assert count("nest_birds_with_egg", "bowl") == 2       # one bowl bird with eggs + the star nest
    assert count("eggs_in_nest", "bowl") == 3              # ruling 20190921: star nests count
    assert count("eggs_in_nest", "ground") == 3


def test_final_scoring_categories(db):
    s = fresh()
    a = put(s, 0, "Carolina Chickadee", "forest", eggs=2, cached=3)
    b = put(s, 0, "American Coot", "wetland", eggs=1, tucked=2)
    falconer = next(c.id for c in db.bonus.values() if c.name == "Falconer")
    s.players[0].bonus = [falconer]
    put(s, 0, "Barred Owl", "forest")
    s.goal_points[0] = 4.0
    row = scoring.player_breakdown(s, 0)
    vp = db.birds[a].vp + db.birds[b].vp + db.by_name["Barred Owl"].vp
    assert row == {"birds": vp, "bonus": 2, "eggs": 3, "cached": 3, "tucked": 2, "goals": 4.0,
                   "total": vp + 2 + 3 + 3 + 2 + 4.0}
    assert scoring.totals(s)[0] == row["total"]
    result = scoring.breakdown(s)
    assert result["team_total"] == sum(p["total"] for p in result["players"]) + result["group"]


def test_state_based_bonus_cards(db):
    s = fresh()
    by = {c.name: c for c in db.bonus.values()}
    names = pick(lambda b: b.egg_limit >= 4, 3)
    put(s, 0, names[0], "forest", eggs=4)
    put(s, 0, names[1], "forest", eggs=1)
    put(s, 0, names[2], "grassland", eggs=0)
    hand(s, 0, "Mallard", "Osprey")
    assert scoring.bonus_count(s, 0, by["Breeding Manager"]) == 1
    assert scoring.bonus_count(s, 0, by["Oologist"]) == 2
    assert scoring.bonus_count(s, 0, by["Ecologist"]) == 0      # the wetland is empty
    assert scoring.bonus_count(s, 0, by["Visionary Leader"]) == 2


def test_tiebreak_by_leftover_food():
    s = fresh(3)
    for p, name in enumerate(pick(lambda b: b.vp == 4, 3)):
        put(s, p, name, "forest")
    s.players[2].board[0][0][1] = 0
    food(s, 0, fish=1)
    food(s, 1, seed=2)
    food(s, 2, seed=2)
    result = api.final_scores(s)
    assert [p["total"] for p in result["players"]] == [4, 4, 4]
    assert result["winners"] == [1, 2] and result["leftover_food"] == [1, 2, 2]
    put(s, 0, pick(lambda b: b.vp == 1, 1)[0], "grassland")
    assert api.final_scores(s)["winners"] == [0]


def test_illegal_choice_is_rejected_and_apply_is_pure():
    s = api.new_game(api.GameConfig(2), 3)
    d = api.pending_decision(s)
    before = s.rng, list(s.deck), [list(pl.hand) for pl in s.players]
    with pytest.raises(api.IllegalChoice):
        api.apply(s, d, ("play", 1, 0))
    s2 = api.apply(s, d, d.options[0])
    assert (s.rng, list(s.deck), [list(pl.hand) for pl in s.players]) == before
    assert s2 is not s and api.pending_decision(s) == d
    with pytest.raises(api.IllegalChoice):
        api.apply(s2, d, d.options[0])                    # stale decision: a different one is pending now
