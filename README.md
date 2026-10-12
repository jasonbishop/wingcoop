# Wingspan co-op simulator

Plays complete multiplayer Wingspan games (core set, 2 to 5 players) between bot
players to test house rules that make the game cooperative. The design is in
`Wingspan Co-op Simulator — Build Spec.md`. Milestones 1 to 8 of that spec are built (the help action, milestone 9, is not).

## Setup

```
uv venv --python 3.13 .venv
uv pip install --python .venv/bin/python -e ".[analysis,dev]"
```

The engine itself uses only the standard library.

## Common commands

```
.venv/bin/python -m pytest                      # quick checks (about a minute)
.venv/bin/python -m pytest -m slow              # the 10,000-game random fuzz
.venv/bin/python -m wingsim.data.build          # regenerate cards.json, effects.json and the review sheet
.venv/bin/python -m wingsim.runner wingsim/experiments/coop-goals-small.yaml --workers 4
.venv/bin/python -m wingsim.analysis.report results/coop-goals-small
.venv/bin/python -m wingsim.analysis.controls --positions 600 --iterations 1200 --workers 8
.venv/bin/python -m wingsim.runner wingsim/experiments/controls-mcts.yaml --workers 8
.venv/bin/python -m wingsim.tune wingsim/experiments/coop-goals-small.yaml --minutes 18 --workers 8
.venv/bin/python -m wingsim.runner wingsim/experiments/llm-smoke.yaml --workers 1 --no-report
.venv/bin/python -m wingsim.engine.log export <log.jsonl.gz> <out.json>     # one JSON file for a viewer
```

A run writes `results/<experiment>/games.parquet` (one row per game),
`offers.parquet` (pick-rate counts), `report.md` with charts, and full replay
logs under `logs/<experiment>/<condition>/`.

The controls command writes `results/controls/controls.md`: the positive and negative
controls for the tree-search agent (see `wingsim/analysis/controls.py` for the method).

## Replay logs and a viewer

`docs/replay-log-format.md` describes the log files completely, with samples in `docs/samples/`.
It is written to be handed to whoever builds a play-by-play viewer.

## Language-model agent

`agents: [{type: llm, model: ...}, {type: greedy}]` in an experiment file seats one agent per
seat. It calls any OpenAI-compatible endpoint (OpenRouter by default; the key is read from
`OPENROUTER_API_KEY`, or from `.env`). Settings: `prompt` (template name), `reasoning` (a few
visible sentences before the answer), `thinking` (hidden model-side reasoning: off unless set to
`low`, `medium` or `high`), `budget_usd`, `max_calls`, `base_url`, `api_key_env`.

The prompt text lives in `wingsim/prompts/`: `rules.md` is the rules summary and `default.md` the
system prompt template. Copy `default.md` to a new name and set `prompt: <name>` to try a variant.
Every prompt and reply is stored in the replay log.

## Layout

```
wingsim/
  data/         raw/ (vendored wingsearch files), build.py, effect_overrides.yaml, effects.json,
                cards.json, effects_review.md (for human review of the effect specs)
  engine/       state.py, rules.py, effects.py, scoring.py, observe.py, api.py, log.py, config.py
  plugins/      coop_goals.py, open_hands.py
  agents/       random.py, greedy.py, mcts.py, llm.py, group_policies.py   (must never import analysis)
  prompts/      rules.md, default.md   (text the language-model agent is given)
  analysis/     tags.py, metrics.py, report.py, controls.py
  experiments/  *.yaml
  tests/
  runner.py     experiment runner
  tune.py       per-condition weight tuning for the greedy bot
  game.py       plays one game between agents
```

## Where this differs from the spec

- **26 bonus cards, not 27.** wingsearch tags one fan-made bonus card as `core`; it is left out.
- **`group_share`** is an extra grid setting: whether an equal share of the group score counts as
  a player's own score in the bots' objective. Both values are run.
- **Open hands in the baseline too**, so goal scoring is the only difference between paired conditions.
- **Log file names** carry the motivation and policy as well as the seed and player count, because
  several cells of one condition share a seed.
- **Greedy bots and round goals.** Points banked change only at round end, so the greedy value
  function asks the engine what the current goal would score for projected end-of-round counts
  (`api.score_goal_counts`). It never checks which plugin is active.
- **Pink powers** resolve as soon as the power or action that triggered them has finished, before the
  next bird in the row, following wingsearch rulings 20200204a and 20231030.
- **Controls use probes.** Running whole 5-player games with tree-search bots is slow, so the
  controls hand positions from greedy-bot games to the tree-search agent, once per motivation
  level with the same random seed. `experiments/controls-mcts.yaml` runs the literal version
  (whole games played by tree-search bots) on a small number of seeds.
- **Tree search and other players.** An agent is told only its own objective, so the search
  assumes every other player has the same motivation weight.
- **Log format version 2.** Logs also carry a snapshot before the first decision, a `labels` list
  with a readable sentence for every option, and optionally a snapshot before every decision
  (`logging: {snapshots: decision}`).
- **Card text reaches the language model through the engine** (`engine/describe.py`), so the
  purity tests still hold for every file in `agents/`.
- **Not built yet (milestone 9):** the help action.
