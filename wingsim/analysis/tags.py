"""Analysis tags, derived automatically from the effect specs.

These exist only for analysing results. Agent code must never import this
module (enforced by tests/test_purity.py).
"""
from ..engine.cards import db


def _walk(steps):
    for step in steps:
        yield step
        if "then" in step:
            yield from _walk(step["then"])
        if isinstance(step.get("if"), dict):
            yield from _walk([step["if"]])


def tags_for(bird):
    """Tags for one bird, from its JSON effect spec."""
    if not bird.spec:
        return frozenset()
    steps = list(_walk(bird.spec["steps"]))
    out = set()
    if any(s.get("who", "self") != "self" or s["op"] == "draft_cards" for s in steps):
        out.add("shares_benefit")
    if bird.spec["timing"] == "pink":
        out.add("pink_reactive")
    if bird.predator or any(s["op"] in ("roll_dice_not_in_feeder", "look_at_deck_card") for s in steps):
        out.add("predator")
    if any(s["op"] in ("tuck", "look_at_deck_card") for s in steps):
        out.add("tucker")
    if any(s["op"] == "cache_food" or s.get("may_cache") for s in steps):
        out.add("cacher")
    return frozenset(out)


_TAGS = None


def all_tags():
    """{bird id: frozenset of tags} for every core bird."""
    global _TAGS
    if _TAGS is None:
        _TAGS = {cid: tags_for(b) for cid, b in db().birds.items()}
    return _TAGS


def birds_with(tag):
    return sorted(cid for cid, t in all_tags().items() if tag in t)
