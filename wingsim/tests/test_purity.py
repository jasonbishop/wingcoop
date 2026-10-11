"""Agent purity rules (hard requirements).

1. Agent code must not branch on a card's identity, name, power text or analysis tags.
2. Agents must not check which plugins are active (group policies excepted).
3. The agents package must not import analysis.
"""
import ast
import pathlib
import re
import subprocess
import sys

import wingsim.agents as agents_pkg
from wingsim.analysis import tags

AGENTS = pathlib.Path(agents_pkg.__file__).parent
FILES = sorted(AGENTS.glob("*.py"))


def test_agents_never_import_analysis_statically():
    assert FILES
    for path in FILES:
        for node in ast.walk(ast.parse(path.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom):
                names = [(node.module or "")] + [a.name for a in node.names]
            for name in names:
                assert "analysis" not in name.split("."), f"{path.name} imports {name}"


def test_importing_agents_does_not_load_analysis():
    modules = [f"wingsim.agents.{p.stem}" for p in FILES if p.stem != "__init__"]
    code = ("import sys, importlib\n"
            f"[importlib.import_module(m) for m in {modules!r}]\n"
            "bad = [m for m in sys.modules if m.startswith('wingsim.analysis')]\n"
            "sys.exit(1 if bad else 0)\n")
    assert subprocess.run([sys.executable, "-c", code]).returncode == 0


def test_no_bird_names_power_text_or_tags_in_agent_code(db):
    source = {p.name: p.read_text() for p in FILES}
    names = [b.name for b in db.birds.values()]
    assert len(names) == 180
    for fname, text in source.items():
        lowered = text.lower()
        for name in names:
            assert name.lower() not in lowered, f"{fname} mentions the bird {name!r}"
        for tag in ("shares_benefit", "pink_reactive", "tucker", "cacher"):
            assert tag not in lowered, f"{fname} mentions the analysis tag {tag!r}"
        for forbidden in (".name", ".text", ".spec", ".steps", ".trigger", ".timing", "by_name", "effects.json"):
            assert forbidden not in text, f"{fname} reads {forbidden}"


def test_agents_do_not_check_which_plugins_are_active():
    pattern = re.compile(r"\.plugins\b|\.variant\b|plugin_tags|scoring_plugins|coop")
    for path in FILES:
        if path.name == "group_policies.py":       # the exception: they answer the plugin's own decisions
            continue
        hits = pattern.findall(path.read_text())
        assert not hits, f"{path.name} looks at plugins: {hits}"


def test_tags_are_derived_from_specs(db):
    shared = tags.birds_with("shares_benefit")
    assert len(shared) == 20                         # the spec's "about 20"
    names = {db.birds[c].name for c in shared}
    assert {"Osprey", "Anna's Hummingbird", "Hermit Thrush", "American Oystercatcher", "Canvasback"} <= names
    assert "Mallard" not in names
    assert len(tags.birds_with("pink_reactive")) == 12
    assert len(tags.birds_with("predator")) == 23
    assert "tucker" in tags.all_tags()[db.by_name["American Coot"].id]
    assert "cacher" in tags.all_tags()[db.by_name["Blue Jay"].id]
    assert tags.all_tags()[db.by_name["American Woodcock"].id] == frozenset()
