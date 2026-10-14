"""The rules engine: a deterministic stack machine.

`state.stack` holds frames (immutable tuples). `run()` executes the top frame's
handler until a frame needs a choice, at which point it sets `state.pend` to
(player, kind, options) and returns. `resume()` feeds the choice back to that
frame. Decisions with a single legal option are resolved without asking.

Options are tuples whose first element is a tag, for example ("play", bird id,
habitat) or ("die", face, food).
"""
from itertools import combinations

from .cards import ALL_FOODS, RODENT, db
from . import effects as fx
from .scoring import goal_count, score_goal_counts, breakdown
from .state import GROUP, OVER, PRE_ROUND, ROUND_END, SETUP, TURNS, rand_below, shuffle

EGG_COST = (0, 1, 1, 2, 2)
# Base gain of each habitat action, by the number of birds already in the row.
BASE_GAIN = ((1, 1, 2, 2, 3, 3), (2, 2, 3, 3, 4, 4), (1, 1, 2, 2, 3, 3))
ACTIONS_PER_ROUND = (8, 7, 6, 5)
ACTION_TAGS = ("food", "eggs", "cards")

# Pink trigger types queued in state.pinkq as (type, acting player, parameter).
T_PLAY, T_LAY, T_PREDATOR, T_FOOD = range(4)
TRIGGER_TYPE = {
    "on_other_player_play_bird_in": T_PLAY,
    "on_other_player_lay_eggs": T_LAY,
    "on_other_player_predator_success": T_PREDATOR,
    "on_other_player_gain_food": T_FOOD,
}


class IllegalChoice(ValueError):
    pass


def emit(s, event, /, **data):
    ev = s.events
    if ev is not None:
        data["e"] = event
        ev.append(data)
    hooks = s.cfg.event_plugins
    if hooks:
        for pg in hooks:
            pg.on_event(s, event, data)


# ---------------------------------------------------------------- helpers

def find(pl, cid):
    """Locate a bird on a player's mat: (habitat, index, slot) or None."""
    b = pl.board
    for h in (0, 1, 2):
        row = b[h]
        for i in range(len(row)):
            if row[i][0] == cid:
                return h, i, row[i]
    return None


def draw_from_deck(s):
    """Top card of the deck, reshuffling the discard pile if the deck is empty. -1 if no cards."""
    deck = s.deck
    if not deck:
        if not s.discard:
            return -1
        s.deck = deck = s.discard
        s.discard = []
        shuffle(s, deck)
        emit(s, "deck_reshuffled", cards=len(deck), deck=list(deck))
    return deck.pop()


def refill_tray(s):
    tray = s.tray
    start = len(tray)
    while len(tray) < 3:
        if not s.deck and len(tray) > start:
            # The deck runs out part way: report the cards drawn so far before the reshuffle event.
            emit(s, "tray_refill", tray=list(tray))
            start = len(tray)
        c = draw_from_deck(s)
        if c < 0:
            break
        tray.append(c)
    emit(s, "tray_refill", tray=list(tray))


def reroll_feeder(s, why):
    s.feeder = [rand_below(s, 6) for _ in range(5)]
    emit(s, "feeder_reset", dice=list(s.feeder), why=why)


def take_die(s, p, face, food):
    s.feeder.remove(face)
    s.players[p].food[food] += 1
    if food == RODENT and s.food_action == p:
        s.rodent = True
    emit(s, "die_taken", p=p, face=face, food=food)
    if not s.feeder:
        reroll_feeder(s, "empty")


def total_eggs(pl):
    n = 0
    for row in pl.board:
        for x in row:
            n += x[1]
    return n


def can_afford(have, b):
    if b.total_cost == 0:
        return True
    cost = b.cost
    tot = have[0] + have[1] + have[2] + have[3] + have[4]
    if b.either:
        if tot >= 2:
            return True
        for i in ALL_FOODS:
            if cost[i] and have[i]:
                return True
        return False
    direct = 0
    for i in ALL_FOODS:
        c = cost[i]
        if c:
            h = have[i]
            direct += h if h < c else c
    return tot - direct >= b.wild + 2 * (b.total_cost - b.wild - direct)


def _multisets(avail, k):
    """Every way to take k food tokens from the available counts."""
    out = []

    def rec(i, left, cur):
        if i == 4:
            if left <= avail[4]:
                out.append(tuple(cur + [left]))
            return
        for take in range(min(avail[i], left) + 1):
            rec(i + 1, left - take, cur + [take])

    rec(0, k, [])
    return out


def payments(have, b):
    """Legal ways to pay a bird's food cost, as 5-tuples of food spent.

    Ruling 20200907: any 2 food tokens may stand in for 1 food of a type you
    lack, as often as needed, and only when playing a bird.
    """
    if b.total_cost == 0:
        return [(0, 0, 0, 0, 0)]
    cost = b.cost
    if b.either:
        opts = []
        for i in ALL_FOODS:
            if cost[i] and have[i]:
                v = [0, 0, 0, 0, 0]
                v[i] = 1
                opts.append(tuple(v))
        return opts or _multisets(have, 2)
    direct = [min(have[i], cost[i]) for i in ALL_FOODS]
    missing = b.total_cost - b.wild - sum(direct)
    extra = b.wild + 2 * missing
    if extra == 0:
        return [tuple(direct)]
    rem = [have[i] - direct[i] for i in ALL_FOODS]
    return [tuple(direct[i] + m[i] for i in ALL_FOODS) for m in _multisets(rem, extra)]


def play_options(s, p, only_habitat=None):
    pl = s.players[p]
    birds = s.cfg.db.birds
    food = pl.food
    board = pl.board
    eggs = total_eggs(pl)
    opts = []
    for c in pl.hand:
        b = birds[c]
        if not can_afford(food, b):
            continue
        for h in b.habitats:
            if only_habitat is not None and h != only_habitat:
                continue
            k = len(board[h])
            if k < 5 and eggs >= EGG_COST[k]:
                opts.append(("play", c, h))
    return opts


def push_play(s, p, c, h):
    b = s.cfg.db.birds[c]
    st = s.stack
    st.append(("place", p, c, h))
    n_eggs = EGG_COST[len(s.players[p].board[h])]
    if n_eggs:
        st.append(("pay_eggs", p, n_eggs))
    if b.total_cost:
        st.append(("pay_food", p, c))


def push_group_decision(s, plugin, kind, options):
    s.stack.append(("group", s.cfg.plugins.index(plugin), kind, tuple(options)))


# ---------------------------------------------------------------- game flow

def h_main(s, f):
    ph = s.phase
    n = len(s.players)
    if ph == TURNS:
        p = s.turn
        if s.actions_left[p] == 0:
            s.phase = ROUND_END
            return
        s.players[p].pink_used = ()
        s.eot_discard = 0
        emit(s, "turn_start", p=p, round=s.round, turn_no=s.turn_no)
        s.stack.append(("turn", p, 0))
    elif ph == SETUP:
        i = s.setup_idx
        if i < n:
            s.setup_idx = i + 1
            s.stack.append(("setup", (s.first + i) % n, 0))
        else:
            for pg in s.cfg.plugins:
                pg.on_setup(s)
            s.phase = PRE_ROUND
    elif ph == PRE_ROUND:
        r = s.round
        s.actions_left = [ACTIONS_PER_ROUND[r - 1]] * n
        s.turn = s.first
        s.phase = TURNS
        emit(s, "round_start", round=r, first=s.first, goal=s.goals[r - 1])
        for pg in reversed(s.cfg.plugins):
            pg.before_round(s, r)
    elif ph == ROUND_END:
        end_round(s)
    else:
        s.stack.pop()


def end_round(s):
    n = len(s.players)
    r = s.round
    goal = s.cfg.db.goals[s.goals[r - 1]]
    counts = tuple(goal_count(s, j, goal) for j in range(n))
    ind, delta, info = score_goal_counts(s, counts)
    for j in range(n):
        s.goal_points[j] += ind[j]
    s.group_score += delta
    s.goal_log = s.goal_log + ((r, counts, tuple(ind), delta, info),)
    emit(s, "round_end", round=r, goal=goal.id, counts=list(counts), points=list(ind), group_delta=delta,
         group_score=s.group_score, info=info)
    emit(s, "tray_cleared", birds=list(s.tray))
    s.discard.extend(s.tray)
    s.tray = []
    refill_tray(s)
    s.first = (s.first + 1) % n
    s.round = r + 1
    if r >= 4:
        s.phase = OVER
        s.stack.clear()
        emit(s, "final_scoring", scores=breakdown(s))
    else:
        s.phase = PRE_ROUND


def h_setup(s, f):
    p, stage = f[1], f[2]
    pl = s.players[p]
    if stage == 0:
        hand = pl.hand
        opts = [("keep", tuple(c for i, c in enumerate(hand) if m >> i & 1)) for m in range(1 << len(hand))]
        s.pend = (p, "setup_keep_birds", opts)
    elif stage == 1:
        s.pend = (p, "setup_discard_food", [("discard_food", c) for c in combinations(ALL_FOODS, f[3])])
    else:
        s.pend = (p, "setup_keep_bonus", [("bonus", b) for b in pl.bonus])


def r_setup(s, f, ch):
    p, stage = f[1], f[2]
    pl = s.players[p]
    if stage == 0:
        keep = ch[1]
        s.discard.extend(c for c in pl.hand if c not in keep)
        pl.hand = list(keep)
        emit(s, "setup_kept_birds", p=p, birds=list(keep))
        s.stack[-1] = ("setup", p, 1, len(keep))
    elif stage == 1:
        for i in ch[1]:
            pl.food[i] -= 1
        emit(s, "setup_discarded_food", p=p, food=list(ch[1]))
        s.stack[-1] = ("setup", p, 2)
    else:
        discarded = [b for b in pl.bonus if b != ch[1]]
        s.bonus_discard.extend(discarded)
        pl.bonus = [ch[1]]
        emit(s, "bonus_kept", p=p, bonus=ch[1], discarded=discarded)
        s.stack.pop()


def h_turn(s, f):
    p, stage = f[1], f[2]
    pl = s.players[p]
    if stage == 0:
        opts = play_options(s, p)
        opts.append(("food",))
        opts.append(("eggs",))
        opts.append(("cards",))
        for pg in s.cfg.option_plugins:
            opts.extend(pg.extra_options(s, p, "turn_start"))
        s.pend = (p, "action", opts)
    elif stage == 1:
        s.stack[-1] = ("turn", p, 2)
        if s.pinkq:
            s.stack.append(("pinks", p))
    elif stage == 2:
        if s.eot_discard > 0 and pl.hand:
            s.pend = (p, "discard_card", [("card", c) for c in pl.hand])
        else:
            s.eot_discard = 0
            s.stack[-1] = ("turn", p, 3)
    else:
        opts = []
        for pg in s.cfg.option_plugins:
            opts.extend(pg.extra_options(s, p, "turn_end"))
        if opts:
            s.pend = (p, "end_turn", [("pass",)] + opts)
        else:
            finish_turn(s, p)


def finish_turn(s, p):
    refill_tray(s)
    s.actions_left[p] -= 1
    s.turn = (p + 1) % len(s.players)
    s.turn_no += 1
    emit(s, "turn_end", p=p)
    s.stack.pop()


def r_turn(s, f, ch):
    p, stage = f[1], f[2]
    pl = s.players[p]
    tag = ch[0]
    if stage == 0:
        if tag == "play":
            emit(s, "action", p=p, action="play", bird=ch[1], habitat=ch[2])
            s.stack[-1] = ("turn", p, 1)
            push_play(s, p, ch[1], ch[2])
        elif tag in ACTION_TAGS:
            emit(s, "action", p=p, action=tag)
            s.stack[-1] = ("turn", p, 1)
            s.stack.append(("act", p, ACTION_TAGS.index(tag), 0))
        else:
            s.cfg.plugin_tags[tag].apply_option(s, p, ch)
    elif stage == 2:
        pl.hand.remove(ch[1])
        s.discard.append(ch[1])
        s.eot_discard -= 1
        emit(s, "card_discarded", p=p, bird=ch[1], why="end_of_turn")
    else:
        if tag == "pass":
            finish_turn(s, p)
        else:
            s.cfg.plugin_tags[tag].apply_option(s, p, ch)


def h_pay_food(s, f):
    p = f[1]
    opts = [("pay", v) for v in payments(s.players[p].food, s.cfg.db.birds[f[2]])]
    s.pend = (p, "pay_food", opts)


def r_pay_food(s, f, ch):
    food = s.players[f[1]].food
    v = ch[1]
    for i in ALL_FOODS:
        food[i] -= v[i]
    emit(s, "food_spent", p=f[1], food=list(v), bird=f[2], why="bird_cost")
    s.stack.pop()


def h_pay_eggs(s, f):
    p = f[1]
    opts = [("bird", x[0]) for row in s.players[p].board for x in row if x[1] > 0]
    s.pend = (p, "pay_egg", opts)


def r_pay_eggs(s, f, ch):
    p, n = f[1], f[2]
    find(s.players[p], ch[1])[2][1] -= 1
    emit(s, "egg_discarded", p=p, bird=ch[1], why="bird_cost")
    if n > 1:
        s.stack[-1] = ("pay_eggs", p, n - 1)
    else:
        s.stack.pop()


def h_place(s, f):
    _, p, c, h = f
    pl = s.players[p]
    pl.hand.remove(c)
    row = pl.board[h]
    row.append([c, 0, 0, 0])
    emit(s, "bird_played", p=p, bird=c, habitat=h, slot=len(row) - 1)
    s.pinkq.append((T_PLAY, p, h))
    st = s.stack
    st[-1] = ("pinks", p)
    b = s.cfg.db.birds[c]
    if b.timing == "white" and fx.feasible(s, p, c, b):
        st.append(("maybe", p, c, 0))


def h_act(s, f):
    _, p, h, stage = f
    pl = s.players[p]
    row = pl.board[h]
    st = s.stack
    if stage == 0:
        n = BASE_GAIN[h][len(row)]
        st[-1] = ("act", p, h, 1)
        if h == 0:
            s.food_action = p
            s.rodent = False
            st.append(("gain_feeder", p, None, n, -1, 0))
        elif h == 1:
            st.append(("lay", p, n, None, -1, 0))
        else:
            st.append(("draw", p, 0, n))
    elif stage == 1:
        if len(row) & 1:
            opts = [("skip",)]
            if h == 0:
                opts.extend(("discard_card", c) for c in pl.hand)
            elif h == 1:
                opts.extend(("discard_food", i) for i in ALL_FOODS if pl.food[i])
            else:
                opts.extend(("discard_egg", x[0]) for r in pl.board for x in r if x[1] > 0)
            s.pend = (p, "bonus_trade", opts)
        else:
            st[-1] = ("act", p, h, 2)
    elif stage == 2:
        # The core benefit is done. Rulings 20191218 and 20200411: pink powers that
        # watch the "gain food" and "lay eggs" actions look only at this core benefit.
        if h == 0:
            s.food_action = -1
            if s.rodent:
                s.pinkq.append((T_FOOD, p, RODENT))
        elif h == 1:
            s.pinkq.append((T_LAY, p, 0))
        st[-1] = ("act", p, h, 3)
        st.append(("row", p, h, len(row) - 1))
    else:
        st.pop()


def r_act(s, f, ch):
    _, p, h, stage = f
    pl = s.players[p]
    st = s.stack
    st[-1] = ("act", p, h, 2)
    tag = ch[0]
    if tag == "skip":
        return
    if tag == "discard_card":
        pl.hand.remove(ch[1])
        s.discard.append(ch[1])
        emit(s, "card_discarded", p=p, bird=ch[1], why="bonus_trade")
        st.append(("gain_feeder", p, None, 1, -1, 0))
    elif tag == "discard_food":
        pl.food[ch[1]] -= 1
        emit(s, "food_spent", p=p, food=[int(i == ch[1]) for i in ALL_FOODS], why="bonus_trade")
        st.append(("lay", p, 1, None, -1, 0))
    else:
        find(pl, ch[1])[2][1] -= 1
        emit(s, "egg_discarded", p=p, bird=ch[1], why="bonus_trade")
        st.append(("draw", p, 0, 1))


def h_row(s, f):
    """Activate the brown powers in a row from right to left."""
    _, p, h, i = f
    if s.pinkq:
        # Rulings 20200204a and 20231030: a pink power resolves as soon as the power
        # that triggered it has finished, before the next bird in the row.
        s.stack.append(("pinks", p))
        return
    if i < 0:
        s.stack.pop()
        return
    s.stack[-1] = ("row", p, h, i - 1)
    row = s.players[p].board[h]
    if i < len(row):
        c = row[i][0]
        b = s.cfg.db.birds[c]
        if b.timing == "brown" and fx.feasible(s, p, c, b):
            s.stack.append(("maybe", p, c, 0))


def h_maybe(s, f):
    s.pend = (f[1], "activate_power", [("activate", f[2]), ("skip",)])


def r_maybe(s, f, ch):
    _, p, c, pink = f
    if ch[0] == "skip":
        s.stack.pop()
        return
    b = s.cfg.db.birds[c]
    if pink:
        pl = s.players[p]
        pl.pink_used = pl.pink_used + (c,)
    emit(s, "power", p=p, bird=c, color=b.timing)
    s.stack[-1] = ("steps", p, c, b.steps, 0, ())


def h_steps(s, f):
    _, p, c, steps, i, chain = f
    if i >= len(steps):
        s.stack.pop()
        return
    s.stack[-1] = ("steps", p, c, steps, i + 1, chain)
    step = steps[i]
    fx.EXEC[step["op"]](s, p, c, step, chain)


def h_then(s, f):
    s.stack.pop()
    if s.did:
        s.stack.append(("steps", f[1], f[2], f[3], 0, f[4]))


def h_pinks(s, f):
    st = s.stack
    st.pop()
    q = s.pinkq
    if not q:
        return
    s.pinkq = []
    actor = f[1]
    n = len(s.players)
    birds = s.cfg.db.birds
    frames = []
    # Ruling 20231030: several triggered pink powers resolve in turn order,
    # starting with the player after the active player.
    for off in range(1, n):
        j = (actor + off) % n
        pl = s.players[j]
        for row in pl.board:
            for x in row:
                b = birds[x[0]]
                if b.timing != "pink" or x[0] in pl.pink_used:
                    continue
                t = b.trigger
                tt = TRIGGER_TYPE[t["on"]]
                for kind, _, prm in q:
                    if kind == tt and (tt == T_LAY or tt == T_PREDATOR
                                       or (tt == T_PLAY and prm == t["habitat"])
                                       or (tt == T_FOOD and prm == t["food"])):
                        if fx.feasible(s, j, x[0], b):
                            frames.append(("maybe", j, x[0], 1))
                        break
    st.extend(reversed(frames))


def h_group(s, f):
    s.pend = (GROUP, f[2], list(f[3]))


def r_group(s, f, ch):
    s.stack.pop()
    emit(s, "group_decision", kind=f[2], choice=ch)
    s.cfg.plugins[f[1]].on_group_choice(s, f[2], ch)


# ---------------------------------------------------------------- atomic frames

def h_gain_supply(s, f):
    _, p, foods, n, other = f
    if n <= 0:
        s.stack.pop()
        return
    if len(foods) == 1:
        s.players[p].food[foods[0]] += n
        emit(s, "food_gained", p=p, food=foods[0], n=n, source="supply")
        s.stack.pop()
        return
    s.pend = (p, "choose_food", [("food", i) for i in foods if not (other and i == s.last_food)])


def r_gain_supply(s, f, ch):
    _, p, foods, n, other = f
    s.players[p].food[ch[1]] += 1
    emit(s, "food_gained", p=p, food=ch[1], n=1, source="supply")
    s.stack[-1] = ("gain_supply", p, foods, n - 1, other)


def h_gain_feeder(s, f):
    """Gain food from the birdfeeder. Flags: 1 = may decline, 2 = already chose not to reroll."""
    _, p, foods, n, cache, fl = f
    if n == 0:
        s.stack.pop()
        return
    feeder = s.feeder
    if not feeder:
        reroll_feeder(s, "empty")
        feeder = s.feeder
    if not fl & 2 and feeder.count(feeder[0]) == len(feeder):
        s.pend = (p, "reroll_feeder", [("keep",), ("reroll",)])
        return
    opts = []
    for face in sorted(set(feeder)):
        if face < 5:
            if foods is None or face in foods:
                opts.append(("die", face, face))
        else:
            if foods is None or 0 in foods:
                opts.append(("die", 5, 0))
            if foods is None or 1 in foods:
                opts.append(("die", 5, 1))
    if not opts:
        s.did = False
        s.stack.pop()
        return
    if n < 0:  # gain every matching die
        s.stack.pop()
        takes = [(face, food, feeder.count(face)) for _, face, food in opts]
        for face, food, k in takes:
            for _ in range(k):
                take_die(s, p, face, food)
        s.did = True
        return
    if fl & 1:
        opts.append(("skip",))
    s.pend = (p, "take_die", opts)


def r_gain_feeder(s, f, ch):
    _, p, foods, n, cache, fl = f
    tag = ch[0]
    if tag == "keep":
        s.stack[-1] = ("gain_feeder", p, foods, n, cache, fl | 2)
        return
    if tag == "reroll":
        reroll_feeder(s, "all_same")
        return
    if tag == "skip":
        s.did = False
        s.stack.pop()
        return
    take_die(s, p, ch[1], ch[2])
    s.did = True
    if n > 1:
        s.stack[-1] = ("gain_feeder", p, foods, n - 1, cache, fl & 1)
    else:
        s.stack.pop()
    if cache >= 0:
        s.stack.append(("cache_choice", p, cache, ch[2]))


def h_cache_choice(s, f):
    s.pend = (f[1], "cache_food", [("cache",), ("keep",)])


def r_cache_choice(s, f, ch):
    _, p, c, food = f
    s.stack.pop()
    if ch[0] == "cache":
        pl = s.players[p]
        pl.food[food] -= 1
        find(pl, c)[2][2] += 1
        emit(s, "food_cached", p=p, bird=c, food=food, n=1, source="player")


def h_each_feeder(s, f):
    s.pend = (f[1], "choose_first_player", [("player", j) for j in range(len(s.players))])


def r_each_feeder(s, f, ch):
    _, p, count, decl = f
    n = len(s.players)
    s.stack.pop()
    for off in reversed(range(n)):
        s.stack.append(("gain_feeder", (ch[1] + off) % n, None, count, -1, decl))


def h_draw(s, f):
    """Draw bird cards. Source 0 = tray or deck (player's choice), 1 = deck, 2 = the whole tray."""
    _, p, src, n = f
    pl = s.players[p]
    if src == 2:
        s.stack.pop()
        if s.tray:
            emit(s, "cards_drawn", p=p, source="tray", birds=list(s.tray))
            pl.hand.extend(s.tray)
            s.tray = []
        return
    if src == 1:
        s.stack.pop()
        for _ in range(n):
            c = draw_from_deck(s)
            if c < 0:
                break
            pl.hand.append(c)
            emit(s, "cards_drawn", p=p, source="deck", birds=[c])
        return
    if n <= 0:
        s.stack.pop()
        return
    opts = [("tray", c) for c in s.tray]
    if s.deck or s.discard:
        opts.append(("deck",))
    if not opts:
        s.stack.pop()
        return
    s.pend = (p, "draw_card", opts)


def _take_card(s, ch):
    if ch[0] == "tray":
        s.tray.remove(ch[1])
        return ch[1]
    return draw_from_deck(s)


def r_draw(s, f, ch):
    _, p, src, n = f
    c = _take_card(s, ch)
    s.players[p].hand.append(c)
    emit(s, "cards_drawn", p=p, source=ch[0], birds=[c])
    s.stack[-1] = ("draw", p, src, n - 1)


def h_lay(s, f):
    """Lay eggs one at a time. Flags: 1 = may decline, 2 = remember the bird chosen,
    4 = not on the remembered bird."""
    _, p, n, nest, excl, fl = f
    if n <= 0:
        s.stack.pop()
        return
    if fl & 4:
        excl = s.memo
    birds = s.cfg.db.birds
    opts = []
    for row in s.players[p].board:
        for x in row:
            b = birds[x[0]]
            if x[1] < b.egg_limit and x[0] != excl and (nest is None or b.nest == nest or b.nest == "wild"):
                opts.append(("bird", x[0]))
    if not opts:
        s.stack.pop()
        return
    if fl & 1:
        opts.append(("skip",))
    s.pend = (p, "lay_egg", opts)


def r_lay(s, f, ch):
    _, p, n, nest, excl, fl = f
    if ch[0] == "skip":
        s.stack.pop()
        return
    find(s.players[p], ch[1])[2][1] += 1
    if fl & 2:
        s.memo = ch[1]
    emit(s, "eggs_laid", p=p, bird=ch[1], n=1)
    s.stack[-1] = ("lay", p, n - 1, nest, excl, fl)


def h_opt_lay(s, f):
    _, p, c, n = f
    loc = find(s.players[p], c)
    # Ruling 20190203: a full bird may still tuck; it just cannot take the egg.
    if loc is None or loc[2][1] >= s.cfg.db.birds[c].egg_limit:
        s.stack.pop()
        return
    s.pend = (p, "optional_lay", [("lay",), ("skip",)])


def r_opt_lay(s, f, ch):
    _, p, c, n = f
    s.stack.pop()
    if ch[0] == "lay":
        slot = find(s.players[p], c)[2]
        k = min(n, s.cfg.db.birds[c].egg_limit - slot[1])
        slot[1] += k
        emit(s, "eggs_laid", p=p, bird=c, n=k)


def h_tuck_hand(s, f):
    _, p, c, n = f
    hand = s.players[p].hand
    if n <= 0 or not hand:
        if n > 0:
            s.did = False
        s.stack.pop()
        return
    s.pend = (p, "tuck_card", [("card", x) for x in hand])


def r_tuck_hand(s, f, ch):
    _, p, c, n = f
    pl = s.players[p]
    pl.hand.remove(ch[1])
    s.tucked.append(ch[1])
    find(pl, c)[2][3] += 1
    s.did = True
    emit(s, "card_tucked", p=p, bird=c, card=ch[1], source="hand")
    s.stack[-1] = ("tuck_hand", p, c, n - 1)


def h_bonus_keep(s, f):
    s.pend = (f[1], "keep_bonus", [("bonus", b) for b in f[2]])


def r_bonus_keep(s, f, ch):
    _, p, cards = f
    s.players[p].bonus.append(ch[1])
    s.bonus_discard.extend(b for b in cards if b != ch[1])
    emit(s, "bonus_kept", p=p, bonus=ch[1], discarded=[b for b in cards if b != ch[1]])
    s.stack.pop()


def h_cost_egg(s, f):
    _, p, excl = f
    opts = [("bird", x[0]) for row in s.players[p].board for x in row if x[1] > 0 and x[0] != excl]
    if not opts:
        s.did = False
        s.stack.pop()
        return
    s.pend = (p, "discard_egg", opts)


def r_cost_egg(s, f, ch):
    p = f[1]
    find(s.players[p], ch[1])[2][1] -= 1
    s.did = True
    emit(s, "egg_discarded", p=p, bird=ch[1], why="power_cost")
    s.stack.pop()


def h_cost_food(s, f):
    p = f[1]
    food = s.players[p].food
    opts = [("food", i) for i in ALL_FOODS if food[i]]
    if not opts:
        s.did = False
        s.stack.pop()
        return
    s.pend = (p, "discard_food", opts)


def r_cost_food(s, f, ch):
    p = f[1]
    s.players[p].food[ch[1]] -= 1
    s.last_food = ch[1]
    s.did = True
    emit(s, "food_spent", p=p, food=[int(i == ch[1]) for i in ALL_FOODS], why="power_cost")
    s.stack.pop()


def repeat_targets(s, p, c, predator_only, chain):
    loc = find(s.players[p], c)
    if loc is None:
        return []
    birds = s.cfg.db.birds
    out = []
    for x in s.players[p].board[loc[0]]:
        t = x[0]
        if t == c or t in chain:
            continue
        b = birds[t]
        if b.timing == "brown" and (b.predator or not predator_only):
            out.append(("bird", t))
    return out


def h_repeat(s, f):
    _, p, c, pred, chain = f
    opts = repeat_targets(s, p, c, pred, chain)
    if not opts:
        s.stack.pop()
        return
    s.pend = (p, "repeat_power", opts)


def r_repeat(s, f, ch):
    _, p, c, pred, chain = f
    t = ch[1]
    emit(s, "power", p=p, bird=t, color="brown", repeated_by=c)
    # Ruling 20200108: the other bird repeats its own power as itself.
    s.stack[-1] = ("steps", p, t, s.cfg.db.birds[t].steps, 0, chain + (c,))


def h_extra_play(s, f):
    _, p, h = f
    s.pend = (p, "play_extra", [("skip",)] + play_options(s, p, h))


def r_extra_play(s, f, ch):
    s.stack.pop()
    if ch[0] == "play":
        emit(s, "action", p=f[1], action="play_extra", bird=ch[1], habitat=ch[2])
        push_play(s, f[1], ch[1], ch[2])


def move_targets(s, p, c):
    loc = find(s.players[p], c)
    if loc is None:
        return []
    h, i, _ = loc
    board = s.players[p].board
    if i != len(board[h]) - 1:
        return []  # ruling 20260319: no longer rightmost, so the power fizzles
    # Ruling 20201206b: habitat restrictions apply only when a bird is played.
    return [("habitat", h2) for h2 in (0, 1, 2) if h2 != h and len(board[h2]) < 5]


def h_move(s, f):
    _, p, c = f
    opts = move_targets(s, p, c)
    if not opts:
        s.stack.pop()
        return
    s.pend = (p, "move_bird", opts)


def r_move(s, f, ch):
    _, p, c = f
    board = s.players[p].board
    h = find(s.players[p], c)[0]
    slot = board[h].pop()
    board[ch[1]].append(slot)
    emit(s, "bird_moved", p=p, bird=c, source=h, to=ch[1])
    s.stack.pop()


def h_draft(s, f):
    """American Oystercatcher: the owner draws the cards, then everyone picks one."""
    _, p, pool, need = f
    if need > 0:
        opts = [("tray", c) for c in s.tray]
        if s.deck or s.discard:
            opts.append(("deck",))
        if opts:
            s.pend = (p, "draw_card", opts)
            return
    emit(s, "cards_revealed", p=p, birds=list(pool))
    s.stack[-1] = ("draft_pick", p, pool, 0)


def r_draft(s, f, ch):
    _, p, pool, need = f
    c = _take_card(s, ch)
    emit(s, "card_set_aside", p=p, source=ch[0], bird=c)
    s.stack[-1] = ("draft", p, pool + (c,), need - 1)


def h_draft_pick(s, f):
    _, p, pool, k = f
    n = len(s.players)
    if not pool:
        s.stack.pop()
        return
    if k >= n:  # the owner keeps what is left
        s.players[p].hand.extend(pool)
        emit(s, "cards_drawn", p=p, source="draft", birds=list(pool))
        s.stack.pop()
        return
    s.pend = ((p + k) % n, "draft_pick", [("card", c) for c in pool])


def r_draft_pick(s, f, ch):
    _, p, pool, k = f
    j = (p + k) % len(s.players)
    s.players[j].hand.append(ch[1])
    emit(s, "cards_drawn", p=j, source="draft", birds=[ch[1]])
    s.stack[-1] = ("draft_pick", p, tuple(c for c in pool if c != ch[1]), k + 1)


HANDLERS = {
    "main": h_main, "setup": h_setup, "turn": h_turn, "pay_food": h_pay_food, "pay_eggs": h_pay_eggs,
    "place": h_place, "act": h_act, "row": h_row, "maybe": h_maybe, "steps": h_steps, "then": h_then,
    "pinks": h_pinks, "group": h_group, "gain_supply": h_gain_supply, "gain_feeder": h_gain_feeder,
    "cache_choice": h_cache_choice, "each_feeder": h_each_feeder, "draw": h_draw, "lay": h_lay,
    "opt_lay": h_opt_lay, "tuck_hand": h_tuck_hand, "bonus_keep": h_bonus_keep, "cost_egg": h_cost_egg,
    "cost_food": h_cost_food, "repeat": h_repeat, "extra_play": h_extra_play, "move": h_move,
    "draft": h_draft, "draft_pick": h_draft_pick,
}
RESUME = {
    "setup": r_setup, "turn": r_turn, "pay_food": r_pay_food, "pay_eggs": r_pay_eggs, "act": r_act,
    "maybe": r_maybe, "group": r_group, "gain_supply": r_gain_supply, "gain_feeder": r_gain_feeder,
    "cache_choice": r_cache_choice, "each_feeder": r_each_feeder, "draw": r_draw, "lay": r_lay,
    "opt_lay": r_opt_lay, "tuck_hand": r_tuck_hand, "bonus_keep": r_bonus_keep, "cost_egg": r_cost_egg,
    "cost_food": r_cost_food, "repeat": r_repeat, "extra_play": r_extra_play, "move": r_move,
    "draft": r_draft, "draft_pick": r_draft_pick,
}


def run(s):
    """Advance until a real choice is needed or the game is over."""
    stack = s.stack
    handlers = HANDLERS
    while stack:
        f = stack[-1]
        handlers[f[0]](s, f)
        pend = s.pend
        if pend is not None:
            if len(pend[2]) != 1:
                return
            s.pend = None
            f = stack[-1]
            RESUME[f[0]](s, f, pend[2][0])


def resume(s, choice):
    pend = s.pend
    if pend is None:
        raise IllegalChoice("no decision is pending")
    if choice not in pend[2]:
        raise IllegalChoice(f"{choice!r} is not a legal option for {pend[1]}")
    s.pend = None
    f = s.stack[-1]
    RESUME[f[0]](s, f, choice)
    run(s)


def play_random(s, rng):
    """Play uniformly random choices in place until the game is over. `rng` is a random.Random."""
    rnd = rng.random
    stack = s.stack
    while True:
        pend = s.pend
        if pend is None:
            return
        opts = pend[2]
        s.pend = None
        f = stack[-1]
        RESUME[f[0]](s, f, opts[int(rnd() * len(opts))])
        run(s)


def deal(cfg, seed):
    """Set up a new game up to the first decision."""
    from .state import Player, State

    n = cfg.n
    d = cfg.db
    s = State.__new__(State)
    s.cfg = cfg
    s.rng = (seed * 0x9E3779B97F4A7C15 + 0x1234567) & ((1 << 64) - 1)
    s.phase = SETUP
    s.round = 1
    s.turn = 0
    s.turn_no = 0
    s.setup_idx = 0
    s.actions_left = [0] * n
    s.deck = list(d.bird_ids)
    shuffle(s, s.deck)
    s.discard = []
    s.bonus_deck = list(d.bonus_ids)
    shuffle(s, s.bonus_deck)
    s.bonus_discard = []
    s.tucked = []
    tiles = list(range(len(d.tiles)))
    shuffle(s, tiles)
    s.goals = tuple(d.tiles[t][rand_below(s, 2)] for t in tiles[:4])
    s.goal_points = [0.0] * n
    s.group_score = 0.0
    s.goal_log = ()
    s.players = []
    for _ in range(n):
        pl = Player()
        pl.hand = [s.deck.pop() for _ in range(5)]
        pl.bonus = [s.bonus_deck.pop() for _ in range(2)]
        pl.food = [1, 1, 1, 1, 1]
        s.players.append(pl)
    s.tray = [s.deck.pop() for _ in range(3)]
    s.feeder = [rand_below(s, 6) for _ in range(5)]
    s.first = rand_below(s, n)
    s.variant = {}
    s.stack = [("main",)]
    s.pend = None
    s.did = False
    s.memo = -1
    s.last_food = -1
    s.pinkq = []
    s.eot_discard = 0
    s.food_action = -1
    s.rodent = False
    s.events = [] if cfg.record_events else None
    emit(s, "setup", goals=list(s.goals), first=s.first, tray=list(s.tray), feeder=list(s.feeder))
    run(s)
    return s
