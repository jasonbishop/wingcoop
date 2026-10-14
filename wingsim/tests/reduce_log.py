"""A viewer's event reducer, written only from docs/replay-log-format.md (sections 4.6 and 8).

The tests use it to check that the events in a log are complete: applying the events
after one snapshot must give exactly the next snapshot. Anything this file has to
guess is a gap in the log or in the document.
"""
import copy

TURNS_PER_ROUND = (8, 7, 6, 5)
# State fields the reducer maintains; the engine internals are left out.
FIELDS = ("phase", "round", "turn_no", "first", "turn", "actions_left", "deck", "discard", "tray", "feeder",
          "bonus_deck", "bonus_discard", "tucked", "goals", "goal_points", "group_score", "goal_log", "players",
          "set_aside")


def view(state):
    out = {k: copy.deepcopy(state[k]) for k in FIELDS}
    out["coop.d"] = state["variant"].get("coop.d")
    return out


def _bird(s, p, bird):
    for row in s["players"][p]["board"]:
        for x in row:
            if x["bird"] == bird:
                return x
    raise AssertionError(f"bird {bird} is not on player {p}'s mat")


def _pop_deck(s, card):
    top = s["deck"].pop()
    assert card is None or top == card, f"expected {card} on top of the deck, found {top}"
    return top


def apply(s, e):
    k = e["e"]
    pl = s["players"][e["p"]] if "p" in e else None
    if k == "setup":
        s.update(goals=e["goals"], first=e["first"], tray=e["tray"], feeder=e["feeder"])
    elif k == "setup_kept_birds":
        s["discard"] += [c for c in pl["hand"] if c not in e["birds"]]
        pl["hand"] = list(e["birds"])
    elif k == "setup_discarded_food":
        for f in e["food"]:
            pl["food"][f] -= 1
    elif k == "bonus_drawn":
        for c in e["cards"]:
            assert s["bonus_deck"].pop() == c
            s["set_aside"]["bonus"].append(c)
    elif k == "bonus_reshuffled":
        assert sorted(e["deck"]) == sorted(s["bonus_discard"]) and len(e["deck"]) == e["cards"]
        s["bonus_deck"], s["bonus_discard"] = list(e["deck"]), []
    elif k == "bonus_kept":
        offered = s["set_aside"]["bonus"] if e["bonus"] in s["set_aside"]["bonus"] else pl["bonus"]
        for c in [e["bonus"]] + e["discarded"]:
            offered.remove(c)
        pl["bonus"].append(e["bonus"])
        s["bonus_discard"] += e["discarded"]
    elif k == "group_decision":
        if e["kind"] == "set_difficulty":
            s["coop.d"] = e["choice"][1]
    elif k == "round_start":
        r = e["round"]
        s.update(round=r, first=e["first"], turn=e["first"], phase="turns",
                 actions_left=[TURNS_PER_ROUND[r - 1]] * len(s["players"]))
    elif k == "turn_start":
        s.update(turn=e["p"], turn_no=e["turn_no"], round=e["round"])
        pl["pink_used"] = []
    elif k == "turn_end":
        s["actions_left"][e["p"]] -= 1
        s["turn"] = (e["p"] + 1) % len(s["players"])
        s["turn_no"] += 1
    elif k == "food_spent":
        for f, n in enumerate(e["food"]):
            pl["food"][f] -= n
    elif k == "egg_discarded":
        _bird(s, e["p"], e["bird"])["eggs"] -= 1
    elif k == "card_discarded":
        if e["why"] != "predator_miss":     # a missed predator's card was already off the deck
            pl["hand"].remove(e["bird"])
        s["discard"].append(e["bird"])
    elif k == "bird_played":
        pl["hand"].remove(e["bird"])
        pl["board"][e["habitat"]].insert(e["slot"], {"bird": e["bird"], "eggs": 0, "cached": 0, "tucked": 0})
    elif k == "die_taken":
        s["feeder"].remove(e["face"])
        pl["food"][e["food"]] += 1
    elif k == "feeder_reset":
        s["feeder"] = list(e["dice"])
    elif k == "food_gained":
        pl["food"][e["food"]] += e["n"]
    elif k == "cards_drawn":
        for c in e["birds"]:
            if e["source"] == "tray":
                s["tray"].remove(c)
            elif e["source"] == "deck":
                _pop_deck(s, c)
            else:
                s["set_aside"]["birds"].remove(c)
            pl["hand"].append(c)
    elif k == "card_set_aside":
        if e["source"] == "tray":
            s["tray"].remove(e["bird"])
        else:
            _pop_deck(s, e["bird"])
        s["set_aside"]["birds"].append(e["bird"])
    elif k == "cards_revealed":
        assert sorted(e["birds"]) == sorted(s["set_aside"]["birds"])
    elif k == "card_tucked":
        if e["source"] == "hand":
            pl["hand"].remove(e["card"])
        elif e["source"] == "deck":
            _pop_deck(s, e["card"])
        _bird(s, e["p"], e["bird"])["tucked"] += 1
        s["tucked"].append(e["card"])
    elif k == "eggs_laid":
        _bird(s, e["p"], e["bird"])["eggs"] += e["n"]
    elif k == "food_cached":
        _bird(s, e["p"], e["bird"])["cached"] += e["n"]
        if e["source"] == "player":
            pl["food"][e["food"]] -= e["n"]
    elif k == "power":
        if e["color"] == "pink" and e["bird"] not in pl["pink_used"]:
            pl["pink_used"].append(e["bird"])
    elif k == "predator":
        if e["kind"] == "look":
            _pop_deck(s, e["card"])
    elif k == "bird_moved":
        row = pl["board"][e["source"]]
        assert row[-1]["bird"] == e["bird"]
        pl["board"][e["to"]].append(row.pop())
    elif k == "tray_cleared":
        assert e["birds"] == s["tray"]
        s["discard"] += s["tray"]
        s["tray"] = []
    elif k == "tray_refill":
        for c in e["tray"][len(s["tray"]):]:
            _pop_deck(s, c)
        assert e["tray"][:len(s["tray"])] == s["tray"]
        s["tray"] = list(e["tray"])
    elif k == "deck_reshuffled":
        assert sorted(e["deck"]) == sorted(s["discard"]) and len(e["deck"]) == e["cards"]
        s["deck"], s["discard"] = list(e["deck"]), []
    elif k == "round_end":
        s["goal_log"].append([e["round"], e["counts"], e["points"], e["group_delta"], e["info"]])
        s["group_score"] = e["group_score"]
        s["goal_points"] = [a + b for a, b in zip(s["goal_points"], e["points"])]
        s["first"] = (s["first"] + 1) % len(s["players"])
        s["round"] = e["round"] + 1
    elif k == "final_scoring":
        s["phase"] = "over"
    elif k == "action":
        pass
    else:
        raise AssertionError(f"unknown event {k}")


def check(lines):
    """Rebuild every snapshot of a log from the one before it. Returns the number checked."""
    checked = 0
    s = want = None
    for ln in lines:
        if ln["t"] == "snapshot":
            if s is not None:
                want = view(ln["state"])
                for k in want:
                    assert s[k] == want[k], (f"snapshot before decision {ln['before_seq']}: {k} differs\n"
                                             f"  got  {s[k]}\n  want {want[k]}")
                checked += 1
            s = view(ln["state"])
        elif ln["t"] == "event" and s is not None:
            apply(s, ln)
    return checked
