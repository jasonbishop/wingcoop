"""Milestone 1: card data and effect specs."""
import json
import pathlib

from wingsim.data import build

DATA = pathlib.Path(build.__file__).parent


def test_counts(db):
    assert len(db.birds) == 180
    assert sum(1 for b in db.birds.values() if b.spec) == 174
    assert len(db.goals) == 16 and len(db.tiles) == 8
    # wingsearch tags one fan-made bonus card as core; the published base game has 26.
    assert len(db.bonus) == 26
    assert not any(c.name.startswith("[Fan Made]") for c in db.bonus.values())


def test_every_power_has_a_spec_and_effects_json_is_current():
    cards, effects = build.build()
    assert json.loads((DATA / "effects.json").read_text()) == effects
    for b in cards["birds"]:
        assert (b["text"] is None) == (str(b["id"]) not in effects), b["name"]


def test_distinct_texts_and_templates():
    effects = json.loads((DATA / "effects.json").read_text())
    assert len({e["text"] for e in effects.values()}) == 70
    assert len({e["template"] for e in effects.values()}) == 43
    for e in effects.values():  # one text always maps to one template and one spec
        assert e["spec"]["timing"] in ("brown", "white", "pink")
        assert (e["spec"]["timing"] == "pink") == ("trigger" in e["spec"])


def test_timing_matches_card_colour(db):
    raw = {b["id"]: b for b in json.loads((DATA / "raw" / "master.json").read_text()) if b["Set"] == "core"}
    for b in db.birds.values():
        assert b.timing == raw[b.id]["Color"]


def test_goal_tiles_pair_both_faces(db):
    faces = [g for t in db.tiles for g in t]
    assert sorted(faces) == sorted(db.goals)
    kinds = {frozenset((db.goals[a].kind, db.goals[b].kind)) for a, b in db.tiles}
    assert frozenset(("total_birds", "egg_sets")) in kinds
    assert frozenset(("birds_in_habitat", "eggs_in_habitat")) in kinds
    assert frozenset(("nest_birds_with_egg", "eggs_in_nest")) in kinds


def test_bonus_scoring_tiers(db):
    by = {c.name: c for c in db.bonus.values()}
    assert [by["Backyard Birder"].points(n) for n in (4, 5, 6, 7)] == [0, 3, 3, 6]
    assert [by["Forester"].points(n) for n in (2, 3, 4, 5, 6)] == [0, 4, 4, 8, 8]
    assert by["Falconer"].points(3) == 6


def test_bonus_columns_follow_rulings(db):
    by = {c.name: c.id for c in db.bonus.values()}

    def counts(bird, card):
        return by[card] in db.by_name[bird].bonus

    assert counts("Greater Prairie-Chicken", "Cartographer")      # ruling 02d
    assert not counts("Burrowing Owl", "Anatomist")               # ruling 20190522
    assert not counts("Barred Owl", "Photographer")               # ruling 20190724
    assert counts("Golden Eagle", "Photographer")                 # ruling 20190729
    assert not counts("Black-Billed Magpie", "Falconer")          # ruling 20210321
    assert not counts("American Crow", "Rodentologist")           # ruling 20200703
    assert counts("American Crow", "Omnivore Specialist")
    assert counts("Horned Lark", "Bird Counter")                  # ruling 20200405
    assert db.by_name["Spotted Sandpiper"].vp == 5                # ruling 02f
    assert db.by_name["Bronzed Cowbird"].egg_limit == 0           # ruling 20190718
