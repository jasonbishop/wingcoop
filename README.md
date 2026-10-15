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
.venv/bin/python -m wingsim.engine.log relog <old.jsonl.gz> <new.jsonl.gz>    # rewrite an older log in the current format
```

A run writes `results/<experiment>/games.parquet` (one row per game),
`offers.parquet` (pick-rate counts), `report.md` with charts, and full replay
logs under `logs/<experiment>/<condition>/`.

The controls command writes `results/controls/controls.md`: the positive and negative
controls for the tree-search agent (see `wingsim/analysis/controls.py` for the method).

## Replay logs and a viewer

`docs/replay-log-format.md` describes the log files completely, with samples in `docs/samples/`.
It is the contract between the simulator and the viewer.

`viewer/` plays logged games back on a 3D table in the browser (Three.js; needs Node and npm):

```
cd viewer
npm install
npm run dev        # http://<this machine>:5273/  (listens on all interfaces)
npm test           # rebuilds every snapshot in docs/samples from the events
```

The opening page lists every log under `logs/` and `docs/samples/`; an exported `.json` can also
be dropped on the page, and `/?log=docs/samples/coop-3p-greedy-every-decision.jsonl.gz&at=120`
opens a log at a given position. Players sit around a round table with their mats, food, cubes
for the turns left, bonus cards and hands; the goal board, birdfeeder, decks, tray and discard
ride a lazy susan that turns to face the seat being watched. A side panel shows each decision:
the options, what was chosen, the agent's values or the language model's reply and prompt, and
what followed. Logs with a snapshot before every decision are shown exactly; per-turn logs are
filled in from the events.

The viewer reads only the log (and `wingsim/data/cards.json` for card text), never engine code.
Where the log falls short for a viewer (events missing for some card movements, end of turn
only implied, and a few nice-to-haves such as live goal counts) is written up in
`viewer/FORMAT-REQUESTS.md` for the simulator side. See `viewer/README.md` for how it works.

## Language-model agent

`agents: [{type: llm, model: ...}, {type: greedy}]` in an experiment file seats one agent per
seat. It calls any OpenAI-compatible endpoint (OpenRouter by default; the key is read from
`OPENROUTER_API_KEY`, or from `.env`, and sent only to OpenRouter). Settings: `prompt` (template
name), `reasoning` (`true`: a few visible sentences before the answer, 600 tokens; `full`: a few short
paragraphs, 4000 tokens, for free local models or for reading the model's reasoning), `thinking` (hidden model-side reasoning:
off unless set to `low`, `medium` or `high`), `budget_usd`, `max_calls`, `base_url`, `api_key_env` (a
key to send to another endpoint), `extra_body` (extra request fields, e.g.
`{chat_template_kwargs: {enable_thinking: false}}` for a local Qwen server).

Prompt features, each a setting so variants can be compared (`wingsim/agents/llm.py` describes them):
`plan` (a short written plan carried between turns, with the `plan` template), `outcomes` (a line per
action option saying what it changes right away), `compact` (shorter payment choices; starting birds
chosen by naming them), `goal_status` (a block on the current round goal: each player's count against
the co-op difficulty, what the round would score if it ended now, turns left, earlier rounds).
`experiments/llm-prompts-moe.yaml` compares them against a local model; run
it with `--workers 1`, and `--resume` to continue after a stop (every finished game is saved in
`results/<experiment>/rows.jsonl`). `experiments/llm-mcts-moe.yaml` pairs the local model with a
tree-search partner under the co-op rules.

To total a run's tokens and estimate what it would cost on a paid model (current OpenRouter prices,
fetched from its public model list):
`.venv/bin/python -m wingsim.analysis.tokens results/<experiment>/rows.jsonl --model <openrouter id> ...`
(it also reads game logs, or `--price IN OUT` in dollars per million tokens).

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
  analysis/     tags.py, metrics.py, report.py, controls.py, tokens.py
  experiments/  *.yaml
  tests/
  runner.py     experiment runner
  tune.py       per-condition weight tuning for the greedy bot
  game.py       plays one game between agents
viewer/         browser replay viewer (Node; see viewer/README.md)
  app/viewer/   log reader, event reducer, 3D table, playback, panels
  components/   table pieces (mat, cards, goal board, birdfeeder, pieces) and their art
  art/          concept sheets and the script that cuts textures from them
  FORMAT-REQUESTS.md   log-format gaps for the simulator to fix
docs/           replay-log-format.md and sample logs
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
