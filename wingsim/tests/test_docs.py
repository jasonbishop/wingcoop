"""The replay-log document must cover everything the engine actually writes."""
import pathlib
import re

from wingsim.agents.random import RandomAgent, RandomGroupPolicy
from wingsim.engine import api
from wingsim.engine.log import GameLog, card_reference, export, read_log, replay
from wingsim.game import play_game

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
