"""The replay-log document must cover everything the engine actually writes."""
import pathlib
import re

from wingsim.agents.random import RandomAgent, RandomGroupPolicy
from wingsim.engine import api
from wingsim.engine.log import GameLog, card_reference, export, read_log, replay
from wingsim.game import play_game

from . import reduce_log

ROOT = pathlib.Path(__file__).resolve().parents[2]
DOC = (ROOT / "docs" / "replay-log-format.md").read_text()


def logged(seed, n, plugins, snapshots):
    cfg = api.GameConfig(n, plugins, record_events=True)
    log = GameLog(cfg, seed, [{"type": "random"}] * n, snapshots=snapshots)
    play_game(cfg, seed, [RandomAgent(seed + i) for i in range(n)], RandomGroupPolicy(seed), log=log)
    return log.lines


def section(title):
    start = DOC.index(title)
    nxt = re.search(r"\n#{2,3} ", DOC[start + len(title):])
    return DOC[start:start + len(title) + (nxt.start() if nxt else len(DOC))]


def test_document_covers_every_event_decision_and_field():
    events, kinds, tags = {}, set(), {}
    keys = {"header": set(), "snapshot": set(), "decision": set(), "state": set(), "player": set(), "slot": set()}
    for seed in range(60):
        lines = logged(seed, 2 + seed % 4, {"coop_goals": {}} if seed % 2 else None, "turn")
        for ln in lines:
            if ln["t"] == "event":
                events.setdefault(ln["e"], set()).update(k for k in ln if k not in ("t", "seq", "e"))
            elif ln["t"] == "decision":
                kinds.add(ln["kind"])
                tags.setdefault(ln["kind"], set()).update(o[0] for o in ln["options"])
                keys["decision"].update(ln)
            elif ln["t"] == "snapshot":
                keys["snapshot"].update(ln)
                keys["state"].update(ln["state"])
                for pl in ln["state"]["players"]:
                    keys["player"].update(pl)
                    for row in pl["board"]:
                        for slot in row:
                            keys["slot"].update(slot)
            else:
                keys["header"].update(ln)
    assert len(events) >= 25 and len(kinds) >= 24
    table = section("### 4.6 Events")
    for name, fields in events.items():
        row = next((r for r in table.splitlines() if r.startswith(f"| `{name}` |")), None)
        assert row, f"event {name} is not documented"
        for f in fields:
            assert f"`{f}`" in row, f"event {name}: field {f} is not documented"
    table = section("### 4.5 Decision kinds and option shapes")
    for kind in kinds:
        row = next((r for r in table.splitlines() if r.startswith(f"| `{kind}` |")), None)
        assert row, f"decision kind {kind} is not documented"
        for tag in tags[kind]:
            assert f'["{tag}"' in row, f"decision {kind}: option {tag} is not documented"
    for part, title in (("header", "### 4.1"), ("snapshot", "### 4.2"), ("decision", "### 4.3"),
                        ("state", "### 5.1"), ("player", "### 5.2"), ("slot", "### 5.2")):
        text = section(title)
        for k in keys[part] - {"t"}:
            assert f"`{k}`" in text or f'"{k}"' in text, f"{part} field {k} is not documented"


def test_samples_match_the_document_and_replay(tmp_path):
    samples = ROOT / "docs" / "samples"
    for name, mode in (("coop-3p-greedy-every-decision", "decision"), ("baseline-2p-greedy-per-turn", "turn")):
        assert f"`{name}.jsonl.gz`" in DOC or name in DOC
        lines = read_log(samples / f"{name}.jsonl.gz")
        assert lines[0]["version"] == 2 and lines[0]["snapshots"] == mode
        assert api.is_over(replay(lines))
        decisions = [ln for ln in lines if ln["t"] == "decision"]
        assert all(len(d["labels"]) == len(d["options"]) for d in decisions)
        if mode == "decision":
            before = [ln["before_seq"] for ln in lines if ln["t"] == "snapshot"]
            assert before == [d["seq"] for d in decisions] + [None]
    out = export(samples / "baseline-2p-greedy-per-turn.jsonl.gz", tmp_path / "x.json")
    import json
    data = json.loads(pathlib.Path(out).read_text())
    assert set(data) == {"cards", "lines"} and len(data["cards"]["birds"]) == 180
    bird = next(iter(data["cards"]["birds"].values()))
    for field in bird:
        assert f"`{field}`" in section("## 7. Card reference"), field


def test_card_reference_names_what_each_bird_caches(db):
    ref = card_reference(db)["birds"]
    assert ref[str(db.by_name["Carolina Chickadee"].id)]["caches"] == "seed"
    assert ref[str(db.by_name["Barn Owl"].id)]["caches"] == "rodent"
    assert ref[str(db.by_name["Blue Jay"].id)]["caches"] == "seed"
    assert ref[str(db.by_name["Mallard"].id)]["caches"] is None


def _play_logged(seed, n, plugins, snapshots, small_decks=False):
    """Like logged(), but optionally with most of both decks moved to their discard piles, so that games
    reshuffle them."""
    from wingsim.engine.state import GROUP
    cfg = api.GameConfig(n, plugins, record_events=True)
    log = GameLog(cfg, seed, [{"type": "random"}] * n, snapshots=snapshots)
    s = api.new_game(cfg, seed)
    if small_decks:
        s.discard, s.deck = s.deck[:-12], s.deck[-12:]
        s.bonus_discard, s.bonus_deck = s.bonus_deck[:-1], s.bonus_deck[-1:]
    agents, group = [RandomAgent(seed + i) for i in range(n)], RandomGroupPolicy(seed)
    log.events(s)
    log.maybe_snapshot(s)
    while (d := api.pending_decision(s)) is not None:
        choice = (group if d.player == GROUP else agents[d.player]).choose(api.observe(s, d.player), d)
        log.decision(s, d, choice, None)
        s = api.apply(s, d, choice)
        log.events(s)
        log.maybe_snapshot(s)
    return log.lines


def test_events_rebuild_every_snapshot():
    """Section 8's rules, applied to the events after one snapshot, give exactly the next snapshot."""
    seen = set()
    for seed in range(16):
        n = 2 + seed % 4
        plugins = {"coop_goals": {}} if seed % 2 else None
        for small in (False, True):
            lines = _play_logged(seed, n, plugins, "decision" if seed % 4 < 2 else "turn", small_decks=small)
            assert reduce_log.check(lines) > 20
            seen.update(ln["e"] for ln in lines if ln["t"] == "event")
            final = lines[-1]
            assert final["t"] == "snapshot" and final["goal_counts"] is None
            scored = next(ln for ln in lines if ln["t"] == "event" and ln["e"] == "final_scoring")["scores"]
            assert final["scores"]["team_total"] == scored["team_total"]
    assert {"bonus_drawn", "bonus_reshuffled", "deck_reshuffled", "tray_cleared", "turn_end"} <= seen


def test_samples_rebuild_from_events():
    for path in sorted((ROOT / "docs" / "samples").glob("*.jsonl.gz")):
        assert reduce_log.check(read_log(path)) > 20, path.name


def test_set_aside_cards_are_in_the_state(db):
    from wingsim.engine.state import state_to_dict
    s = api.new_game(api.GameConfig(3), 4)
    s.stack.append(("bonus_keep", 1, (1003, 1007)))
    s.stack.append(("draft", 0, (12, 40), 2))
    assert state_to_dict(s)["set_aside"] == {"birds": [12, 40], "bonus": [1003, 1007]}
