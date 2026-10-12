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
                out = {"choices": [{"message": {"role": "assistant", "content": reply}}],
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
    assert "ANSWER: <number>" in a.system and a.max_tokens == 300
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
