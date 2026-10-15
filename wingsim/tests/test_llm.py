"""Language-model agent, against a local stand-in for an OpenAI-compatible endpoint."""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

from wingsim import runner
from wingsim.agents import llm
from wingsim.agents.base import Objective
from wingsim.agents.llm import LLMAgent, parse_choice
from wingsim.engine import api, describe
from wingsim.engine.log import read_log, replay

from .conftest import random_game


class FakeEndpoint:
    """Answers chat requests with scripted replies (the last one repeats) and records what it was sent."""

    def __init__(self, replies, status=None):
        self.replies = list(replies)
        self.requests = []
        self.status = list(status or [])
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                outer.requests.append({"path": self.path, "body": body, "auth": self.headers.get("Authorization")})
                code = outer.status.pop(0) if outer.status else 200
                if code != 200:
                    self.send_response(code)
                    self.end_headers()
                    self.wfile.write(b"busy")
                    return
                reply = outer.replies.pop(0) if len(outer.replies) > 1 else outer.replies[0]
                message = reply if isinstance(reply, dict) else {"content": reply}   # a dict: the whole message
                out = {"choices": [{"message": {"role": "assistant", **message}}],
                       "usage": {"prompt_tokens": 1000, "completion_tokens": 2, "cost": 0.001}}
                data = json.dumps(out).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()


@pytest.fixture
def endpoint():
    made = []

    def make(replies, status=None):
        e = FakeEndpoint(replies, status)
        made.append(e)
        return e

    llm.SPEND.update(calls=0, prompt_tokens=0, completion_tokens=0, cost_usd=0.0)
    yield make
    for e in made:
        e.close()


def agent_at_first_decision(url, monkeypatch, **kw):
    monkeypatch.setenv("TEST_KEY", "secret-key")
    cfg = api.GameConfig(3, {"coop_goals": {}})
    s = api.new_game(cfg, 3)
    d = api.pending_decision(s)
    a = LLMAgent("test/model", base_url=url, api_key_env="TEST_KEY", **kw)
    a.start(cfg, d.player, Objective(1.0, 3))
    return s, d, a


def test_parse_choice():
    assert parse_choice("3", 5) == 3
    assert parse_choice("I think option 2 is safest.\nANSWER: 4", 5) == 4
    assert parse_choice("**ANSWER: 1**", 5) == 1
    assert parse_choice("Option 7", 5) is None and parse_choice("none of them", 5) is None
    assert parse_choice("", 5) is None and parse_choice("0", 5) is None


def test_prompt_holds_rules_objective_observation_and_numbered_options(endpoint, monkeypatch):
    e = endpoint(["2"])
    s, d, a = agent_at_first_decision(e.url, monkeypatch)
    choice = a.choose(api.observe(s, d.player), d)
    assert choice == d.options[1]
    req = e.requests[0]
    assert req["path"] == "/v1/chat/completions" and req["auth"] == "Bearer secret-key"
    assert req["body"]["model"] == "test/model" and req["body"]["temperature"] == 0.0
    system, user = (m["content"] for m in req["body"]["messages"])
    assert "RULES SUMMARY" in system and "HOUSE RULE - cooperative round goals" in system
    assert "Maximize the team total" in system and "All hands and bonus cards are open" in system
    assert f"You are player {d.player}" in user and "Round goals:" in user and "Birdfeeder dice:" in user
    assert "DECISION: Setup: choose which of your 5 starting birds to keep" in user
    for i in range(1, len(d.options) + 1):
        assert f"\n{i}. " in user
    name = s.cfg.db.birds[s.players[d.player].hand[0]].name
    assert name in user                                   # the cards are described by name and text
    info = a.info()
    assert "reasoning" not in req["body"] and "usage" not in req["body"]     # OpenRouter-only fields
    assert info["replies"] == ["2"] and info["chosen"] == 2 and info["fallback"] is None
    assert info["prompt"] == user and info["usage"]["prompt_tokens"] == 1000
    assert a.stats["calls"] == 1 and a.stats["cost_usd"] == pytest.approx(0.001)
    assert "secret-key" not in json.dumps(a.settings()) and "secret-key" not in json.dumps(info)


def test_unparsable_reply_is_retried_once_then_random_and_logged(endpoint, monkeypatch):
    e = endpoint(["hmm, hard to say", "ANSWER: 5"])
    s, d, a = agent_at_first_decision(e.url, monkeypatch, reasoning=True)
    assert a.choose(api.observe(s, d.player), d) == d.options[4]
    assert len(e.requests) == 2 and len(e.requests[1]["body"]["messages"]) == 4
    assert a.info()["replies"] == ["hmm, hard to say", "ANSWER: 5"] and a.info()["fallback"] is None
    assert a.stats["retries"] == 1 and a.stats["fallbacks"] == 0
    assert "ANSWER: <number>" in a.system and a.max_tokens == 600
    assert e.requests[1]["body"]["max_tokens"] == 300 and "Do not start over" in e.requests[1]["body"]["messages"][-1]["content"]
    assert a.info()["limits"] == [600, 300] and len(a.info()["usage_all"]) == 2
    assert a.info()["usage"] == a.info()["usage_all"][-1]
    e2 = endpoint(["no idea"])
    s, d, b = agent_at_first_decision(e2.url, monkeypatch)
    choice = b.choose(api.observe(s, d.player), d)
    assert choice in d.options and len(e2.requests) == 2    # asked twice, then picked at random
    assert b.info()["fallback"] == "random" and b.stats["fallbacks"] == 1


def test_busy_endpoint_is_retried_and_budget_stops_the_game(endpoint, monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda s: None)
    e = endpoint(["1"], status=[429, 503])
    s, d, a = agent_at_first_decision(e.url, monkeypatch)
    assert a.choose(api.observe(s, d.player), d) == d.options[0] and len(e.requests) == 3
    capped = LLMAgent("test/model", base_url=e.url, api_key_env="TEST_KEY", budget_usd=0.0005)
    capped.start(s.cfg, d.player, Objective(0.0, 3))
    with pytest.raises(llm.BudgetExceeded):                 # this process has already spent $0.001
        capped.choose(api.observe(s, d.player), d)
    e3 = endpoint(["1"], status=[401])
    s, d, bad = agent_at_first_decision(e3.url, monkeypatch)
    with pytest.raises(RuntimeError, match="HTTP 401"):
        bad.choose(api.observe(s, d.player), d)


def test_openrouter_thinking_setting(monkeypatch):
    sent = []
    monkeypatch.setattr(llm.urllib.request, "urlopen", lambda req, timeout: sent.append(json.loads(req.data)) or
                        (_ for _ in ()).throw(llm.urllib.error.HTTPError("u", 400, "bad", {}, __import__("io").BytesIO(b"x"))))
    for thinking, expected, tokens in ((None, {"enabled": False}, 16), ("low", {"effort": "low"}, 4016)):
        a = LLMAgent("x/y", thinking=thinking)
        assert a.max_tokens == tokens
        with pytest.raises(RuntimeError):
            a.call([{"role": "user", "content": "hi"}])
        assert sent[-1]["reasoning"] == expected and sent[-1]["usage"] == {"include": True}


def test_load_env_accepts_spaces_around_equals(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("# comment\nMY_TEST_KEY =abc123\nOTHER= 'x y'\n")
    monkeypatch.delenv("MY_TEST_KEY", raising=False)
    monkeypatch.delenv("OTHER", raising=False)
    llm.load_env(f)
    import os
    assert os.environ["MY_TEST_KEY"] == "abc123" and os.environ["OTHER"] == "x y"


def test_every_option_of_every_decision_has_a_label():
    """Random games reach every decision kind; each option must get a readable, distinct label."""
    import random
    from wingsim.engine import rules
    seen = set()
    for seed in range(12):
        cfg = api.GameConfig(2 + seed % 4, {"coop_goals": {}} if seed % 2 else None, open_hands=seed % 3 != 0)
        rng = random.Random(seed)
        s = api.new_game(cfg, seed)
        while s.pend is not None:
            labels = describe.option_labels(s)
            assert len(labels) == len(s.pend[2]) and all(isinstance(x, str) and len(x) > 3 for x in labels)
            assert len(set(labels)) == len(labels), (s.pend[1], labels)
            assert describe.decision_text(s)
            seen.add(s.pend[1])
            if len(seen) % 5 == 0 and s.pend[0] != api.GROUP:
                text = describe.observation_text(api.observe(s, s.pend[0]))
                assert "PLAYER 0" in text and "Round goals:" in text
            rules.resume(s, s.pend[2][rng.randrange(len(s.pend[2]))])
    assert len(seen) >= 22


def test_mixed_table_in_the_runner_logs_prompts_and_replays(endpoint, monkeypatch, tmp_path):
    e = endpoint(["1"])
    monkeypatch.setenv("TEST_KEY", "k")
    exp = {"name": "llm-unit", "seeds": {"start": 2, "count": 1}, "players": [2],
           "conditions": {"coop": {"plugins": {"coop_goals": {}}}},
           "agents": [{"type": "llm", "model": "test/model", "base_url": e.url, "api_key_env": "TEST_KEY"},
                      {"type": "random"}],
           "motivation": [1.0], "group_policy": ["fixed(1)"],
           "logging": {"level": "full", "snapshots": "decision"}}
    games, offers, out = runner.run_experiment(exp, ".", workers=1, out_root=tmp_path / "r",
                                               log_root=tmp_path / "l", progress=False)
    row = games.iloc[0]
    assert row.agent == "llm:test/model+random" and row.p0_agent == "llm" and row.p1_agent == "random"
    assert row.llm_calls == len(e.requests) > 50 and row.llm_fallbacks == 0
    assert row.llm_cost_usd == pytest.approx(0.001 * row.llm_calls)
    lines = read_log(row.log)
    assert lines[0]["seats"][0]["type"] == "llm" and "RULES SUMMARY" in lines[0]["seats"][0]["settings"]["system_prompt"]
    mine = [ln for ln in lines if ln["t"] == "decision" and ln["player"] == 0]
    assert all(ln["info"]["replies"] == ["1"] and ln["choice"] == 0 and ln["labels"] for ln in mine)
    assert mine[0]["info"]["prompt"].startswith("Setup, before round 1.")
    assert api.is_over(replay(row.log))


PLANNED = ("<think>scratch work 7</think>The plan holds. ANSWER: 1\n"
           "PLAN:\nEngine: forest\nBonus target: none yet\nRound goal: most birds\nNeed next: seed\n"
           "Pivot if: no seed for 2 turns\nEND PLAN")


def test_openrouter_key_is_sent_only_to_openrouter(endpoint, monkeypatch):
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-secret")
    e = endpoint(["ANSWER: 1"])
    cfg = api.GameConfig(2)
    s = api.new_game(cfg, 1)
    d = api.pending_decision(s)
    a = LLMAgent("local-model", base_url=e.url)
    a.start(cfg, d.player, Objective(0.0, 2))
    a.choose(api.observe(s, d.player), d)
    assert e.requests[0]["auth"] is None
    assert LLMAgent("m").api_key_env == "OPENROUTER_API_KEY"


def test_replies_are_read_past_thinking_tags_and_plan_blocks():
    assert parse_choice("<think>maybe 9</think>ANSWER: 2", 3) == 2
    assert parse_choice("<think>Option 2 is solid.\nANSWER: 3", 3, strict=True) == 3   # stray tag, thinking off
    assert parse_choice("ANSWER: 3\nPLAN:\nNeed next: 2 fish\nEND PLAN", 4) == 3
    assert parse_choice("Game plan: get fish, then eggs.\nANSWER: 2", 4, strict=True) == 2    # not a plan block
    assert parse_choice("ANSWER: 1\n**PLAN:**\nEngine: ducks\nEND PLAN", 4, strict=True) == 1
    assert llm.parse_plan(PLANNED).startswith("Engine: forest")
    quoted = "My old plan:\nPLAN:\nEngine: ducks\nEND PLAN\nIt still holds.\nANSWER: 2\nPLAN:\nEngine: geese\nEND PLAN"
    assert llm.parse_plan(quoted) == "Engine: geese" and parse_choice(quoted, 3, strict=True) == 2
    assert llm.parse_numbers("I keep two. ANSWER: 1, 4", 5) == [1, 4]
    assert llm.parse_numbers("ANSWER: none", 5) == []
    assert llm.parse_numbers("ANSWER: 1, 6", 5) is None


def test_compact_starting_hand_is_chosen_by_bird_number(endpoint, monkeypatch):
    e = endpoint(["Two birds. ANSWER: 1, 3"])
    s, d, a = agent_at_first_decision(e.url, monkeypatch, compact=True)
    assert d.kind == "setup_keep_birds"
    choice = a.choose(api.observe(s, d.player), d)
    dealt = max((o[1] for o in d.options), key=len)
    assert set(choice[1]) == {dealt[0], dealt[2]}
    prompt = e.requests[0]["body"]["messages"][1]["content"]
    assert "Your dealt birds:" in prompt and "Keep 2:" not in prompt


def test_plan_is_kept_shown_and_logged_through_a_game(endpoint, monkeypatch):
    e = endpoint([PLANNED])
    monkeypatch.setenv("TEST_KEY", "k")
    cfg = api.GameConfig(2, record_events=True)
    from wingsim.agents.greedy import GreedyAgent
    from wingsim.game import play_game
    from wingsim.engine.log import GameLog
    a = LLMAgent("test/model", base_url=e.url, api_key_env="TEST_KEY", prompt="plan", plan=True, outcomes=True,
                 compact=True)
    g = GreedyAgent(seed=1)
    a.start(cfg, 0, Objective(0.0, 2))
    g.start(cfg, 1, Objective(0.0, 2))
    log = GameLog(cfg, 2, [a.settings(), g.settings()])
    play_game(cfg, 2, [a, g], log=log)
    mine = [ln for ln in log.lines if ln["t"] == "decision" and ln["player"] == 0]
    actions = [d for d in mine if d["kind"] == "action"]
    assert len(actions) == 26 and all(d["info"]["plan_updated"] for d in actions)
    assert actions[0]["info"]["plan"] is None and actions[1]["info"]["plan"].startswith("Engine: forest")
    assert "PLAN:" in actions[0]["info"]["prompt"] and "After: " in actions[0]["info"]["prompt"]
    later = [d for d in mine if d["kind"] != "action" and d["round"] >= 1 and "THIS TURN SO FAR" in d["info"]["prompt"]]
    assert later and "Your reasoning: The plan holds." in later[0]["info"]["prompt"]
    assert all(d["info"]["fallback"] is None for d in mine)
    body = e.requests[0]["body"]
    assert "YOUR PLAN" in body["messages"][0]["content"]


def test_reasoned_replies_need_an_answer_line():
    assert parse_choice("Option 1 is weak; I keep 2 eggs in mind", 3) == 2
    assert parse_choice("Option 1 is weak; I keep 2 eggs in mind", 3, strict=True) is None
    assert parse_choice("so ANSWER: 3", 3, strict=True) == 3


def test_cut_off_reasoning_gets_a_short_answer_only_retry(endpoint, monkeypatch):
    # A reply that ran out of tokens mid-reasoning; asked again, the model gives just a number.
    e = endpoint(["Option 1 gains 2 food, option 3 lays", "**3**"])
    s, d, a = agent_at_first_decision(e.url, monkeypatch, reasoning=True)
    assert a.choose(api.observe(s, d.player), d) == d.options[2] and a.info()["fallback"] is None
    e2 = endpoint(["Option 1 gains 2 food, option 3 lays", "Option 2 is"])   # still no answer: random
    s, d, b = agent_at_first_decision(e2.url, monkeypatch, reasoning=True)
    b.choose(api.observe(s, d.player), d)
    assert b.info()["fallback"] == "random"


def test_separate_thinking_text_is_logged(endpoint, monkeypatch):
    e = endpoint([{"content": "ANSWER: 2", "reasoning_content": "Option 2 keeps the fish."}])
    s, d, a = agent_at_first_decision(e.url, monkeypatch, reasoning=True)
    a.choose(api.observe(s, d.player), d)
    assert a.info()["thinking"] == ["Option 2 keeps the fish."] and a.info()["chosen"] == 2
    e2 = endpoint(["ANSWER: 2"])
    s, d, b = agent_at_first_decision(e2.url, monkeypatch, reasoning=True)
    b.choose(api.observe(s, d.player), d)
    assert "thinking" not in b.info()


def test_full_reasoning_relaxes_the_length_and_raises_the_limit(endpoint, monkeypatch):
    e = endpoint(["ANSWER: 1"])
    s, d, a = agent_at_first_decision(e.url, monkeypatch, reasoning="full")
    assert a.reasoning and a.full and a.max_tokens == 4000 and a.settings()["reasoning"] == "full"
    assert "a few short paragraphs at most" in a.system and "three sentences" not in a.system
    s, d, b = agent_at_first_decision(e.url, monkeypatch, reasoning=True)
    assert not b.full and b.max_tokens == 600 and "three sentences at most" in b.system


def _play_to(cfg, stop, seed=7):
    """Play a game with greedy seats (and fixed(2) for the group) until stop(state, decision) holds."""
    from wingsim.agents import group_policies
    from wingsim.agents.greedy import GreedyAgent
    s = api.new_game(cfg, seed)
    seats = [GreedyAgent() for _ in range(cfg.n)]
    for i, g in enumerate(seats):
        g.start(cfg, i, Objective(1.0, cfg.n))
    pol = group_policies.parse("fixed(2)")
    pol.start(cfg, None, seed)
    while (d := api.pending_decision(s)) is not None and not stop(s, d):
        s = api.apply(s, d, (pol if d.player == api.GROUP else seats[d.player]).choose(api.observe(s, d.player), d))
    return s, d


def test_goal_status_block_in_coop_games():
    cfg = api.GameConfig(2, {"coop_goals": {"penalty": "avg_x_d", "allowed_changes": [0, 1]}}, True, "team_total")
    s, d = _play_to(cfg, lambda s, d: s.round == 2 and d.player == 0 and d.kind == "action")
    a = LLMAgent("test/model", base_url="http://localhost:1/v1", reasoning="full", goal_status=True)
    a.start(cfg, 0, Objective(1.0, 2))
    user = a.build_prompt(api.observe(s, 0), d)[0]
    counts = api.goal_counts(s)
    assert "ROUND GOAL STATUS - round 2:" in user and "EVERY player needs a count of at least 2" in user
    assert f"player 0 (you): {counts[0]}" in user and "If the round ended now:" in user
    assert "Earlier rounds: round 1 (d = 2)" in user and a.settings()["goal_status"] is True
    b = LLMAgent("test/model", base_url="http://localhost:1/v1", reasoning="full")
    b.start(cfg, 0, Objective(1.0, 2))
    assert "ROUND GOAL STATUS" not in b.build_prompt(api.observe(s, 0), d)[0]


def test_goal_status_block_in_individual_games():
    cfg = api.GameConfig(2, {}, True, "individual")
    s, d = _play_to(cfg, lambda s, d: s.round == 2 and d.player == 0 and d.kind == "action")
    text = api.describe_goal_status(api.observe(s, 0))
    pts, _, _ = api.score_goal_counts(s, api.goal_counts(s))
    assert f"player 0 (you): count {api.goal_counts(s)[0]}, {pts[0]:g} points" in text
    assert "Earlier rounds: round 1: points player 0 (you)" in text and "Difficulty" not in text
