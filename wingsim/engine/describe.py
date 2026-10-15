"""Plain-text descriptions of cards, options and observations.

Used for the language-model agent's prompt and for the labels stored in replay
logs. Card names and power text are read here, in the engine, so that agent
code never has to touch them.
"""
from .cards import FACE_NAMES, FOODS, HABITATS
from .observe import HIDDEN
from .rules import BASE_GAIN, EGG_COST, find
from .scoring import current_goal_counts, player_breakdown
from .state import GROUP, OVER, SETUP

GOAL_TEXT = {
    "birds_in_habitat": "birds in your {p}",
    "eggs_in_habitat": "eggs on birds in your {p}",
    "nest_birds_with_egg": "birds with a {p} nest that have at least 1 egg (star nests count)",
    "eggs_in_nest": "eggs on birds with a {p} nest (star nests count)",
    "egg_sets": "sets of 3 eggs, one each in forest, grassland and wetland",
    "total_birds": "birds on your mat",
}
ACTION_TEXT = (
    "Gain food (forest): take {n} food from the birdfeeder{trade}, then activate your forest birds",
    "Lay eggs (grassland): lay {n} eggs{trade}, then activate your grassland birds",
    "Draw cards (wetland): draw {n} card(s){trade}, then activate your wetland birds",
)
TRADE_TEXT = (" (may discard 1 card for 1 more food)", " (may spend 1 food for 1 more egg)",
              " (may discard 1 egg for 1 more card)")
DECISION_TEXT = {
    "action": "Choose your action for this turn.",
    "activate_power": "This bird's power may be used now. Use it?",
    "bonus_trade": "This row offers an optional trade for one extra resource.",
    "cache_food": "You gained the food. Cache it on the bird or keep it?",
    "choose_first_player": "Choose which player takes food from the birdfeeder first.",
    "choose_food": "Choose which food to gain from the supply.",
    "discard_card": "Discard a card from your hand (owed at the end of your turn).",
    "discard_egg": "Choose a bird to remove an egg from, as the cost of the power.",
    "discard_food": "Choose a food to spend as the cost of the power.",
    "draft_pick": "Choose one of the revealed cards to take.",
    "draw_card": "Draw a card: take a face-up bird from the tray or the top of the deck.",
    "end_turn": "Your action is finished. Anything else before your turn ends?",
    "keep_bonus": "Choose which bonus card to keep.",
    "lay_egg": "Choose a bird to lay an egg on.",
    "move_bird": "Choose the habitat to move this bird to.",
    "optional_lay": "You may also lay an egg on this bird.",
    "pay_egg": "Choose a bird to remove an egg from, to pay the column's egg cost.",
    "pay_food": "Choose how to pay the bird's food cost.",
    "play_extra": "You may play an additional bird, paying its normal cost.",
    "repeat_power": "Choose which bird's power to repeat.",
    "reroll_feeder": "All dice in the birdfeeder show the same face. You may reroll all 5 dice first.",
    "set_difficulty": "The group sets the difficulty for the coming round.",
    "setup_discard_food": "Setup: choose which food tokens to discard (1 for each bird you kept).",
    "setup_keep_birds": "Setup: choose which of your 5 starting birds to keep. Each bird kept costs 1 of "
                        "your 5 starting food tokens.",
    "setup_keep_bonus": "Setup: choose which bonus card to keep.",
    "take_die": "Choose a die to take from the birdfeeder.",
    "tuck_card": "Choose a card from your hand to tuck behind the bird.",
}


def food_list(vector):
    parts = [f"{k} {FOODS[i]}" for i, k in enumerate(vector) if k]
    return " + ".join(parts) if parts else "nothing"


def cost_text(b):
    if b.total_cost == 0:
        return "free"
    if b.either:
        return "1 " + " or ".join(FOODS[i] for i in range(5) if b.cost[i])
    parts = [f"{k} {FOODS[i]}" for i, k in enumerate(b.cost) if k]
    if b.wild:
        parts.append(f"{b.wild} of any food")
    return " + ".join(parts)


def bird_name(db, cid):
    return "a hidden card" if cid == HIDDEN else db.birds[cid].name


def card_line(db, cid):
    """One line with everything printed on a bird card."""
    if cid == HIDDEN:
        return "(hidden card)"
    b = db.birds[cid]
    nest = {"wild": "star", "none": "no"}.get(b.nest, b.nest)
    power = f"{b.timing} power: {b.text}" if b.text else "no power"
    flags = "".join(f", {f}" for f, on in (("predator", b.predator), ("flocking", b.flocking)) if on)
    return (f"{b.name} [{b.vp} points; cost {cost_text(b)}; lives in {'/'.join(HABITATS[h] for h in b.habitats)}; "
            f"{nest} nest, holds {b.egg_limit} egg{'' if b.egg_limit == 1 else 's'}; wingspan {b.wingspan} cm{flags}] {power}")


def bonus_line(db, bid):
    if bid == HIDDEN:
        return "(hidden bonus card)"
    c = db.bonus[bid]
    if c.per is not None:
        pay = f"{c.per} points per bird"
    else:
        pay = "; ".join(f"{lo}+ birds: {pts} points" for lo, pts in c.tiers)
    return f"{c.name}: {c.condition} ({pay})"


def goal_text(db, gid):
    g = db.goals[gid]
    p = HABITATS[g.param] if isinstance(g.param, int) else g.param
    return GOAL_TEXT[g.kind].format(p=p)


def option_label(s, kind, o):
    """A short sentence describing one legal option of the pending decision."""
    db = s.cfg.db
    tag = o[0]
    if tag == "play":
        b = db.birds[o[1]]
        eggs = EGG_COST[len(s.players[s.pend[0]].board[o[2]])] if s.pend and s.pend[0] != GROUP else 0
        egg = f" and {eggs} egg{'s' if eggs > 1 else ''}" if eggs else ""
        return f"Play {b.name} in your {HABITATS[o[2]]} (pay {cost_text(b)}{egg})"
    if tag in ("food", "eggs", "cards") and kind == "action":
        h = ("food", "eggs", "cards").index(tag)
        row = s.players[s.pend[0]].board[h]
        return ACTION_TEXT[h].format(n=BASE_GAIN[h][len(row)], trade=TRADE_TEXT[h] if len(row) & 1 else "")
    if tag == "skip":
        return {"activate_power": "Do not use the power", "bonus_trade": "No trade", "lay_egg": "Do not lay the egg",
                "take_die": "Take nothing", "optional_lay": "Do not lay the egg",
                "play_extra": "Do not play another bird"}.get(kind, "Skip")
    if tag == "activate":
        b = db.birds[o[1]]
        return f"Use {b.name}'s power: {b.text}"
    if tag == "die":
        return f"Take a {FACE_NAMES[o[1]]} die" + (f" as {FOODS[o[2]]}" if o[1] == 5 else "")
    if tag == "keep" and kind == "reroll_feeder":
        return "Keep the dice as they are"
    if tag == "reroll":
        return "Reroll all 5 dice into the birdfeeder"
    if tag == "tray":
        return f"Take from the tray: {card_line(db, o[1])}"
    if tag == "deck":
        return "Draw the top card of the deck (unseen)"
    if tag == "bird":
        name = db.birds[o[1]].name
        if kind == "lay_egg":
            loc = find(s.players[s.pend[0]], o[1])
            have = f" (now {loc[2][1]} of {db.birds[o[1]].egg_limit})" if loc else ""
            return f"Lay it on {name}{have}"
        if kind == "repeat_power":
            return f"Repeat {name}'s power: {db.birds[o[1]].text}"
        return f"Remove an egg from {name}"
    if tag == "pay":
        return f"Pay {food_list(o[1])}"
    if tag == "discard_card":
        return f"Discard {bird_name(db, o[1])} from your hand to gain 1 more food"
    if tag == "discard_food" and kind == "bonus_trade":
        return f"Spend 1 {FOODS[o[1]]} to lay 1 more egg"
    if tag == "discard_egg":
        return f"Remove an egg from {db.birds[o[1]].name} to draw 1 more card"
    if tag == "cache":
        return "Cache it on the bird (worth 1 point at the end; cannot be spent)"
    if tag == "keep" and kind == "cache_food":
        return "Keep it in your supply"
    if tag == "player":
        return f"Player {o[1]} goes first"
    if tag == "food":
        return f"{'Spend' if kind == 'discard_food' else 'Gain'} 1 {FOODS[o[1]]}"
    if tag == "card":
        verb = {"discard_card": "Discard", "tuck_card": "Tuck", "draft_pick": "Take"}.get(kind, "Choose")
        return f"{verb} {card_line(db, o[1]) if kind == 'draft_pick' else bird_name(db, o[1])}"
    if tag == "bonus":
        return f"Keep {bonus_line(db, o[1])}"
    if tag == "habitat":
        return f"Move it to your {HABITATS[o[1]]}"
    if tag == "lay":
        return "Lay the egg on this bird"
    if tag == "keep":
        names = ", ".join(db.birds[c].name for c in o[1])
        return f"Keep {len(o[1])}: {names} (discard {len(o[1])} food)" if o[1] else "Keep no birds (keep all 5 food)"
    if tag == "discard_food":
        return "Discard " + (", ".join(FOODS[i] for i in o[1]) or "nothing")
    if tag == "pass":
        return "End your turn"
    plugin = s.cfg.plugin_tags.get(tag)
    if plugin is not None:
        return plugin.option_label(s, o)
    for pg in s.cfg.plugins:
        label = pg.option_label(s, o)
        if label:
            return label
    return " ".join(str(x) for x in o)


def option_labels(s):
    """Labels for every option of the pending decision, in order."""
    pend = s.pend
    if pend is None or pend[2] is None:
        return []
    return [option_label(s, pend[1], o) for o in pend[2]]


def decision_text(s):
    """What is being decided, including the bird concerned where there is one."""
    pend = s.pend
    text = DECISION_TEXT.get(pend[1], pend[1].replace("_", " "))
    f = s.stack[-1]
    db = s.cfg.db
    subject = None
    if f[0] in ("maybe", "cache_choice", "opt_lay", "tuck_hand", "repeat", "move"):
        subject = f[2]
    elif f[0] == "pay_food":
        subject = f[2]
    if subject is not None and subject in db.birds:
        text += f" Bird: {card_line(db, subject)}"
    return text


def _board_lines(db, pl):
    out = []
    for h in (0, 1, 2):
        row = pl.board[h]
        gain = BASE_GAIN[h][len(row)]
        what = ("food", "eggs", "card(s)")[h]
        out.append(f"  {HABITATS[h].capitalize()} ({len(row)} of 5 birds; its action gives {gain} {what}):"
                   + ("" if row else " empty"))
        for i, x in enumerate(row, 1):
            b = db.birds[x[0]]
            extra = "".join(f", {k} {label}" for k, label in ((x[2], "cached food"), (x[3], "tucked cards")) if k)
            out.append(f"    {i}. {card_line(db, x[0])} | eggs {x[1]}/{b.egg_limit}{extra}")
    return out


def observation_text(obs):
    """Everything the observer may see, as text."""
    s = obs.state
    db = s.cfg.db
    me = obs.player
    n = len(s.players)
    L = []
    if s.phase == OVER:
        L.append("The game is over.")
    elif s.phase == SETUP:
        L.append("Setup, before round 1.")
    else:
        L.append(f"Round {s.round} of 4. Turns left this round: "
                 + ", ".join(f"player {j}: {s.actions_left[j]}" for j in range(n)) + ".")
    L.append(f"{n} players, seated clockwise 0 to {n - 1}. First player this round: player {s.first}."
             + ("" if me == GROUP else f" You are player {me}."))
    counts = current_goal_counts(s)
    L.append("Round goals:")
    for r, gid in enumerate(s.goals, 1):
        line = f"  Round {r}: {goal_text(db, gid)}"
        if r <= len(s.goal_log):
            entry = s.goal_log[r - 1]
            line += f" - finished; counts {list(entry[1])}"
        elif r == s.round and counts is not None:
            line += f" - CURRENT; counts so far {list(counts)}"
        L.append(line)
    for pg in s.cfg.plugins:
        status = pg.status_text(s)
        if status:
            L.append(status)
    L.append("Birdfeeder dice: " + ", ".join(FACE_NAMES[f] for f in sorted(s.feeder))
             + f" ({5 - len(s.feeder)} dice outside the feeder).")
    L.append(f"Bird tray (face up): " + ("empty" if not s.tray else ""))
    for c in s.tray:
        L.append(f"  - {card_line(db, c)}")
    L.append(f"Deck: {len(s.deck)} cards. Discard pile: {len(s.discard)} cards.")
    for j, pl in enumerate(s.players):
        hidden_bonus = HIDDEN in pl.bonus
        if hidden_bonus:       # score what is visible; a hidden bonus card's points stay hidden
            kept, pl.bonus = pl.bonus, []
            sc = player_breakdown(s, j)
            pl.bonus = kept
        else:
            sc = player_breakdown(s, j)
        bonus = "bonus hidden" if hidden_bonus else f"bonus {sc['bonus']}"
        L.append("")
        L.append(f"PLAYER {j}" + (" (you)" if j == me else "") + f": food {food_list(pl.food)}; "
                 f"points so far {sc['total']:g} (birds {sc['birds']}, eggs {sc['eggs']}, cached {sc['cached']}, "
                 f"tucked {sc['tucked']}, {bonus}, goals {sc['goals']:g})")
        if pl.bonus and HIDDEN not in pl.bonus:
            for b in pl.bonus:
                L.append(f"  Bonus card: {bonus_line(db, b)}")
        else:
            L.append(f"  Bonus cards: {len(pl.bonus)} (hidden)")
        if pl.hand and HIDDEN in pl.hand:
            L.append(f"  Hand: {len(pl.hand)} cards (hidden)")
        else:
            L.append(f"  Hand ({len(pl.hand)} cards):" + ("" if pl.hand else " empty"))
            for c in pl.hand:
                L.append(f"    - {card_line(db, c)}")
        L.extend(_board_lines(db, pl))
    return "\n".join(L)


# ---------------------------------------------------------------- prompt helpers for the language-model agent

def compact_payments(s, what, labels):
    """For a food payment with several options: name the part every option pays, and label each
    option by the rest only, so the options differ visibly."""
    pend = s.pend
    if pend is None or pend[1] != "pay_food" or pend[2] is None or len(pend[2]) < 2:
        return what, labels
    vectors = [o[1] for o in pend[2]]
    common = [min(v[i] for v in vectors) for i in range(5)]
    have = s.players[pend[0]].food
    what += f" You have {food_list(have)}."
    if any(common):
        what += f" Every option pays {food_list(common)}; they differ only in the rest."
        labels = [f"Pay {food_list(common)}, plus {food_list([v[i] - common[i] for i in range(5)])}"
                  for v in vectors]
    return what, labels


def keep_birds_items(s):
    """For the setup choice of starting birds: the dealt birds as (id, card line), in hand order."""
    pend = s.pend
    if pend is None or pend[1] != "setup_keep_birds":
        return None
    ids = max((o[1] for o in pend[2]), key=len)
    db = s.cfg.db
    return [(c, card_line(db, c)) for c in ids]


def _bonus_progress(s, p, before, after):
    from .scoring import bonus_count
    db = s.cfg.db
    out = []
    for b in s.players[p].bonus:
        if b == HIDDEN:
            continue
        card = db.bonus[b]
        n0, n1 = bonus_count(before, p, card), bonus_count(after, p, card)
        if n1 != n0:
            pts0, pts1 = card.points(n0), card.points(n1)
            out.append(f"bonus card {card.name}: {n0} -> {n1} birds"
                       + (f" ({pts0} -> {pts1} points)" if pts1 != pts0 else f" (still {pts0} points)"))
    return out


def _goal_progress(before, after, p):
    c0, c1 = current_goal_counts(before), current_goal_counts(after)
    if c0 is None or c1 is None or c0[p] == c1[p]:
        return []
    return [f"round goal count {c0[p]} -> {c1[p]}"]


def _row_powers(db, row):
    """The brown powers a row's action would offer, in the order they are offered (right to left)."""
    names = [db.birds[x[0]].name for x in reversed(row) if db.birds[x[0]].timing == "brown"]
    return f"then you may use these brown powers, right to left: {', '.join(names)}" if names else \
        "no brown powers in this row"


def action_outcomes(s):
    """One line per option of a pending action decision: what it changes right away, worked out from
    what the deciding player can see. Later choices (which die, where the eggs go) are left open."""
    pend = s.pend
    if pend is None or pend[1] != "action" or pend[2] is None:
        return None
    from .rules import payments
    db = s.cfg.db
    p = pend[0]
    pl = s.players[p]
    eggs_total = sum(x[1] for row in pl.board for x in row)
    room = sum(db.birds[x[0]].egg_limit - x[1] for row in pl.board for x in row)
    out = []
    for o in pend[2]:
        tag = o[0]
        if tag == "play":
            c, h = o[1], o[2]
            b = db.birds[c]
            k = len(pl.board[h])
            egg_cost = EGG_COST[k]
            after = s.copy()
            ap = after.players[p]
            ap.hand.remove(c)
            ap.board[h].append([c, 0, 0, 0])
            parts = [f"+{b.vp} points for the bird"]
            if egg_cost:
                parts.append(f"-{egg_cost} egg{'s' if egg_cost > 1 else ''} from your birds (-{egg_cost} points; "
                             f"you have {eggs_total})")
            pays = payments(pl.food, b)
            if len(pays) == 1:
                left = [pl.food[i] - pays[0][i] for i in range(5)]
                parts.append(f"food left: {food_list(left)}")
            else:
                spent = sum(pays[0])
                swap = " (any 2 food stand in for each food you lack)" if spent > b.total_cost else ""
                parts.append(f"spends {spent} food{swap}; {len(pays)} ways to pay, you choose next")
            gain = BASE_GAIN[h][k + 1]
            if gain != BASE_GAIN[h][k]:
                what = ("food", "eggs", "cards")[h]
                parts.append(f"your {HABITATS[h]} action then gives {gain} {what} (was {BASE_GAIN[h][k]})")
            parts += _goal_progress(s, after, p) + _bonus_progress(s, p, s, after)
            if b.timing == "white":
                parts.append("its power happens now")
            out.append("; ".join(parts))
        elif tag in ("food", "eggs", "cards"):
            h = ("food", "eggs", "cards").index(tag)
            row = pl.board[h]
            n = BASE_GAIN[h][len(row)]
            if h == 0:
                first = f"+{n} food (your choice of dice); food {sum(pl.food)} -> {sum(pl.food) + n}"
            elif h == 1:
                lay = min(n, room)
                first = (f"+{lay} egg{'s' if lay != 1 else ''} = +{lay} points (room for {room} more eggs on your birds)"
                         if lay else "no room for eggs on your birds")
            else:
                first = f"+{n} card{'s' if n > 1 else ''} (tray or deck); hand {len(pl.hand)} -> {len(pl.hand) + n}"
            out.append(f"{first}; {_row_powers(db, row)}")
        else:
            out.append(None)
    return out


def goal_status(s, me):
    """Where the table stands on the current round goal, as a few lines: each player's count, what the
    round would score if it ended now, the turns left, and how earlier rounds went. None when there is no
    current round goal (the game is over)."""
    from .scoring import score_goal_counts
    counts = current_goal_counts(s)
    if counts is None or s.phase == OVER:
        return None
    n = len(counts)
    db = s.cfg.db
    who = lambda j: f"player {j}" + (" (you)" if j == me else "")
    _, delta, info = score_goal_counts(s, counts)
    coop = isinstance(info, tuple) and info and info[0] == "coop"
    L = [f"ROUND GOAL STATUS - round {s.round}: {goal_text(db, s.goals[s.round - 1])}"]
    if coop and info[1] is not None:
        d = info[1]
        L.append(f"  Difficulty d = {d}: EVERY player needs a count of at least {d} (counts above 5 count as 5).")
        L.append("  " + "; ".join(f"{who(j)}: {c}" + (" - meets it" if c >= d else f" - short by {d - c}")
                                  for j, c in enumerate(counts)) + ".")
        mean = sum(min(c, 5) for c in counts) / n
        if info[2]:
            L.append(f"  If the round ended now: the goal is met and the group score rises by {delta:g} "
                     f"(average {mean:g} x d {d}).")
        else:
            met = tuple(max(c, d) for c in counts)
            _, up, _ = score_goal_counts(s, met)
            short = [j for j, c in enumerate(counts) if c < d]
            L.append(f"  If the round ended now: the goal fails (short: {', '.join(who(j) for j in short)}) and the "
                     f"group score falls by {-delta + 0.0:g}. With every player at {d} or more it would rise by "
                     f"at least {up:g}.")
    elif coop:
        L.append("  The difficulty has not been set yet.")
    else:
        pts, _, _ = score_goal_counts(s, counts)
        L.append("  " + "; ".join(f"{who(j)}: count {c}, {pts[j]:g} points" for j, c in enumerate(counts))
                 + " if the round ended now.")
    if s.phase != SETUP:
        L.append("  Turns left this round: " + ", ".join(f"{who(j)} {s.actions_left[j]}" for j in range(n)) + ".")
    done = []
    for r, cs, pts, dl, inf in s.goal_log:
        if isinstance(inf, tuple) and inf and inf[0] == "coop" and inf[1] is not None:
            done.append(f"round {r} (d = {inf[1]}) {'met' if inf[2] else 'failed'}, group score {dl + 0.0:+g}")
        else:
            done.append(f"round {r}: points " + ", ".join(f"{who(j)} {p:g}" for j, p in enumerate(pts)))
    if done:
        L.append("  Earlier rounds: " + "; ".join(done) + f". Group score so far: {s.group_score:g}." if coop
                 else "  Earlier rounds: " + "; ".join(done) + ".")
    return "\n".join(L)
