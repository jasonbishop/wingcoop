"""Table talk: language-model seats leave short messages for each other."""
import argparse

from wingsim import runner
from wingsim.agents import llm
from wingsim.agents.base import Objective
from wingsim.analysis import probe
from wingsim.engine import api
from wingsim.engine.log import read_log

from .test_llm import endpoint  # noqa: F401  (the fixture)

TALKED = ("The plan holds.\nANSWER: 1\nPLAN:\nEngine: forest\nBonus target: none\nRound goal: birds\n"
          "Need next: fish\nPivot if: no fish\nEND PLAN\nSAY: I need fish, can you leave the fish die?")


def test_say_lines_are_read_and_kept_out_of_answers_and_plans():
    assert llm.parse_say(TALKED) == "I need fish, can you leave the fish die?"
    assert llm.parse_say("ANSWER: 2\nSAY: nothing") is None and llm.parse_say("ANSWER: 2") is None
    assert llm.parse_say("**SAY:** \"Taking eggs.\"\nANSWER: 1") == "Taking eggs."
    assert llm.parse_choice("SAY: I will take 3 eggs\nANSWER: 2", 4, strict=True) == 2
    assert llm.parse_choice("Go.\nSAY: I will take 3 eggs", 4) is None    # the number in a message is not an answer
    no_end = "ANSWER: 1\nPLAN:\nEngine: forest\nSAY: fish please"
    assert llm.parse_plan(no_end) == "Engine: forest" and llm.parse_say(no_end) == "fish please"


def talk_experiment(url, tmp_path):
    seat = {"type": "llm", "model": "test/model", "base_url": url, "prompt": "plan", "plan": True,
            "compact": True, "talk": True}
    exp = {"name": "talk", "seeds": {"start": 5, "count": 1}, "players": [3],
           "conditions": {"coop": {"plugins": {"coop_goals": {}}, "win_condition": "team_total",
                                   "agents": [seat, {"type": "greedy"}, dict(seat)]}},
           "motivation": [1.0], "group_policy": ["fixed(2)"], "group_share": [False],
           "logging": {"level": "full", "snapshots": "decision"}}
    runner.run_experiment(exp, ".", workers=1, out_root=tmp_path / "results", log_root=tmp_path / "logs",
                          progress=False)
    path, = (tmp_path / "logs" / "talk").rglob("*.jsonl.gz")
    return read_log(path)


def test_talkers_share_a_table_and_messages_are_logged(endpoint, tmp_path):
    e = endpoint([TALKED])
    lines = talk_experiment(e.url, tmp_path)
    seats = lines[0]["seats"]
    assert [s["settings"].get("talk") for s in seats] == [True, None, True]
    assert llm.TALK_RULES in seats[0]["settings"]["system_prompt"]
    acts = [ln for ln in lines if ln["t"] == "decision" and ln["kind"] == "action" and ln["player"] in (0, 2)]
    assert all(ln["info"]["said"] == "I need fish, can you leave the fish die?" for ln in acts)
    first, later = acts[0], acts[1]
    assert "(nothing said yet)" in first["info"]["prompt"] and llm.TALK_ASK in first["info"]["prompt"]
    a, b = first["player"], later["player"]
    assert {a, b} == {0, 2}
    who = "player 0 (you), player 2" if b == 0 else "player 0, player 2 (you)"
    assert f"players who talk: {who}" in later["info"]["prompt"]
    assert f"round 1, turn {first['turn_no']}, player {a}: I need fish" in later["info"]["prompt"]
    bot = [ln for ln in lines if ln["t"] == "decision" and ln["player"] == 1]
    assert bot and not any("said" in (ln.get("info") or {}) for ln in bot)


def test_probe_rebuilds_the_table_talk(endpoint, tmp_path):
    e = endpoint([TALKED])
    lines = talk_experiment(e.url, tmp_path)
    args = argparse.Namespace(model=None, base_url=None, reasoning="logged", thinking="logged", plan="logged",
                              extra_body=None, timeout=60, budget_usd=None, outcomes=None, goal_status=None,
                              talk=None, coach=None, digest=None, temperature=0.0, max_tokens=None)
    asked = [ln for ln in lines if ln["t"] == "decision" and (ln.get("info") or {}).get("prompt")]
    for ln in asked[::9]:
        cfg, s, d, t = probe.position(lines, seq=ln["seq"])
        a, _ = probe.build_agent(lines[0], t["player"], args)
        a.start(cfg, t["player"], Objective(1.0, 3))
        a.current_plan = ln["info"].get("plan")
        a.turn_notes = probe.turn_notes(lines, t)
        a.table = probe.table_talk(lines, t)
        assert a.build_prompt(api.observe(s, t["player"]), d)[0] == ln["info"]["prompt"]


HARNESS = ("The plan holds.\nANSWER: 1\nPLAN:\nEngine: forest\nBonus target: none\nRound goal: birds\n"
           "Need next: fish\nPivot if: no fish\nEND PLAN\nSAY: I need fish.\nTO COACH: Agreed, taking food.\n"
           "NOTES:\n- Too many cards in hand.")


def test_coach_and_digest_calls_feed_the_action_prompt(endpoint, tmp_path):
    e = endpoint([HARNESS])
    seat = {"type": "llm", "model": "test/model", "base_url": e.url, "prompt": "plan", "plan": True,
            "compact": True, "talk": True, "coach": True, "digest": True}
    exp = {"name": "harness", "seeds": {"start": 5, "count": 1}, "players": [3],
           "conditions": {"coop": {"plugins": {"coop_goals": {}}, "win_condition": "team_total",
                                   "agents": [seat, {"type": "greedy"}, dict(seat)]}},
           "motivation": [1.0], "group_policy": ["fixed(2)"], "group_share": [False],
           "logging": {"level": "full", "snapshots": "decision"}}
    games, _, _ = runner.run_experiment(exp, ".", workers=1, out_root=tmp_path / "results",
                                        log_root=tmp_path / "logs", progress=False)
    path, = (tmp_path / "logs" / "harness").rglob("*.jsonl.gz")
    lines = read_log(path)
    acts = [ln for ln in lines if ln["t"] == "decision" and ln["kind"] == "action" and ln["player"] in (0, 2)]
    first, second = acts[0], acts[1]
    assert [c["role"] for c in first["info"]["aux"]] == ["coach"]                # nothing said yet
    assert [c["role"] for c in second["info"]["aux"]] == ["digest", "coach"]     # the first player spoke
    assert llm.DIGEST_ASK in second["info"]["aux"][0]["prompt"] and "I need fish." in second["info"]["aux"][0]["prompt"]
    prompt = second["info"]["prompt"]
    assert "COACH NOTES" in prompt and "- Too many cards in hand." in prompt and llm.COACH_REPLY_ASK in prompt
    assert "YOUR NOTES ON THE TABLE TALK (written round 1" in prompt
    assert first["info"]["coach"] == "- Too many cards in hand." and first["info"]["to_coach"] == "Agreed, taking food."
    again = next(ln for ln in acts[2:] if ln["player"] == first["player"])
    coach_prompt = next(c["prompt"] for c in again["info"]["aux"] if c["role"] == "coach")
    assert "YOUR NOTES LAST TIME" in coach_prompt and "Agreed, taking food." in coach_prompt
    assert f"turn {first['turn_no']}: " in coach_prompt                       # its recent actions
    # every call is counted, and the tokens script sees the extra calls too
    asked = [ln for ln in lines if ln["t"] == "decision" and (ln.get("info") or {}).get("replies")]
    calls = sum(len(ln["info"]["replies"]) + len(ln["info"].get("aux") or []) for ln in asked)
    assert games.llm_calls.iloc[0] == calls
    from wingsim.analysis import tokens
    assert tokens.from_log(path)["calls"] == calls
    # the probe rebuilds every prompt, coach and talk notes included
    args = argparse.Namespace(model=None, base_url=None, reasoning="logged", thinking="logged", plan="logged",
                              extra_body=None, timeout=60, budget_usd=None, outcomes=None, goal_status=None,
                              talk=None, coach=None, digest=None, temperature=0.0, max_tokens=None)
    for ln in asked[::5]:
        cfg, s, d, t = probe.position(lines, seq=ln["seq"])
        a, _ = probe.build_agent(lines[0], t["player"], args)
        a.start(cfg, t["player"], Objective(1.0, 3))
        a.current_plan = ln["info"].get("plan")
        a.turn_notes = probe.turn_notes(lines, t)
        a.table = probe.table_talk(lines, t)
        state = probe.harness_state(lines, t)
        if d.kind == "action":
            probe.apply_aux(state, t, ln["info"], state["posted"])
        probe.set_harness(a, state)
        assert a.build_prompt(api.observe(s, t["player"]), d)[0] == ln["info"]["prompt"], ln["seq"]
