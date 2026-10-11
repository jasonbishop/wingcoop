"""Effect primitives: how each step of a bird power changes the game.

Every function takes (state, owner, bird id, step, chain). It either changes the
state at once or pushes frames for the choices involved. `state.did` records
whether a step actually happened, for "if you do" and "discard X to ..." powers.
"""
from . import rules as R


def x_gain_food(s, p, c, step, chain):
    who = step.get("who", "self")
    n = step["n"]
    food = step["food"]
    st = s.stack
    count = len(s.players)
    if step["from"] == "supply":
        if who == "all":
            for off in range(count):
                j = (p + off) % count
                s.players[j].food[food[0]] += n
                R.emit(s, "food_gained", p=j, food=food[0], n=n, source="supply")
        else:
            st.append(("gain_supply", p, food, n, 1 if step.get("other") else 0))
        return
    nn = -1 if n == "all" else n
    decline = 1 if step.get("may_decline") else 0
    if who == "self":
        st.append(("gain_feeder", p, food, nn, c if step.get("may_cache") else -1, decline))
    elif who == "each_from_feeder_in_order":
        st.append(("each_feeder", p, nn, decline))
    else:  # fewest_in_habitat; rulings 20220305 and 20230412: zero birds counts as fewest
        h = step["habitat"]
        fewest = min(len(q.board[h]) for q in s.players)
        for off in reversed(range(count)):
            j = (p + off) % count
            if len(s.players[j].board[h]) == fewest:
                st.append(("gain_feeder", j, food, nn, -1, decline))


_SOURCES = {"any": 0, "deck": 1, "tray": 2}


def x_draw_cards(s, p, c, step, chain):
    who = step.get("who", "self")
    src = _SOURCES[step["from"]]
    n = 0 if step["n"] == "all" else step["n"]
    count = len(s.players)
    if who == "self":
        if step.get("discard_eot") and (s.deck or s.discard or s.tray):
            s.eot_discard += step["discard_eot"]
        s.stack.append(("draw", p, src, n))
    elif who == "all":
        for off in reversed(range(count)):
            s.stack.append(("draw", (p + off) % count, src, n))
    else:
        h = step["habitat"]
        fewest = min(len(q.board[h]) for q in s.players)
        for off in reversed(range(count)):
            j = (p + off) % count
            if len(s.players[j].board[h]) == fewest:
                s.stack.append(("draw", j, src, n))


def x_lay_eggs(s, p, c, step, chain):
    on = step["on"]
    n = step["n"]
    birds = s.cfg.db.birds
    pl = s.players[p]
    if on == "this":
        if step.get("optional"):
            s.stack.append(("opt_lay", p, c, n))
            return
        slot = R.find(pl, c)[2]
        k = min(n, birds[c].egg_limit - slot[1])
        s.did = k > 0
        if k > 0:
            slot[1] += k
            R.emit(s, "eggs_laid", p=p, bird=c, n=k)
        return
    nest = step.get("nest")
    if on == "each":
        for row in pl.board:
            for x in row:
                b = birds[x[0]]
                if (b.nest == nest or b.nest == "wild") and x[1] < b.egg_limit:
                    k = min(n, b.egg_limit - x[1])
                    x[1] += k
                    R.emit(s, "eggs_laid", p=p, bird=x[0], n=k)
        return
    decline = 1 if step.get("may_decline") else 0
    if step.get("who", "self") == "all":
        count = len(s.players)
        s.memo = -1
        for off in reversed(range(count)):
            j = (p + off) % count
            s.stack.append(("lay", j, n, nest, -1, decline | (2 if j == p else 0)))
    else:
        excl = c if step.get("other_than_this") else -1
        s.stack.append(("lay", p, n, nest, excl, decline | (4 if step.get("different_bird") else 0)))


def x_cache_food(s, p, c, step, chain):
    R.find(s.players[p], c)[2][2] += step["n"]
    s.did = True
    R.emit(s, "food_cached", p=p, bird=c, food=step["food"], n=step["n"])


def x_tuck(s, p, c, step, chain):
    if step["from"] == "hand":
        s.stack.append(("tuck_hand", p, c, step["n"]))
        return
    slot = R.find(s.players[p], c)[2]
    s.did = False
    for _ in range(step["n"]):
        card = R.draw_from_deck(s)
        if card < 0:
            break
        s.tucked.append(card)
        slot[3] += 1
        s.did = True
        R.emit(s, "card_tucked", p=p, bird=c, source="deck")


def x_draw_bonus_keep(s, p, c, step, chain):
    cards = []
    for _ in range(step["draw"]):
        if not s.bonus_deck:
            if not s.bonus_discard:
                break
            s.bonus_deck = s.bonus_discard
            s.bonus_discard = []
            R.shuffle(s, s.bonus_deck)
        cards.append(s.bonus_deck.pop())
    if cards:
        s.stack.append(("bonus_keep", p, tuple(cards)))


def x_discard_to_gain(s, p, c, step, chain):
    cost = step["cost"]
    s.stack.append(("then", p, c, step["then"], chain))
    if cost["what"] == "egg":
        s.stack.append(("cost_egg", p, c if cost["from"] == "other_birds" else -1))
    elif cost["food"] is None:
        s.stack.append(("cost_food", p))
    else:
        # Ruling 20220213a: a power's food cost needs the actual food; no substitutions.
        f0 = cost["food"][0]
        food = s.players[p].food
        s.did = food[f0] > 0
        if s.did:
            food[f0] -= 1
            s.last_food = f0
            R.emit(s, "food_spent", p=p, food=[int(i == f0) for i in range(5)], why="power_cost")


def x_if_then(s, p, c, step, chain):
    s.stack.append(("then", p, c, step["then"], chain))
    cond = step["if"]
    EXEC[cond["op"]](s, p, c, cond, chain)


def x_roll_dice(s, p, c, step, chain):
    k = 5 - len(s.feeder)
    faces = [R.rand_below(s, 6) for _ in range(k)]
    s.did = step["food"] in faces
    R.emit(s, "predator", p=p, bird=c, kind="roll", dice=faces, success=s.did)
    if s.did:
        # Rulings 20200522 and 20231229: the predator succeeds when it finds its prey.
        s.pinkq.append((R.T_PREDATOR, p, 0))
        s.stack.append(("steps", p, c, step["then"], 0, chain))


def x_look_at_deck_card(s, p, c, step, chain):
    card = R.draw_from_deck(s)
    if card < 0:
        s.did = False
        return
    s.did = s.cfg.db.birds[card].wingspan < step["max_wingspan"]
    R.emit(s, "predator", p=p, bird=c, kind="look", card=card, success=s.did)
    if s.did:
        s.tucked.append(card)
        R.find(s.players[p], c)[2][3] += 1
        s.pinkq.append((R.T_PREDATOR, p, 0))
        R.emit(s, "card_tucked", p=p, bird=c, card=card, source="deck")
    else:
        s.discard.append(card)


def x_repeat_power(s, p, c, step, chain):
    s.stack.append(("repeat", p, c, 1 if step["filter"] == "predator" else 0, chain))


def x_play_additional_bird(s, p, c, step, chain):
    h = step["habitat"]
    if h == "this":  # ruling 20190128: the same habitat this bird was played in
        h = R.find(s.players[p], c)[0]
    s.stack.append(("extra_play", p, h))


def x_move_bird(s, p, c, step, chain):
    s.stack.append(("move", p, c))


def x_draft_cards(s, p, c, step, chain):
    s.stack.append(("draft", p, (), len(s.players) + 1))


EXEC = {
    "gain_food": x_gain_food, "draw_cards": x_draw_cards, "lay_eggs": x_lay_eggs, "cache_food": x_cache_food,
    "tuck": x_tuck, "draw_bonus_keep": x_draw_bonus_keep, "discard_to_gain": x_discard_to_gain,
    "if_then": x_if_then, "roll_dice_not_in_feeder": x_roll_dice, "look_at_deck_card": x_look_at_deck_card,
    "repeat_power": x_repeat_power, "play_additional_bird": x_play_additional_bird, "move_bird": x_move_bird,
    "draft_cards": x_draft_cards,
}


def feasible(s, p, c, b):
    """False when a power could not do anything right now, so the owner is not asked about it."""
    step = b.steps[0]
    op = step["op"]
    pl = s.players[p]
    if op == "if_then":
        step = step["if"]
        op = step["op"]
    if op == "tuck":
        return step["from"] != "hand" or bool(pl.hand)
    if op == "discard_to_gain":
        cost = step["cost"]
        if cost["what"] == "egg":
            excl = c if cost["from"] == "other_birds" else -1
            return any(x[1] > 0 and x[0] != excl for row in pl.board for x in row)
        if cost["food"] is None:
            return any(pl.food)
        return pl.food[cost["food"][0]] > 0
    if op == "move_bird":
        return bool(R.move_targets(s, p, c))
    if op == "repeat_power":
        return bool(R.repeat_targets(s, p, c, step["filter"] == "predator", ()))
    if op == "lay_eggs" and step["on"] == "any" and step.get("who", "self") == "self":
        nest = step.get("nest")
        excl = c if step.get("other_than_this") else -1
        birds = s.cfg.db.birds
        for row in pl.board:
            for x in row:
                bb = birds[x[0]]
                if x[1] < bb.egg_limit and x[0] != excl and (nest is None or bb.nest == nest or bb.nest == "wild"):
                    return True
        return False
    return True
