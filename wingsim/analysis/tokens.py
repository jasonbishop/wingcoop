"""Language-model token use per game, and what it would cost on OpenRouter.

Reads full game logs (*.jsonl.gz, or directories holding them) or an experiment's
rows.jsonl, and totals the input and output tokens of the language-model seats
per game. With --model it fetches the listed models' current prices from
OpenRouter's public model list (no key is sent) and prices every game; --price
gives a price by hand instead, in dollars per million input and output tokens.

The counts are the serving model's own tokens. Another model's tokenizer counts
the same text somewhat differently, and its replies will be longer or shorter
(models that think before answering also bill the thinking as output), so the
costs are an estimate; a game or two on the real model gives the real figure.
Prompt-cache discounts are left out.

Log files written before `usage_all` existed record only the last call of a
decision that was retried; those games are marked "partial" and undercount.

Usage:
  python -m wingsim.analysis.tokens logs/llm-prompts-moe
  python -m wingsim.analysis.tokens results/llm-prompts-moe/rows.jsonl --model qwen/qwen3.6-35b-a3b anthropic/claude-haiku-5.5
  python -m wingsim.analysis.tokens logs/llm-prompts-moe/coop_plan/103-2p-w1.0-fixed_2.jsonl.gz --price 0.15 1.00
  python -m wingsim.analysis.tokens results/llm-prompts-moe/rows.jsonl --list --max-cost 0.50
"""
import argparse
import gzip
import json
import pathlib
import urllib.request

MODELS_URL = "https://openrouter.ai/api/v1/models"


def from_log(path):
    """Token totals for one full game log: {"game", "calls", "input", "output", "partial"}."""
    calls = inp = out = 0
    partial = False
    with gzip.open(path, "rt") as f:
        for line in f:
            d = json.loads(line)
            info = d.get("info") or {} if d.get("t") == "decision" else {}
            if not info.get("replies"):
                continue
            usages = info.get("usage_all") or [info.get("usage") or {}]
            partial |= len(usages) < len(info["replies"])
            for u in usages:
                calls += 1
                inp += u.get("prompt_tokens") or 0
                out += u.get("completion_tokens") or 0
    return {"game": str(path), "calls": calls, "input": inp, "output": out, "partial": partial}


def from_rows(path):
    """Token totals for every language-model game in an experiment's rows.jsonl."""
    games = []
    for line in pathlib.Path(path).read_text().splitlines():
        r = json.loads(line)["row"]
        if "llm_calls" in r:
            games.append({"game": f"{r['condition']} seed {r['seed']}", "calls": r["llm_calls"],
                          "input": r["llm_prompt_tokens"], "output": r["llm_completion_tokens"], "partial": False})
    return games


def collect(paths):
    games = []
    for p in map(pathlib.Path, paths):
        if p.is_dir():
            games += [from_log(f) for f in sorted(p.rglob("*.jsonl.gz"))]
        elif p.name.endswith(".jsonl.gz"):
            games.append(from_log(p))
        else:
            games += from_rows(p)
    return [g for g in games if g["calls"]]


def openrouter_models():
    """OpenRouter's public model list (no key is sent)."""
    with urllib.request.urlopen(MODELS_URL, timeout=30) as resp:
        return json.load(resp)["data"]


def price_of(model):
    """(input, output) dollars per million tokens; negative for routers whose price depends on the pick."""
    p = model.get("pricing") or {}
    return float(p.get("prompt") or 0) * 1e6, float(p.get("completion") or 0) * 1e6


def openrouter_prices(ids, models=None):
    """{model id: (input, output) dollars per million tokens} for the given OpenRouter ids."""
    listed = {m["id"]: m for m in models or openrouter_models()}
    for i in ids:
        if i not in listed:
            raise SystemExit(f"{i} is not in OpenRouter's model list")
    return {i: price_of(listed[i]) for i in ids}


def cheapest(models, games, max_cost=0.50, min_context=16384, batch=False):
    """Text models whose average game would cost at most max_cost, cheapest first:
    [(id, input price, output price, context length, cost per game)]. Left out: batch variants (replies
    come back hours later, no use for a game played turn by turn), aliases (ids starting with "~", each
    the same as a listed model), routers with no fixed price, models that also output images or audio,
    tools billed by input only, and models with too little context for a prompt and a long reply."""
    n = len(games)
    avg = {"input": sum(g["input"] for g in games) / n, "output": sum(g["output"] for g in games) / n}
    out = []
    for m in models:
        price = price_of(m)
        if (min(price) < 0 or m["id"].startswith("~") or (m["id"].endswith(":batch") and not batch)
                or (m.get("architecture") or {}).get("output_modalities", ["text"]) != ["text"]
                or (price[1] == 0 and price[0] > 0)            # text tools billed by input only, not chat models
                or (m.get("context_length") or 0) < min_context):
            continue
        c = cost(avg, price)
        if c <= max_cost:
            out.append((m["id"], price[0], price[1], m.get("context_length") or 0, c))
    return sorted(out, key=lambda r: (r[4], r[0]))


def cost(game, price):
    return (game["input"] * price[0] + game["output"] * price[1]) / 1e6


def main():
    ap = argparse.ArgumentParser(description="Language-model tokens per game, and their cost on OpenRouter")
    ap.add_argument("paths", nargs="+", help="game logs, directories of them, or an experiment's rows.jsonl")
    ap.add_argument("--model", nargs="+", default=[], help="OpenRouter model ids to price the games at")
    ap.add_argument("--price", nargs=2, type=float, metavar=("IN", "OUT"),
                    help="a price by hand, dollars per million input and output tokens")
    ap.add_argument("--list", action="store_true",
                    help="list every OpenRouter model (free and paid) that would cost at most --max-cost a game")
    ap.add_argument("--max-cost", type=float, default=0.50, help="dollars per game for --list (default 0.50)")
    ap.add_argument("--min-context", type=int, default=16384, help="smallest context length for --list")
    ap.add_argument("--batch", action="store_true", help="include batch-priced variants in --list")
    args = ap.parse_args()
    games = collect(args.paths)
    if not games:
        raise SystemExit("no language-model games found")
    models = openrouter_models() if args.model or args.list else None
    prices = openrouter_prices(args.model, models) if args.model else {}
    if args.price:
        prices["--price"] = tuple(args.price)
    width = max(len(g["game"]) for g in games)
    for g in games:
        line = f"{g['game']:{width}}  {g['calls']:4} calls  {g['input']:9,} in  {g['output']:9,} out"
        print(line + ("  partial" if g["partial"] else ""))
    n = len(games)
    tin, tout = sum(g["input"] for g in games), sum(g["output"] for g in games)
    print(f"\n{n} games: {tin:,} input and {tout:,} output tokens; per game {tin / n:,.0f} in, {tout / n:,.0f} out")
    for name, price in prices.items():
        total = sum(cost(g, price) for g in games)
        print(f"  {name} (${price[0]:g} in / ${price[1]:g} out per M): ${total / n:.2f} a game, ${total:.2f} in all")
    if args.list:
        rows = cheapest(models, games, args.max_cost, args.min_context, args.batch)
        print(f"\nOpenRouter models at ${args.max_cost:.2f} a game or less, at the average game above "
              f"({len(rows)} models; free ones are rate-limited, see openrouter.ai/docs):")
        w = max([len(r[0]) for r in rows] + [5])
        print(f"  {'model':{w}}  {'$ in/M':>7}  {'$ out/M':>7}  {'context':>9}  {'$ a game':>8}  {f'$ {n} games':>11}")
        for mid, pin, pout, ctx, c in rows:
            print(f"  {mid:{w}}  {pin:7.3f}  {pout:7.3f}  {ctx:9,}  {c:8.3f}  {c * n:11.2f}")


if __name__ == "__main__":
    main()
