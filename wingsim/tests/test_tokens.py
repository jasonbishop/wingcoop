"""Token totals from game logs and rows, and their cost."""
import gzip
import json

import pytest

from wingsim.analysis import tokens


def write_log(path, decisions):
    with gzip.open(path, "wt") as f:
        f.write(json.dumps({"t": "header"}) + "\n")
        f.write(json.dumps({"t": "decision", "kind": "action", "info": None}) + "\n")      # a bot's decision
        for info in decisions:
            f.write(json.dumps({"t": "decision", "kind": "action", "info": info}) + "\n")


def test_log_totals_count_every_call_and_mark_old_retries(tmp_path):
    u = lambda i, o: {"prompt_tokens": i, "completion_tokens": o}
    write_log(tmp_path / "new.jsonl.gz", [
        {"replies": ["a"], "usage": u(100, 10), "usage_all": [u(100, 10)]},
        {"replies": ["b", "c"], "usage": u(130, 5), "usage_all": [u(120, 600), u(130, 5)]},
    ])
    write_log(tmp_path / "old.jsonl.gz", [{"replies": ["b", "c"], "usage": u(130, 5)}])
    new = tokens.from_log(tmp_path / "new.jsonl.gz")
    assert (new["calls"], new["input"], new["output"], new["partial"]) == (3, 350, 615, False)
    assert tokens.from_log(tmp_path / "old.jsonl.gz")["partial"]
    assert len(tokens.collect([tmp_path])) == 2
    assert tokens.cost(new, (1.0, 10.0)) == pytest.approx((350 + 6150) / 1e6)


def test_cheapest_lists_free_and_paid_models_under_the_limit_cheapest_first():
    def model(mid, pin, pout, ctx=200_000, out=("text",)):
        return {"id": mid, "context_length": ctx, "architecture": {"output_modalities": list(out)},
                "pricing": {"prompt": str(pin / 1e6), "completion": str(pout / 1e6)}}
    models = [model("a/mid", 0.2, 1.0), model("a/cheap", 0.1, 0.5), model("a/free:free", 0, 0),
              model("a/dear", 2.0, 10.0), model("a/cheap:batch", 0.05, 0.25), model("~a/cheap-latest", 0.1, 0.5),
              model("a/router", -1, -1), model("a/music", 0, 0, out=("audio", "text")),
              model("a/tool", 0.04, 0), model("a/short", 0.01, 0.01, ctx=8192)]
    games = [{"input": 400_000, "output": 200_000}, {"input": 400_000, "output": 100_000}]
    rows = tokens.cheapest(models, games, max_cost=0.50)
    assert [r[0] for r in rows] == ["a/free:free", "a/cheap", "a/mid"]
    assert rows[1][4] == pytest.approx((400_000 * 0.1 + 150_000 * 0.5) / 1e6)
    assert "a/cheap:batch" in [r[0] for r in tokens.cheapest(models, games, batch=True)]


def test_rows_totals_skip_bot_only_games(tmp_path):
    rows = [{"row": {"condition": "plan", "seed": 101, "llm_calls": 3, "llm_prompt_tokens": 900,
                     "llm_completion_tokens": 50}},
            {"row": {"condition": "bots", "seed": 101}}]
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    games = tokens.collect([tmp_path / "rows.jsonl"])
    assert [(g["game"], g["input"], g["output"]) for g in games] == [("plan seed 101", 900, 50)]
