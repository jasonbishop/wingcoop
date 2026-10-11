"""Build cards.json and effects.json from the vendored wingsearch data.

Usage: python -m wingsim.data.build

Step 1: each core power text is matched against the regex templates below and
        turned into a structured effect spec.
Step 2: effect_overrides.yaml supplies hand-written specs for any text no
        template matches.
Step 3: effects.json is written for human review. The build fails if any core
        bird with a power has no spec.
"""
import json
import pathlib
import re
import sys

HERE = pathlib.Path(__file__).parent
RAW = HERE / "raw"
COMMIT = "43e5036"

FOODS = ("invertebrate", "seed", "fish", "fruit", "rodent")
FOOD_COLUMNS = ("Invertebrate", "Seed", "Fish", "Fruit", "Rodent")
HABITATS = ("forest", "grassland", "wetland")
HABITAT_COLUMNS = ("Forest", "Grassland", "Wetland")
NESTS = ("bowl", "cavity", "ground", "platform")

F = "(invertebrate|seed|fish|fruit|rodent)"
N = "(bowl|cavity|ground|platform)"
H = "(forest|grassland|wetland)"

TUCK_HAND = {"op": "tuck", "from": "hand", "n": 1}


def _tuck_then(*then):
    return [{"op": "if_then", "if": dict(TUCK_HAND), "then": list(then)}]


# (template name, regex, builder(match) -> steps or (trigger, steps))
TEMPLATES = [
    ("all_draw_deck", rf"All players draw (\d+) \[card\] from the deck\.",
     lambda m: [{"op": "draw_cards", "from": "deck", "n": int(m[1]), "who": "all"}]),
    ("all_gain_supply", rf"All players gain (\d+) \[{F}\] from the supply\.",
     lambda m: [{"op": "gain_food", "from": "supply", "food": [m[2]], "n": int(m[1]), "who": "all"}]),
    ("all_lay_nest_plus_one",
     rf"All players lay (\d+) \[egg\] on any 1 \[{N}\] bird\. You may lay 1 \[egg\] on 1 additional \[{N}\] bird\.",
     lambda m: [
         {"op": "lay_eggs", "n": int(m[1]), "on": "any", "nest": m[2], "who": "all", "may_decline": True},
         {"op": "lay_eggs", "n": 1, "on": "any", "nest": m[3], "who": "self", "different_bird": True,
          "may_decline": True},
     ]),
    ("cache_supply", rf"Cache (\d+) \[{F}\] from the supply on this bird\.",
     lambda m: [{"op": "cache_food", "food": m[2], "n": int(m[1])}]),
    ("discard_egg_other_gain_wild",
     r"Discard 1 \[egg\] from any of your other birds to gain (\d+) \[wild\] from the supply\.",
     lambda m: [{"op": "discard_to_gain", "cost": {"what": "egg", "from": "other_birds"},
                 "then": [{"op": "gain_food", "from": "supply", "food": "any", "n": int(m[1]), "who": "self"}]}]),
    ("discard_egg_draw", r"Discard 1 \[egg\] to draw (\d+) \[card\]\.",
     lambda m: [{"op": "discard_to_gain", "cost": {"what": "egg", "from": "any_bird"},
                 "then": [{"op": "draw_cards", "from": "any", "n": int(m[1]), "who": "self"}]}]),
    ("discard_food_tuck_deck", rf"Discard 1 \[{F}\] to tuck (\d+) \[card\] from the deck behind this bird\.",
     lambda m: [{"op": "discard_to_gain", "cost": {"what": "food", "food": [m[1]]},
                 "then": [{"op": "tuck", "from": "deck", "n": int(m[2])}]}]),
    ("draw", r"Draw (\d+) \[card\]\.",
     lambda m: [{"op": "draw_cards", "from": "any", "n": int(m[1]), "who": "self"}]),
    ("draw_discard_end_of_turn",
     r"Draw (\d+) \[card\]\. If you do, discard 1 \[card\] from your hand at the end of your turn\.",
     lambda m: [{"op": "draw_cards", "from": "any", "n": int(m[1]), "who": "self", "discard_eot": 1}]),
    ("each_gain_die_in_order",
     r"Each player gains (\d+) \[die\] from the birdfeeder, starting with the player of your choice\.",
     lambda m: [{"op": "gain_food", "from": "feeder", "food": "any", "n": int(m[1]),
                 "who": "each_from_feeder_in_order", "may_decline": True}]),
    ("gain_die", r"Gain (\d+) \[die\] from the birdfeeder\.",
     lambda m: [{"op": "gain_food", "from": "feeder", "food": "any", "n": int(m[1]), "who": "self"}]),
    ("gain_supply", rf"Gain (\d+) \[{F}\] from the supply\.",
     lambda m: [{"op": "gain_food", "from": "supply", "food": [m[2]], "n": int(m[1]), "who": "self"}]),
    ("gain_feeder_if_available", rf"Gain (\d+) \[{F}\] from the birdfeeder, if available\.",
     lambda m: [{"op": "gain_food", "from": "feeder", "food": [m[2]], "n": int(m[1]), "who": "self"}]),
    ("gain_feeder_either_if_available", rf"Gain (\d+) \[{F}\] or \[{F}\] from the birdfeeder, if available\.",
     lambda m: [{"op": "gain_food", "from": "feeder", "food": [m[2], m[3]], "n": int(m[1]), "who": "self"}]),
    ("gain_feeder_may_cache",
     rf"Gain (\d+) \[{F}\] from the birdfeeder, if available\. You may cache it on this bird\.",
     lambda m: [{"op": "gain_food", "from": "feeder", "food": [m[2]], "n": int(m[1]), "who": "self",
                 "may_cache": True}]),
    ("move_if_rightmost",
     r"If this bird is to the right of all other birds in its habitat, move it to another habitat\.",
     lambda m: [{"op": "move_bird", "if": "rightmost"}]),
    ("lay_any", r"Lay (\d+) \[egg\] on any bird\.",
     lambda m: [{"op": "lay_eggs", "n": int(m[1]), "on": "any", "who": "self"}]),
    ("lay_this", r"Lay (\d+) \[egg\] on this bird\.",
     lambda m: [{"op": "lay_eggs", "n": int(m[1]), "on": "this", "who": "self"}]),
    ("look_at_deck_tuck_if_small",
     r"Look at a \[card\] from the deck\. If less than (\d+)cm, tuck it behind this bird\. If not, discard it\.",
     lambda m: [{"op": "look_at_deck_card", "max_wingspan": int(m[1])}]),
    ("fewest_gain_die", rf"Player\(s\) with the fewest birds in their \[{H}\] gain (\d+) \[die\] from birdfeeder\.",
     lambda m: [{"op": "gain_food", "from": "feeder", "food": "any", "n": int(m[2]),
                 "who": "fewest_in_habitat", "habitat": m[1]}]),
    ("fewest_draw", rf"Player\(s\) with the fewest birds in their \[{H}\] draw (\d+) \[card\]\.",
     lambda m: [{"op": "draw_cards", "from": "any", "n": int(m[2]), "who": "fewest_in_habitat", "habitat": m[1]}]),
    ("repeat_predator", r"Repeat 1 \[predator\] power in this habitat\.",
     lambda m: [{"op": "repeat_power", "filter": "predator"}]),
    ("repeat_brown", r"Repeat a brown power on another bird in this habitat\.",
     lambda m: [{"op": "repeat_power", "filter": "brown"}]),
    ("roll_dice_cache",
     rf"Roll all dice not in birdfeeder\. If any are \[{F}\], cache 1 \[{F}\] from the supply on this bird\.",
     lambda m: [{"op": "roll_dice_not_in_feeder", "food": m[1],
                 "then": [{"op": "cache_food", "food": m[2], "n": 1}]}]),
    ("trade_food", r"Trade 1 \[wild\] for any other type from the supply\.",
     lambda m: [{"op": "discard_to_gain", "cost": {"what": "food", "food": "any"},
                 "then": [{"op": "gain_food", "from": "supply", "food": "any_other", "n": 1, "who": "self"}]}]),
    ("tuck_hand_then_draw", r"Tuck 1 \[card\] from your hand behind this bird\. If you do, draw (\d+) \[card\]\.",
     lambda m: _tuck_then({"op": "draw_cards", "from": "any", "n": int(m[1]), "who": "self"})),
    ("tuck_hand_then_gain",
     rf"Tuck 1 \[card\] from your hand behind this bird\. If you do, gain (\d+) \[{F}\] from the supply\.",
     lambda m: _tuck_then({"op": "gain_food", "from": "supply", "food": [m[2]], "n": int(m[1]), "who": "self"})),
    ("tuck_hand_then_gain_either",
     rf"Tuck 1 \[card\] from your hand behind this bird\. If you do, gain (\d+) \[{F}\] or \[{F}\] from the supply\.",
     lambda m: _tuck_then({"op": "gain_food", "from": "supply", "food": [m[2], m[3]], "n": int(m[1]),
                           "who": "self"})),
    ("tuck_hand_then_lay_any",
     r"Tuck 1 \[card\] from your hand behind this bird\. If you do, lay (\d+) \[egg\] on any bird\.",
     lambda m: _tuck_then({"op": "lay_eggs", "n": int(m[1]), "on": "any", "who": "self"})),
    ("tuck_hand_then_may_lay_this",
     r"Tuck 1 \[card\] from your hand behind this bird\. If you do, you may also lay (\d+) \[egg\] on this bird\.",
     lambda m: _tuck_then({"op": "lay_eggs", "n": int(m[1]), "on": "this", "who": "self", "optional": True})),
    # pink: once between turns
    ("pink_play_bird_gain_supply",
     rf"When another player plays a bird in their \[{H}\], gain (\d+) \[{F}\] from the supply\.",
     lambda m: ({"on": "on_other_player_play_bird_in", "habitat": m[1]},
                [{"op": "gain_food", "from": "supply", "food": [m[3]], "n": int(m[2]), "who": "self"}])),
    ("pink_play_bird_tuck",
     rf"When another player plays a bird in their \[{H}\], tuck (\d+) \[card\] from your hand behind this bird\.",
     lambda m: ({"on": "on_other_player_play_bird_in", "habitat": m[1]},
                [{"op": "tuck", "from": "hand", "n": int(m[2])}])),
    ("pink_gain_food_cache",
     rf"When another player takes the “gain food” action, if they gain any number of \[{F}\], "
     rf"cache (\d+) \[{F}\] from the supply on this bird\.",
     lambda m: ({"on": "on_other_player_gain_food", "food": m[1]},
                [{"op": "cache_food", "food": m[3], "n": int(m[2])}])),
    ("pink_lay_eggs_lay_nest",
     rf"When another player takes the “lay eggs” action, lay (\d+) \[egg\] on a bird with a \[{N}\] nest\.",
     lambda m: ({"on": "on_other_player_lay_eggs"},
                [{"op": "lay_eggs", "n": int(m[1]), "on": "any", "nest": m[2], "who": "self"}])),
    ("pink_lay_eggs_lay_other_nest",
     rf"When another player takes the “lay eggs” action, lay (\d+) \[egg\] on another bird with a \[{N}\] nest\.",
     lambda m: ({"on": "on_other_player_lay_eggs"},
                [{"op": "lay_eggs", "n": int(m[1]), "on": "any", "nest": m[2], "who": "self",
                  "other_than_this": True}])),
    ("pink_predator_gain_die",
     r"When another player's \[predator\] succeeds, gain (\d+) \[die\] from the birdfeeder\.",
     lambda m: ({"on": "on_other_player_predator_success"},
                [{"op": "gain_food", "from": "feeder", "food": "any", "n": int(m[1]), "who": "self"}])),
    # white: when played
    ("draw_bonus_keep", r"Draw (\d+) new bonus cards and keep (\d+)\.",
     lambda m: [{"op": "draw_bonus_keep", "draw": int(m[1]), "keep": int(m[2])}]),
    ("draw_tray_all", r"Draw the 3 face-up \[card\] in the bird tray\.",
     lambda m: [{"op": "draw_cards", "from": "tray", "n": "all", "who": "self"}]),
    ("gain_all_feeder", rf"Gain all \[{F}\] that are in the birdfeeder\.",
     lambda m: [{"op": "gain_food", "from": "feeder", "food": [m[1]], "n": "all", "who": "self"}]),
    ("lay_each_nest", rf"Lay (\d+) \[egg\] on each of your birds with a \[{N}\] nest\.",
     lambda m: [{"op": "lay_eggs", "n": int(m[1]), "on": "each", "nest": m[2], "who": "self"}]),
    ("play_additional_same_habitat", r"Play an additional bird in this bird's habitat\. Pay its normal cost\.",
     lambda m: [{"op": "play_additional_bird", "habitat": "this"}]),
    ("play_additional_in_habitat", rf"Play an additional bird in your \[{H}\]\. Pay its normal cost\.",
     lambda m: [{"op": "play_additional_bird", "habitat": m[1]}]),
]


def convert(text, color, overrides):
    """Return (template name, spec) for one power text, or (None, None)."""
    if text in overrides:
        o = overrides[text]
        spec = {"timing": color, "steps": o["steps"]}
        if "trigger" in o:
            spec["trigger"] = o["trigger"]
        return "override:" + o["name"], spec
    for name, pattern, build in TEMPLATES:
        m = re.fullmatch(pattern, text)
        if not m:
            continue
        built = build(m)
        if isinstance(built, tuple):
            trigger, steps = built
            return name, {"timing": color, "trigger": trigger, "steps": steps}
        return name, {"timing": color, "steps": built}
    return None, None


def parse_vp(text):
    m = re.fullmatch(r"(\d+)\[point\] per bird", text)
    if m:
        return {"per": int(m[1])}
    tiers = []
    for part in text.split(";"):
        m = re.fullmatch(r"\s*(\d+)(?: to (\d+)|\+)? birds: (\d+)\[point\]", part)
        if not m:
            raise ValueError(f"cannot parse bonus VP text: {text!r}")
        tiers.append([int(m[1]), int(m[3])])
    # A count scores the highest tier whose lower bound it reaches. The source
    # text for Backyard Birder reads "5 to 6 birds ... 6+ birds", so the upper
    # tier starts one above the lower tier's printed range.
    first = re.match(r"\s*(\d+) to (\d+)", text)
    if first and len(tiers) == 2 and tiers[1][0] <= int(first[2]):
        tiers[1][0] = int(first[2]) + 1
    return {"tiers": tiers}


# Bonus cards whose count comes from the game state rather than a bird column.
STATE_BONUS = {
    "Breeding Manager": "birds_with_4_eggs",
    "Ecologist": "birds_in_smallest_habitat",
    "Oologist": "birds_with_egg",
    "Visionary Leader": "cards_in_hand",
}
BONUS_COLUMN = {"Omnivore Specialist": "Omnivore Expert"}


def parse_goal(text):
    t = re.sub(r"[\[\]]", "", text).strip()
    m = re.fullmatch(r"bird in (forest|grassland|wetland)", t)
    if m:
        return "birds_in_habitat", m[1]
    m = re.fullmatch(r"egg in (forest|grassland|wetland)", t)
    if m:
        return "eggs_in_habitat", m[1]
    m = re.fullmatch(r"(bowl|cavity|ground|platform) bird with egg", t)
    if m:
        return "nest_birds_with_egg", m[1]
    m = re.fullmatch(r"egg in (bowl|cavity|ground|platform)", t)
    if m:
        return "eggs_in_nest", m[1]
    if t.startswith("sets of egg"):
        return "egg_sets", None
    if t == "total bird":
        return "total_birds", None
    raise ValueError(f"cannot parse goal: {text!r}")


def build():
    import yaml

    master = [b for b in json.loads((RAW / "master.json").read_text()) if b.get("Set") == "core"]
    bonus_raw = [b for b in json.loads((RAW / "bonus.json").read_text()) if b.get("Set") == "core"]
    goals_raw = [g for g in json.loads((RAW / "goals.json").read_text()) if g.get("Set") == "core"]
    overrides = {o["text"]: o for o in yaml.safe_load((HERE / "effect_overrides.yaml").read_text())["overrides"]}

    # Fan-made cards are tagged Set == "core" in wingsearch but are not part of
    # the published base game, so they are left out.
    excluded_bonus = [b["Bonus card"] for b in bonus_raw if b["Bonus card"].startswith("[Fan Made]")]
    bonus_raw = [b for b in bonus_raw if b["Bonus card"] not in excluded_bonus]

    bonus = []
    for b in sorted(bonus_raw, key=lambda b: b["id"]):
        name = b["Bonus card"]
        entry = {"id": b["id"], "name": name, "condition": b["Condition"], "vp_text": b["VP"]}
        entry.update(parse_vp(b["VP"]))
        if name in STATE_BONUS:
            entry["count"] = STATE_BONUS[name]
        else:
            column = BONUS_COLUMN.get(name, name)
            if column not in master[0]:
                raise SystemExit(f"bonus card {name!r} has no bird column in master.json")
            entry["count"] = "column"
            entry["column"] = column
        bonus.append(entry)

    birds, effects, missing = [], {}, []
    for b in sorted(master, key=lambda b: b["id"]):
        text = b.get("Power text")
        bird = {
            "id": b["id"],
            "name": b["Common name"],
            "color": b.get("Color"),
            "vp": int(b["Victory points"]),
            "nest": b["Nest type"],
            "egg_limit": int(b["Egg limit"]),
            "wingspan": int(b["Wingspan"]),
            "habitats": [i for i, c in enumerate(HABITAT_COLUMNS) if b.get(c)],
            "cost": [int(b.get(c) or 0) for c in FOOD_COLUMNS],
            "wild": int(b.get("Wild (food)") or 0),
            "either": bool(b.get("/ (food cost)")),
            "total_cost": int(b["Total food cost"]),
            "predator": bool(b.get("Predator")),
            "flocking": bool(b.get("Flocking")),
            "bonus": [e["id"] for e in bonus if e["count"] == "column" and b.get(e["column"])],
            "text": text,
            "rulings": [r["id"] for r in (b.get("rulings") or [])],
        }
        birds.append(bird)
        if not text:
            continue
        name, spec = convert(text, b["Color"], overrides)
        if spec is None:
            missing.append((b["Common name"], text))
            continue
        effects[str(b["id"])] = {"name": b["Common name"], "text": text, "template": name, "spec": spec}

    if missing:
        for name, text in missing:
            print(f"NO SPEC: {name}: {text}", file=sys.stderr)
        raise SystemExit(f"{len(missing)} core birds with a power have no effect spec")

    # Pair goal faces into tiles: each face names the face on its other side.
    def norm(t):
        return re.sub(r"[\[\]]", "", t).strip().lower()

    by_text = {norm(g["Goal"]): g["id"] for g in goals_raw}
    goals, tile_of, tiles = [], {}, []
    for g in sorted(goals_raw, key=lambda g: g["id"]):
        other = by_text.get(norm(g["Reverse"]))
        if other is None:  # the source has a typo in one Reverse field; use the other side's pointer
            other = next(o["id"] for o in goals_raw if norm(o["Reverse"]) == norm(g["Goal"]))
        if g["id"] not in tile_of:
            tile_of[g["id"]] = tile_of[other] = len(tiles)
            tiles.append([g["id"], other])
        kind, param = parse_goal(g["Goal"])
        goals.append({"id": g["id"], "text": g["Goal"], "kind": kind, "param": param, "tile": tile_of[g["id"]]})

    cards = {"source": "navarog/wingsearch", "commit": COMMIT, "birds": birds, "bonus": bonus,
             "goals": goals, "tiles": tiles, "excluded_bonus": excluded_bonus}
    (HERE / "cards.json").write_text(json.dumps(cards, indent=1, ensure_ascii=False) + "\n")
    (HERE / "effects.json").write_text(json.dumps(effects, indent=1, ensure_ascii=False) + "\n")

    used = sorted({e["template"] for e in effects.values()})
    print(f"birds: {len(birds)}  with powers: {len(effects)}  templates used: {len(used)}  "
          f"bonus: {len(bonus)} (excluded: {excluded_bonus})  goal faces: {len(goals)}  tiles: {len(tiles)}")
    unused = [t[0] for t in TEMPLATES if t[0] not in used]
    if unused:
        print("templates that matched nothing:", unused)
    return cards, effects


def review_sheet():
    """Write effects_review.md: one row per distinct power text for human review."""
    cards = json.loads((HERE / "cards.json").read_text())
    effects = json.loads((HERE / "effects.json").read_text())
    master = {b["id"]: b for b in json.loads((RAW / "master.json").read_text()) if b.get("Set") == "core"}
    groups = {}
    for bird in cards["birds"]:
        e = effects.get(str(bird["id"]))
        if e:
            groups.setdefault(e["text"], []).append(bird)
    out = ["# Effect specs for review", "",
           f"Generated from wingsearch commit `{COMMIT}`. One section per distinct power text "
           f"({len(groups)} texts, {len(effects)} birds). Check that each spec does what the printed text says.",
           ""]
    for text, group in sorted(groups.items(), key=lambda kv: (effects[str(kv[1][0]["id"])]["template"], kv[0])):
        e = effects[str(group[0]["id"])]
        out += [f"## {text}", "",
                f"- Template: `{e['template']}`",
                f"- Birds ({len(group)}): " + ", ".join(b["name"] for b in group),
                "", "```json", json.dumps(e["spec"], indent=1), "```", ""]
        seen = set()
        for bird in group:
            for r in master[bird["id"]].get("rulings") or []:
                if r["id"] in seen:
                    continue
                seen.add(r["id"])
                out.append(f"- Ruling {r['id']}: {re.sub(r'<[^>]+>', '', r['text'])}")
        out.append("")
    (HERE / "effects_review.md").write_text("\n".join(out))
    print(f"review sheet: {len(groups)} texts -> {HERE / 'effects_review.md'}")


if __name__ == "__main__":
    build()
    review_sheet()
