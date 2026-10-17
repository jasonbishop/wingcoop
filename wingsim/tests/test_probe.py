"""Asking a logged decision again: the exact position and prompt, with settings changed."""
import argparse
import json
import sys

from wingsim.agents import llm
from wingsim.agents.base import Objective
from wingsim.agents.greedy import GreedyAgent
from wingsim.agents.llm import LLMAgent
from wingsim.analysis import probe
from wingsim.engine import api
from wingsim.engine.log import GameLog
from wingsim.game import play_game

from .test_llm import PLANNED, endpoint  # noqa: F401  (the fixture)


def logged_game(url, tmp_path):
    cfg = api.GameConfig(2, record_events=True)
    a = LLMAgent("test/model", base_url=url, prompt="plan", plan=True, outcomes=True, compact=True)
    g = GreedyAgent(seed=1)
    a.start(cfg, 0, Objective(0.0, 2))
    g.start(cfg, 1, Objective(0.0, 2))
    seats = [{"type": x.type, "settings": x.settings(), "w": 0.0, "group_share": False} for x in (a, g)]
    log = GameLog(cfg, 2, seats, snapshots="decision")
    play_game(cfg, 2, [a, g], log=log)
    return log.write(tmp_path / "game.jsonl.gz"), log.lines


def test_rebuilt_prompts_match_the_log(endpoint, tmp_path):
    e = endpoint([PLANNED])
    path, lines = logged_game(e.url, tmp_path)
    args = argparse.Namespace(model=None, base_url=None, reasoning="logged", thinking="logged", plan="logged",
                              extra_body=None, timeout=60, budget_usd=None, outcomes=None, goal_status=None,
                              temperature=0.0, max_tokens=None)
    asked = [ln for ln in lines if ln["t"] == "decision" and (ln.get("info") or {}).get("prompt")]
    assert any("THIS TURN SO FAR" in ln["info"]["prompt"] for ln in asked)
    for ln in asked[::7]:
        cfg, s, d, t = probe.position(lines, seq=ln["seq"])
        a, _ = probe.build_agent(lines[0], 0, args)
        a.start(cfg, 0, Objective(0.0, 2))
        a.current_plan = ln["info"].get("plan")
        a.turn_notes = probe.turn_notes(lines, t)
        assert a.build_prompt(api.observe(s, 0), d)[0] == ln["info"]["prompt"]
        assert a.system == lines[0]["seats"][0]["settings"]["system_prompt"]


def test_replays_with_changed_settings_are_saved(endpoint, tmp_path, monkeypatch, capsys):
    e = endpoint([PLANNED])
    path, lines = logged_game(e.url, tmp_path)
    sent = len(e.requests)
    out = tmp_path / "probe.jsonl"
    monkeypatch.setattr(sys, "argv", ["probe", str(path), "--turn", "5", "-n", "2", "--reasoning", "full",
                                      "--out", str(out)])
    probe.main()
    rows = [json.loads(x) for x in out.read_text().splitlines()]
    assert [r["t"] for r in rows] == ["probe", "reply", "reply"]
    assert rows[0]["settings"]["reasoning"] == "full" and llm.PLAN_ASK_FULL in rows[0]["prompt"]
    assert all(r["chosen"] == 1 and r["plan_updated"].startswith("Engine: forest") for r in rows[1:])
    body = e.requests[sent]["body"]
    assert body["temperature"] == 0.7 and llm.ANSWER_FULL in body["messages"][0]["content"]
    assert "2 replies" in capsys.readouterr().out
