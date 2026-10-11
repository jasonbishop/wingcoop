"""One test per effect template (and per override): the power runs on a fixture
state and produces exactly the expected change. Rulings from wingsearch are
cited next to the behaviour they decide."""
import json
import pathlib

import pytest

from wingsim.data import build
from wingsim.engine import effects, rules
from wingsim.engine.cards import db as load_db
from wingsim.engine.state import rand_below

from .helpers import (F, FACE, H, all_cards, bird, drive, feeder, first_until, food, fresh, hand, opts, pick,
                      power, put, set_turn, slot, template_of, top, tray, turn)

COVERED = {}


def template(name, example):
    """Mark a test as covering one template, and check the example bird really uses it."""
    def wrap(fn):
        COVERED[name] = fn.__name__

        def test():
            assert template_of(example) == name
            fn()
        test.__name__ = fn.__name__
        return test
    return wrap


def can(s, p, name):
    return effects.feasible(s, p, bird(name), load_db().birds[bird(name)])


def hands(s):
    return [list(pl.hand) for pl in s.players]


def plain(n=1, exclude=(), **want):
    """Birds chosen by printed attributes only."""
    def ok(b):
        return all(getattr(b, k) == v for k, v in want.items()) and b.egg_limit >= 2
    return pick(ok, n, exclude)


# ---------------------------------------------------------------- brown powers

@template("all_draw_deck", "Canvasback")
def test_all_draw_deck():
    s = fresh(3)
    put(s, 0, "Canvasback", "wetland")
    a, b, c = top(s, "Mallard", "Killdeer", "Osprey")
    power(s, 0, "Canvasback")
    assert hands(s) == [[a], [b], [c]]


@template("all_gain_supply", "Osprey")
def test_all_gain_supply():
    s = fresh(3)
    put(s, 1, "Osprey", "wetland")
    power(s, 1, "Osprey")
    assert [pl.food for pl in s.players] == [[0, 0, 1, 0, 0]] * 3


@template("all_lay_nest_plus_one", "Lazuli Bunting")
def test_all_lay_nest_plus_one():
    s = fresh(2)
    a, b, x = plain(3, nest="bowl", exclude=["Lazuli Bunting"])
    put(s, 0, "Lazuli Bunting", "grassland")
    put(s, 0, a, "forest")
    put(s, 0, b, "forest")
    put(s, 1, x, "forest")
    s.pend = None
    s.stack = [("steps", 0, bird("Lazuli Bunting"), load_db().birds[bird("Lazuli Bunting")].steps, 0, ())]
    rules.run(s)
    assert s.pend[0] == 0 and ("skip",) in opts(s)       # ruling 20240604: players may decline
    drive(s, ("bird", bird(a)))
    assert s.pend[0] == 1
    drive(s, ("bird", bird(x)))
    # Ruling 20190406: the two eggs must go on different birds.
    assert s.pend[0] == 0 and ("bird", bird(a)) not in opts(s) and ("bird", bird(b)) in opts(s)
    drive(s, ("bird", bird(b)))
    assert not s.stack
    assert slot(s, 0, a)[1] == 1 and slot(s, 0, b)[1] == 1 and slot(s, 1, x)[1] == 1


@template("cache_supply", "Carolina Chickadee")
def test_cache_supply():
    s = fresh()
    put(s, 0, "Carolina Chickadee", "forest")
    power(s, 0, "Carolina Chickadee")
    assert slot(s, 0, "Carolina Chickadee")[2] == 1
    assert s.players[0].food == [0, 0, 0, 0, 0]


@template("discard_egg_other_gain_wild", "American Crow")
def test_discard_egg_other_gain_wild():
    s = fresh()
    other, = plain(1, nest="bowl")
    put(s, 0, "American Crow", "forest", eggs=1)
    put(s, 0, other, "forest", eggs=1)
    # Only the other bird's egg may be discarded, so that choice is forced.
    power(s, 0, "American Crow", ("food", F["fish"]))
    assert slot(s, 0, "American Crow")[1] == 1 and slot(s, 0, other)[1] == 0
    assert s.players[0].food == [0, 0, 1, 0, 0]
    # Without an egg on another bird the power cannot be used at all.
    assert not can(s, 0, "American Crow")
    # Ruling 20200623: Common Raven's 2 food may be the same type.
    put(s, 0, "Common Raven", "forest")
    slot(s, 0, other)[1] = 1
    power(s, 0, "Common Raven", ("bird", bird(other)), ("food", F["seed"]), ("food", F["seed"]))
    assert s.players[0].food == [0, 2, 1, 0, 0]


@template("discard_egg_draw", "Killdeer")
def test_discard_egg_draw():
    s = fresh()
    put(s, 0, "Killdeer", "grassland", eggs=1)
    t, = tray(s, "Mallard")
    d, = top(s, "Osprey")
    power(s, 0, "Killdeer", ("deck",), ("tray", t))   # its own egg is the only one: forced
    assert slot(s, 0, "Killdeer")[1] == 0
    assert s.players[0].hand == [d, t] and s.tray == []


@template("discard_food_tuck_deck", "Canada Goose")
def test_discard_food_tuck_deck():
    s = fresh()
    put(s, 0, "Canada Goose", "wetland")
    # Ruling 20220213a: the cost needs an actual seed.
    food(s, 0, fish=2)
    assert not can(s, 0, "Canada Goose")
    food(s, 0, seed=1)
    before = len(s.deck)
    power(s, 0, "Canada Goose")
    assert s.players[0].food[F["seed"]] == 0
    assert slot(s, 0, "Canada Goose")[3] == 2 and len(s.deck) == before - 2 and len(s.tucked) == 2


@template("draw", "Mallard")
def test_draw():
    s = fresh()
    put(s, 0, "Mallard", "wetland")
    t, = tray(s, "Osprey")
    power(s, 0, "Mallard", ("tray", t))   # ruling 20221123: tray or deck, the player's choice
    assert s.players[0].hand == [t]


@template("draw_discard_end_of_turn", "Black Tern")
def test_draw_discard_end_of_turn():
    s = fresh()
    tern = put(s, 0, "Black Tern", "wetland")
    a, b = top(s, "Mallard", "Osprey")
    set_turn(s, 0)
    drive(s, ("cards",), ("activate", tern))
    assert s.pend[1] == "discard_card" and set(opts(s)) == {("card", a), ("card", b)}
    drive(s, ("card", a))
    assert s.players[0].hand == [b] and a in s.discard and s.turn == 1


def test_draw_discard_end_of_turn_with_empty_hand():
    # Ruling 20200508: with no card in hand at the end of the turn there is nothing to discard.
    s = fresh()
    tern = put(s, 0, "Black Tern", "wetland")
    s.deck.clear()
    turn(s, 0, ("cards",), ("activate", tern))
    assert s.players[0].hand == [] and s.eot_discard == 0


@template("each_gain_die_in_order", "Anna's Hummingbird")
def test_each_gain_die_in_order():
    s = fresh(3)
    put(s, 0, "Anna's Hummingbird", "forest")
    feeder(s, "fish", "seed", "rodent", "fruit", "invertebrate")
    # Ruling 20200405a: any player may go first, the owner included.
    s.pend = None
    s.stack = [("steps", 0, bird("Anna's Hummingbird"), load_db().birds[bird("Anna's Hummingbird")].steps, 0, ())]
    rules.run(s)
    assert opts(s) == [("player", 0), ("player", 1), ("player", 2)]
    drive(s, ("player", 1), ("die", F["fish"], F["fish"]))
    assert s.pend[0] == 2
    drive(s, ("skip",))                                # ruling 20200420: a player may decline
    assert s.pend[0] == 0
    drive(s, ("die", F["seed"], F["seed"]))
    assert not s.stack
    assert [pl.food for pl in s.players] == [[0, 1, 0, 0, 0], [0, 0, 1, 0, 0], [0, 0, 0, 0, 0]]
    assert sorted(s.feeder) == sorted([F["rodent"], F["fruit"], F["invertebrate"]])


@template("gain_die", "American Redstart")
def test_gain_die():
    s = fresh()
    put(s, 0, "American Redstart", "forest")
    feeder(s, "fish", "rodent", "invertebrate/seed")
    # Ruling 20191126b: any 1 die from the birdfeeder.
    power(s, 0, "American Redstart", ("die", FACE["invertebrate/seed"], F["seed"]))
    assert s.players[0].food == [0, 1, 0, 0, 0] and len(s.feeder) == 2


@template("gain_supply", "Northern Cardinal")
def test_gain_supply():
    s = fresh()
    put(s, 0, "Northern Cardinal", "forest")
    power(s, 0, "Northern Cardinal")
    assert s.players[0].food == [0, 0, 0, 1, 0]


@template("gain_feeder_if_available", "Great Crested Flycatcher")
def test_gain_feeder_if_available():
    s = fresh()
    put(s, 0, "Great Crested Flycatcher", "forest")
    feeder(s, "invertebrate", "seed", "fish")
    power(s, 0, "Great Crested Flycatcher")
    assert s.players[0].food == [1, 0, 0, 0, 0] and len(s.feeder) == 2
    feeder(s, "seed", "fish")                           # not available: nothing happens
    power(s, 0, "Great Crested Flycatcher")
    assert s.players[0].food == [1, 0, 0, 0, 0] and len(s.feeder) == 2
    feeder(s, "fish", "fish")                           # ruling 20190117: may reroll when all dice match
    power(s, 0, "Great Crested Flycatcher", ("keep",))
    assert s.players[0].food == [1, 0, 0, 0, 0] and s.feeder == [F["fish"]] * 2
    s.pend = None
    s.stack = [("steps", 0, bird("Great Crested Flycatcher"),
                load_db().birds[bird("Great Crested Flycatcher")].steps, 0, ())]
    rules.run(s)
    assert opts(s) == [("keep",), ("reroll",)]
    drive(s, ("reroll",))
    assert len(s.feeder) + s.players[0].food[0] - 1 in (4, 5)


@template("gain_feeder_either_if_available", "Indigo Bunting")
def test_gain_feeder_either_if_available():
    s = fresh()
    put(s, 0, "Indigo Bunting", "forest")
    feeder(s, "invertebrate", "fruit", "seed")
    power(s, 0, "Indigo Bunting", ("die", F["fruit"], F["fruit"]))
    assert s.players[0].food == [0, 0, 0, 1, 0]
    assert sorted(s.feeder) == [F["invertebrate"], F["seed"]]


@template("gain_feeder_may_cache", "Blue Jay")
def test_gain_feeder_may_cache():
    s = fresh()
    put(s, 0, "Blue Jay", "forest")
    feeder(s, "seed", "fish")
    power(s, 0, "Blue Jay", ("cache",))                 # rulings 20190901, 20200423: caching is optional
    assert slot(s, 0, "Blue Jay")[2] == 1 and s.players[0].food == [0, 0, 0, 0, 0]
    feeder(s, "seed", "fish")
    power(s, 0, "Blue Jay", ("keep",))
    assert slot(s, 0, "Blue Jay")[2] == 1 and s.players[0].food == [0, 1, 0, 0, 0]


@template("move_if_rightmost", "Bewick's Wren")
def test_move_if_rightmost():
    s = fresh()
    other, = plain(1, nest="bowl")
    put(s, 0, "Bewick's Wren", "forest", eggs=2)
    # Ruling 20220521a: it may move from any column as long as nothing is to its right.
    power(s, 0, "Bewick's Wren", ("habitat", H["grassland"]))
    assert s.players[0].board[H["forest"]] == []
    assert s.players[0].board[H["grassland"]] == [[bird("Bewick's Wren"), 2, 0, 0]]
    put(s, 0, other, "grassland")                       # now a bird is to its right
    assert not can(s, 0, "Bewick's Wren")
    power(s, 0, "Bewick's Wren")                        # ruling 20260319: the power fizzles
    assert rules.find(s.players[0], bird("Bewick's Wren"))[0] == H["grassland"]


@template("lay_any", "Baird's Sparrow")
def test_lay_any():
    s = fresh()
    other, = plain(1, nest="cavity")
    put(s, 0, "Baird's Sparrow", "grassland")
    put(s, 0, other, "forest")
    power(s, 0, "Baird's Sparrow", ("bird", bird(other)))
    assert slot(s, 0, other)[1] == 1 and slot(s, 0, "Baird's Sparrow")[1] == 0


@template("lay_this", "Mourning Dove")
def test_lay_this():
    s = fresh()
    put(s, 0, "Mourning Dove", "grassland")
    limit = load_db().by_name["Mourning Dove"].egg_limit
    for expected in list(range(1, limit + 1)) + [limit]:   # stops at the egg limit
        power(s, 0, "Mourning Dove")
        assert slot(s, 0, "Mourning Dove")[1] == expected


@template("look_at_deck_tuck_if_small", "Barred Owl")
def test_look_at_deck_tuck_if_small():
    s = fresh()
    put(s, 0, "Barred Owl", "forest")
    small, = pick(lambda b: b.wingspan < 75)
    large, = pick(lambda b: b.wingspan >= 75, exclude=["Barred Owl"])
    top(s, small, large)
    power(s, 0, "Barred Owl")
    assert slot(s, 0, "Barred Owl")[3] == 1 and s.tucked == [bird(small)]
    assert s.pinkq == [(rules.T_PREDATOR, 0, 0)]        # rulings 20200522, 20231229: it succeeded
    s.pinkq = []
    power(s, 0, "Barred Owl")
    assert slot(s, 0, "Barred Owl")[3] == 1 and s.discard == [bird(large)] and s.pinkq == []


@template("fewest_gain_die", "Hermit Thrush")
def test_fewest_gain_die():
    s = fresh(3)
    other, = plain(1, nest="bowl")
    put(s, 0, "Hermit Thrush", "forest")
    put(s, 2, other, "forest")
    feeder(s, "fish", "seed")
    # Ruling 20230412: zero birds counts as fewest, so only player 1 gains.
    power(s, 0, "Hermit Thrush", ("die", F["fish"], F["fish"]))
    assert [pl.food[F["fish"]] for pl in s.players] == [0, 1, 0]


@template("fewest_draw", "American Bittern")
def test_fewest_draw():
    s = fresh(2)
    put(s, 0, "American Bittern", "wetland")
    d, = top(s, "Mallard")
    power(s, 0, "American Bittern")                     # ruling 20220305: player 1 has zero, the fewest
    assert hands(s) == [[], [d]]


@template("repeat_predator", "Hooded Merganser")
def test_repeat_predator():
    s = fresh()
    put(s, 0, "Barred Owl", "wetland")
    put(s, 0, "Carolina Chickadee", "wetland")
    put(s, 0, "Hooded Merganser", "wetland")
    small, = pick(lambda b: b.wingspan < 75)
    top(s, small)
    # Ruling 20260111: only a predator in the same habitat can be repeated, so the choice is forced.
    assert rules.repeat_targets(s, 0, bird("Hooded Merganser"), True, ()) == [("bird", bird("Barred Owl"))]
    power(s, 0, "Hooded Merganser")
    assert slot(s, 0, "Barred Owl")[3] == 1 and slot(s, 0, "Hooded Merganser")[3] == 0


@template("repeat_brown", "Gray Catbird")
def test_repeat_brown():
    s = fresh()
    coot = put(s, 0, "American Coot", "wetland")
    cat = put(s, 0, "Gray Catbird", "wetland")
    chick = put(s, 0, "Carolina Chickadee", "wetland")
    c, = hand(s, 0, "Mallard")
    s.pend = None
    s.stack = [("steps", 0, cat, load_db().birds[cat].steps, 0, ())]
    rules.run(s)
    # Ruling 20190127: birds to the left or the right may be repeated.
    assert set(opts(s)) == {("bird", coot), ("bird", chick)}
    drive(s, ("bird", coot))
    assert not s.stack
    # Ruling 20200108: the tucked card goes behind the repeated bird, not this one.
    assert slot(s, 0, "American Coot")[3] == 1 and slot(s, 0, "Gray Catbird")[3] == 0
    assert len(s.players[0].hand) == 1 and c not in s.players[0].hand


def test_repeat_power_cannot_loop():
    s = fresh()
    cat = put(s, 0, "Gray Catbird", "forest")
    mock = put(s, 0, "Northern Mockingbird", "forest")
    s.pend = None
    s.stack = [("steps", 0, cat, load_db().birds[cat].steps, 0, ())]
    rules.run(s)       # catbird -> mockingbird (forced) -> nothing left to repeat
    assert s.pend is None and not s.stack


@template("roll_dice_cache", "Barn Owl")
def test_roll_dice_cache():
    s = fresh()
    put(s, 0, "Barn Owl", "forest")
    feeder(s, "fish", "fish", "fish", "fish", "fish")   # no dice outside the feeder: nothing to roll
    power(s, 0, "Barn Owl")
    assert slot(s, 0, "Barn Owl")[2] == 0
    for seed in range(12):
        s.rng = seed
        feeder(s, "fish")
        probe = s.copy()
        rolled = [rand_below(probe, 6) for _ in range(4)]
        before = slot(s, 0, "Barn Owl")[2]
        s.pinkq = []
        power(s, 0, "Barn Owl")
        hit = F["rodent"] in rolled
        assert slot(s, 0, "Barn Owl")[2] == before + (1 if hit else 0)
        assert bool(s.pinkq) == hit and s.feeder == [F["fish"]]


@template("trade_food", "Green Heron")
def test_trade_food():
    s = fresh()
    put(s, 0, "Green Heron", "wetland")
    assert not can(s, 0, "Green Heron")
    food(s, 0, fish=1)
    s.pend = None
    s.stack = [("steps", 0, bird("Green Heron"), load_db().birds[bird("Green Heron")].steps, 0, ())]
    rules.run(s)
    # Ruling 20200719: the food may not be traded for the same type.
    assert ("food", F["fish"]) not in opts(s) and len(opts(s)) == 4
    drive(s, ("food", F["rodent"]))
    assert s.players[0].food == [0, 0, 0, 0, 1]


@template("tuck_hand_then_draw", "American Coot")
def test_tuck_hand_then_draw():
    s = fresh()
    put(s, 0, "American Coot", "wetland")
    assert not can(s, 0, "American Coot")               # nothing in hand to tuck
    c, = hand(s, 0, "Mallard")
    d, = top(s, "Osprey")
    power(s, 0, "American Coot")
    assert slot(s, 0, "American Coot")[3] == 1 and s.players[0].hand == [d] and s.tucked == [c]


@template("tuck_hand_then_gain", "Cedar Waxwing")
def test_tuck_hand_then_gain():
    s = fresh()
    put(s, 0, "Cedar Waxwing", "forest")
    a, b = hand(s, 0, "Mallard", "Osprey")
    power(s, 0, "Cedar Waxwing", ("card", b))
    assert s.players[0].hand == [a] and s.players[0].food == [0, 0, 0, 1, 0]
    assert slot(s, 0, "Cedar Waxwing")[3] == 1


@template("tuck_hand_then_gain_either", "Pygmy Nuthatch")
def test_tuck_hand_then_gain_either():
    s = fresh()
    put(s, 0, "Pygmy Nuthatch", "forest")
    hand(s, 0, "Mallard")
    power(s, 0, "Pygmy Nuthatch", ("food", F["seed"]))
    assert s.players[0].food == [0, 1, 0, 0, 0] and slot(s, 0, "Pygmy Nuthatch")[3] == 1


@template("tuck_hand_then_lay_any", "White-Throated Swift")
def test_tuck_hand_then_lay_any():
    s = fresh()
    other, = plain(1, nest="bowl")
    put(s, 0, "White-Throated Swift", "grassland")
    put(s, 0, other, "forest")
    hand(s, 0, "Mallard")
    power(s, 0, "White-Throated Swift", ("bird", bird(other)))
    assert slot(s, 0, other)[1] == 1 and slot(s, 0, "White-Throated Swift")[3] == 1


@template("tuck_hand_then_may_lay_this", "Bushtit")
def test_tuck_hand_then_may_lay_this():
    s = fresh()
    put(s, 0, "Bushtit", "forest")
    hand(s, 0, "Mallard", "Osprey", "Killdeer")
    power(s, 0, "Bushtit", ("card", bird("Mallard")), ("lay",))
    assert slot(s, 0, "Bushtit")[1:] == [1, 0, 1]
    power(s, 0, "Bushtit", ("card", bird("Osprey")), ("skip",))
    assert slot(s, 0, "Bushtit")[1:] == [1, 0, 2]
    # Ruling 20190203: a full bird may still tuck; it just cannot take the egg.
    slot(s, 0, "Bushtit")[1] = load_db().by_name["Bushtit"].egg_limit
    power(s, 0, "Bushtit")
    assert slot(s, 0, "Bushtit")[3] == 3 and s.players[0].hand == []


# ---------------------------------------------------------------- pink powers

def _play(s, p, name, habitat):
    """Player p plays a bird; payment choices take the first option. Stops at the next real decision
    owned by another player, or when the turn ends."""
    cid, = hand(s, p, name)
    s.players[p].food = [3, 3, 3, 3, 3]
    set_turn(s, p)
    drive(s, ("play", cid, H[habitat]))
    while s.pend is not None and s.pend[0] == p and s.turn == p:
        rules.resume(s, s.pend[2][0])
    return cid


@template("pink_play_bird_gain_supply", "Belted Kingfisher")
def test_pink_play_bird_gain_supply():
    s = fresh(3)
    king = put(s, 1, "Belted Kingfisher", "wetland")
    _play(s, 2, "Mallard", "wetland")
    assert s.pend[:2] == (1, "activate_power") and opts(s)[0] == ("activate", king)
    drive(s, ("activate", king))
    assert s.players[1].food[F["fish"]] == 1 and s.turn == 0
    # Once between turns: player 0 now plays in the wetland before player 1 has had a turn.
    _play(s, 0, "American Coot", "wetland")
    assert s.turn == 1 and s.pend[1] == "action" and s.players[1].food[F["fish"]] == 1
    # At the start of player 1's own turn the power is ready again.
    assert s.players[1].pink_used == ()


def test_pink_play_bird_ignores_other_habitats_and_moves():
    # Ruling 20200710: only a bird played in the named habitat triggers it; a moved bird does not.
    s = fresh(2)
    put(s, 1, "Belted Kingfisher", "wetland")
    wren = put(s, 0, "Bewick's Wren", "forest")
    _play(s, 0, "Killdeer", "grassland")
    assert s.turn == 1 and s.players[1].food[F["fish"]] == 0
    feeder(s, "fish", "seed", "fruit")
    set_turn(s, 0)
    drive(s, ("food",), ("die", F["fish"], F["fish"]), ("activate", wren), ("habitat", H["wetland"]))
    assert s.turn == 1 and s.players[1].food[F["fish"]] == 0
    assert rules.find(s.players[0], wren)[0] == H["wetland"]


@template("pink_play_bird_tuck", "Horned Lark")
def test_pink_play_bird_tuck():
    s = fresh(2)
    lark = put(s, 1, "Horned Lark", "grassland")
    c, = hand(s, 1, "Osprey")
    _play(s, 0, "Killdeer", "grassland")
    assert s.pend[:2] == (1, "activate_power")
    drive(s, ("activate", lark))
    assert slot(s, 1, "Horned Lark")[3] == 1 and s.players[1].hand == [] and c in s.tucked


@template("pink_gain_food_cache", "Loggerhead Shrike")
def test_pink_gain_food_cache():
    s = fresh(2)
    shrike = put(s, 1, "Loggerhead Shrike", "grassland")
    feeder(s, "rodent", "fish", "seed")
    set_turn(s, 0)
    drive(s, ("food",), ("die", F["rodent"], F["rodent"]))
    assert s.pend[:2] == (1, "activate_power")
    drive(s, ("activate", shrike))
    assert slot(s, 1, "Loggerhead Shrike")[2] == 1 and s.turn == 1
    # No rodent gained by the core action: no trigger.
    feeder(s, "rodent", "fish", "seed")
    s.players[1].pink_used = ()
    turn(s, 0, ("food",), ("die", F["fish"], F["fish"]))
    assert slot(s, 1, "Loggerhead Shrike")[2] == 1


def test_shrike_ignores_rodents_from_bird_powers():
    # Rulings 20190405, 20191218, 20260708: only the core benefit of the "gain food" action counts.
    s = fresh(2)
    put(s, 1, "Loggerhead Shrike", "grassland")
    red = put(s, 0, "American Redstart", "forest")
    feeder(s, "fish", "rodent", "seed", "seed")
    set_turn(s, 0)
    drive(s, ("food",), ("die", F["fish"], F["fish"]), ("activate", red), ("die", F["rodent"], F["rodent"]))
    assert s.turn == 1 and slot(s, 1, "Loggerhead Shrike")[2] == 0
    assert s.players[0].food[F["rodent"]] == 1


@template("pink_lay_eggs_lay_nest", "Bronzed Cowbird")
def test_pink_lay_eggs_lay_nest():
    s = fresh(2)
    bowl, = plain(1, nest="bowl")
    cow = put(s, 1, "Bronzed Cowbird", "grassland")
    put(s, 1, bowl, "forest")
    set_turn(s, 0)
    drive(s, ("eggs",))                                  # player 0 has no birds; the action still counts
    assert s.pend[:2] == (1, "activate_power")
    drive(s, ("activate", cow))
    # Ruling 20190718: the cowbird itself holds no eggs, so the egg goes on the bowl bird.
    assert slot(s, 1, bowl)[1] == 1 and slot(s, 1, "Bronzed Cowbird")[1] == 0


@template("pink_lay_eggs_lay_other_nest", "American Avocet")
def test_pink_lay_eggs_lay_other_nest():
    s = fresh(2)
    star, = plain(1, nest="wild")
    avocet = put(s, 1, "American Avocet", "wetland")
    set_turn(s, 0)
    drive(s, ("eggs",))
    assert s.turn == 1                                   # "another bird": none yet, so it is not offered
    put(s, 1, star, "forest")
    set_turn(s, 0)
    drive(s, ("eggs",), ("activate", avocet))
    # Ruling 20190921: a star nest counts as a ground nest.
    assert slot(s, 1, star)[1] == 1 and slot(s, 1, "American Avocet")[1] == 0


def test_pink_lay_eggs_ignores_eggs_from_powers():
    # Ruling 20200411: only the "lay eggs" action triggers it, not eggs laid by a card power.
    s = fresh(2)
    bowl, = plain(1, nest="bowl")
    put(s, 1, "Bronzed Cowbird", "grassland")
    put(s, 1, bowl, "forest")
    dove = put(s, 0, "Mourning Dove", "wetland")
    top(s, "Mallard")
    turn(s, 0, ("cards",), ("activate", dove))
    assert slot(s, 1, bowl)[1] == 0 and slot(s, 0, "Mourning Dove")[1] == 1


@template("pink_predator_gain_die", "Black Vulture")
def test_pink_predator_gain_die():
    s = fresh(2)
    vulture = put(s, 1, "Black Vulture", "forest")
    owl = put(s, 0, "Barred Owl", "forest")
    chick = put(s, 0, "Carolina Chickadee", "forest")    # left of nothing: activated first (rightmost)
    small, = pick(lambda b: b.wingspan < 75, exclude=["Carolina Chickadee"])
    top(s, small)
    feeder(s, "fish", "seed", "fruit", "rodent")
    set_turn(s, 0)
    drive(s, ("food",), ("die", F["fish"], F["fish"]), ("die", F["seed"], F["seed"]))
    drive(s, ("activate", chick), ("activate", owl))
    # Rulings 20220209, 20231030: it resolves as soon as the predator has finished.
    assert s.pend[:2] == (1, "activate_power") and s.turn == 0
    drive(s, ("activate", vulture), ("die", F["fruit"], F["fruit"]))
    assert s.players[1].food[F["fruit"]] == 1 and s.turn == 1


# ---------------------------------------------------------------- white powers

@template("draw_bonus_keep", "Atlantic Puffin")
def test_draw_bonus_keep():
    s = fresh()
    put(s, 0, "Atlantic Puffin", "wetland")
    a, b = s.bonus_deck[-1], s.bonus_deck[-2]
    held = list(s.players[0].bonus)
    power(s, 0, "Atlantic Puffin", ("bonus", b))
    assert s.players[0].bonus == held + [b] and s.bonus_discard[-1] == a


@template("draw_tray_all", "Brant")
def test_draw_tray_all():
    s = fresh()
    put(s, 0, "Brant", "wetland")
    cards = tray(s, "Mallard", "Osprey", "Killdeer")
    power(s, 0, "Brant")
    assert s.players[0].hand == cards and s.tray == []


@template("gain_all_feeder", "Bald Eagle")
def test_gain_all_feeder():
    s = fresh()
    put(s, 0, "Bald Eagle", "wetland")
    feeder(s, "fish", "seed", "fish", "rodent", "invertebrate/seed")
    power(s, 0, "Bald Eagle")
    assert s.players[0].food == [0, 0, 2, 0, 0] and len(s.feeder) == 3
    put(s, 0, "Northern Flicker", "forest")
    feeder(s, "invertebrate", "invertebrate/seed", "fish")
    power(s, 0, "Northern Flicker")
    assert s.players[0].food == [2, 0, 2, 0, 0] and s.feeder == [F["fish"]]


@template("lay_each_nest", "Bobolink")
def test_lay_each_nest():
    s = fresh()
    ground, = plain(1, nest="ground", exclude=["Bobolink"])
    star, = plain(1, nest="wild")
    bowl, = plain(1, nest="bowl")
    for name in ("Bobolink", ground, star, bowl):
        put(s, 0, name, "grassland")
    power(s, 0, "Bobolink")
    expected = {"Bobolink": 1 if load_db().by_name["Bobolink"].nest == "ground" else 0, ground: 1, star: 1, bowl: 0}
    assert {n: slot(s, 0, n)[1] for n in expected} == expected


@template("play_additional_same_habitat", "House Wren")
def test_play_additional_same_habitat():
    s = fresh()
    wren = put(s, 0, "House Wren", "grassland")
    both, = pick(lambda b: b.habitats == (0, 1) and b.timing != "white" and not b.either, exclude=["House Wren"])
    cost = load_db().by_name[both].total_cost
    cid, = hand(s, 0, both)
    s.players[0].food = [3, 3, 3, 3, 3]
    slot(s, 0, "House Wren")[1] = 1
    s.pend = None
    s.stack = [("steps", 0, wren, load_db().birds[wren].steps, 0, ())]
    rules.run(s)
    # Ruling 20190128: only House Wren's own habitat is offered, though the bird could also live in the forest.
    assert opts(s) == [("skip",), ("play", cid, H["grassland"])]
    drive(s, ("play", cid, H["grassland"]))
    first_until(s, "none")
    # Ruling 20201230: the normal cost includes the egg for the second column.
    assert [x[0] for x in s.players[0].board[H["grassland"]]] == [wren, cid]
    assert slot(s, 0, "House Wren")[1] == 0 and sum(s.players[0].food) == 15 - cost


@template("play_additional_in_habitat", "Great Blue Heron")
def test_play_additional_in_habitat():
    s = fresh()
    heron = put(s, 0, "Great Blue Heron", "wetland")
    cid, = hand(s, 0, "Great Egret")
    s.players[0].food = [3, 3, 3, 3, 3]
    assert rules.play_options(s, 0, H["wetland"]) == []   # no egg for the second column
    slot(s, 0, "Great Blue Heron")[1] = 1
    s.pend = None
    s.stack = [("steps", 0, heron, load_db().birds[heron].steps, 0, ())]
    rules.run(s)
    drive(s, ("play", cid, H["wetland"]))
    # Ruling 20190309: the bird played this way may use its own "play another bird" power.
    assert first_until(s, "activate_power") and opts(s)[0] == ("activate", cid)


def test_draft_players_plus_one_override():
    assert template_of("American Oystercatcher") == "override:draft_players_plus_one"
    COVERED["override:draft_players_plus_one"] = "test_draft_players_plus_one_override"
    s = fresh(2)
    put(s, 0, "American Oystercatcher", "wetland")
    t, = tray(s, "Mallard")
    a, b = top(s, "Osprey", "Killdeer")
    # Rulings 20200617, 20201010: all players+1 cards are drawn, from the tray and/or the deck.
    s.pend = None
    oy = bird("American Oystercatcher")
    s.stack = [("steps", 0, oy, load_db().birds[oy].steps, 0, ())]
    rules.run(s)
    drive(s, ("tray", t))        # the tray is now empty, so the other two come from the deck
    # Ruling 20250603: the cards are revealed; the owner picks first, then clockwise.
    assert s.pend[:2] == (0, "draft_pick") and set(opts(s)) == {("card", t), ("card", a), ("card", b)}
    drive(s, ("card", a))
    assert s.pend[0] == 1
    drive(s, ("card", t))
    assert not s.stack and s.players[0].hand == [a, b] and s.players[1].hand == [t]


def test_every_template_has_a_test():
    effects = json.loads((pathlib.Path(build.__file__).parent / "effects.json").read_text())
    used = {e["template"] for e in effects.values()}
    COVERED.setdefault("override:draft_players_plus_one", "test_draft_players_plus_one_override")
    assert used - set(COVERED) == set()


@pytest.mark.parametrize("cid", load_db().bird_ids)
def test_every_bird_power_runs_and_conserves_cards(cid):
    """Each of the 174 powers runs to completion on a busy board without losing or duplicating a card."""
    d = load_db()
    b = d.birds[cid]
    if not b.spec:
        return
    for seed in (1, 2, 3):
        s = fresh(3, seed)
        for p in range(3):
            for h, names in enumerate((["Barred Owl", "Carolina Chickadee"], ["Killdeer", "Mourning Dove"],
                                       ["Mallard", "American Coot"])):
                if p == 0:
                    for n in names:
                        if bird(n) != cid:
                            put(s, 0, n, ("forest", "grassland", "wetland")[h], eggs=1)
            s.players[p].food = [2, 2, 2, 2, 2]
        s.players[0].board[b.habitats[0]].append([cid, 1 if b.egg_limit else 0, 0, 0])
        s.deck.remove(cid)
        for p in range(3):
            s.players[p].hand = [s.deck.pop() for _ in range(3)]
        s.tray = [s.deck.pop() for _ in range(3)]
        s.pend = None
        s.stack = [("steps", 0, cid, b.steps, 0, ())]
        rules.run(s)
        steps = 0
        while s.pend is not None:
            rules.resume(s, s.pend[2][(seed + steps) % len(s.pend[2])])
            steps += 1
            assert steps < 100
        assert sorted(all_cards(s)) == sorted(d.bird_ids)
        for pl in s.players:
            assert min(pl.food) >= 0
            for row in pl.board:
                for x in row:
                    assert 0 <= x[1] <= d.birds[x[0]].egg_limit and x[2] >= 0 and x[3] >= 0
