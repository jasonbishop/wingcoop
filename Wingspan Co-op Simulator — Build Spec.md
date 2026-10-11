# Wingspan Co-op Simulator — Build Spec

Oct 11, 2026 · @jason

## Purpose and research questions

Build a simulator that plays complete multiplayer Wingspan games between bot players, so we can test house rules meant to make the game cooperative. The first rule under test is a cooperative round-end goal rule (see Rule variants). Every game is logged in full so humans can replay it later.

The simulator must answer:

1. **Outcomes.** Does the co-op goal rule change the team total, the spread between players' scores, and how often the group meets the difficulty?
2. **Behavior.** Do players pick shared-benefit birds ("All players gain 1 fish", "Each player gains 1 die") more often when those birds are available? Do they stop taking feeder dice and tray cards that other players need?
3. **Motivation.** How do 1 and 2 change as players go from purely selfish to purely team-minded, and with 2 to 5 players?
4. **Difficulty choice.** Which difficulty policies score best? Is choosing the difficulty a real decision, or does one policy always win?
5. **Helping (later).** When the group fails, is it usually one player who fell behind with no way for the others to help? Does adding a help action fix that?

**Guiding principle:** results must come from play, never from assumptions built into the bots. Bots are told what to value (the objective) but never which cards or moves are good. See Agents for the hard rules that enforce this.

## Scope and tech choices

Version 1 covers the core set only, for 2 to 5 players, played to the official base-game rules plus the plugins in this spec.

| Item | v1 decision |
| --- | --- |
| Card set | Core only: 180 birds, 27 bonus cards, 16 goal faces (8 double-sided tiles) |
| Players | 2 to 5; no Automa or solo mode |
| Language | Python 3.12+; standard library for the engine; numpy and pandas for analysis only |
| Parallelism | One game per process via `multiprocessing`; games are independent |
| Tests | pytest; a test per effect template and per rule in the engine |
| Config | One YAML file per experiment (see Experiment runner) |
| Performance target | Thousands of greedy-bot games should finish in minutes on a laptop. Profile before optimizing. Keep state copy and `legal_actions` cheap, because tree search calls them constantly |

**Later, not v1:** the European, Oceania (nectar), Asia and Americas (hummingbird cards and the hummingbird garden) expansions, the replay viewer, and any human-playable interface. Design the card data and the effect system so expansions slot in without engine changes.

## Card data and effect system

Card data comes from [navarog/wingsearch](https://github.com/navarog/wingsearch). Bird powers are converted from their printed text into structured effect specs that the engine runs.

**Source files.** Vendor a copy into `data/raw/`, pinned to commit `43e5036` (31 Aug 2026), and filter to `Set == "core"`:

| File (in `src/assets/data/`) | Core records | Fields used |
| --- | --- | --- |
| `master.json` | 180 birds | Common name, Color, Power text, Predator, Flocking, Victory points, Nest type, Egg limit, Wingspan, Forest/Grassland/Wetland, food cost columns (Invertebrate, Seed, Fish, Fruit, Rodent, Wild, `/ (food cost)` for either/or costs), one X column per bonus card, id |
| `bonus.json` | 27 bonus cards | Bonus card, Condition, VP, id |
| `goals.json` | 16 goal faces | Goal, Reverse (the other side of the same tile), id. Take blue-side scoring from the rulebook, not from this file |

wingsearch is GPL-3.0, and the card text belongs to Stonemaier Games. Keeping a private research copy is fine. If the simulator is ever published, fetch the data at build time rather than redistributing it.

**Effect specs.** The 174 core birds with powers use about 70 distinct texts, which reduce to about 43 templates once numbers and food types are abstracted. Build the specs in three steps:

1. A converter matches each power text against regex templates and emits a spec, for example `{"timing": "brown", "steps": [{"op": "gain_food", "from": "supply", "food": "fish", "n": 1, "who": "all"}]}`.
2. `data/effect_overrides.yaml` hand-writes the specs for any text no template matches.
3. The build writes `data/effects.json`, which is checked into git and reviewed by a human. The build fails if any core bird with a power has no spec.

**Effect primitives** the specs are built from:

- Resource gains: `gain_food` (from supply or feeder), `draw_cards` (from deck or tray), `lay_eggs` (on this bird or any bird matching a nest filter), `cache_food`, `tuck` (from hand or deck), `draw_bonus_keep`
- Conditional or costed steps: `discard_to_gain`, `if_then`, `roll_dice_not_in_feeder` (predator), `look_at_deck_card` (wingspan test; predator), `repeat_power`, `play_additional_bird`, `move_bird`
- Who benefits: every step takes `who: self | all | each_from_feeder_in_order | fewest_in_habitat`
- Pink triggers: `on_other_player_lay_eggs`, `on_other_player_play_bird_in(habitat)`, `on_other_player_predator_success`, `on_other_player_gain_food(food)`. Each fires once between your turns, as in the rulebook

Any choice inside a step (which die, which card, which bird gets the egg, whether to use an optional power) goes to the deciding player as a decision request. See Game engine.

**Analysis tags** such as `shares_benefit`, `pink_reactive`, `predator`, `tucker` and `cacher` are derived automatically from the specs (for example, `shares_benefit` = any step with `who` not equal to `self`). About 20 core birds are `shares_benefit`. These tags live only in the analysis package and must never be importable by agent code.

## Game engine

The engine is a deterministic state machine. All game state is plain data, all randomness comes from a seeded generator stored in that state, and every choice from setup to final scoring is a decision request answered by a player.

&#91;embedded content: simulator architecture · 9 parts\]

Agents see only observations and answer decisions, plugins change the game only through hooks, and every event the engine produces lands in the replay log.

**State** (dataclasses that copy cheaply):

- Shared: round (1 to 4), first player, actions left per player (8, 7, 6, 5 by round), bird deck and discard, tray (3 face-up), birdfeeder (5 dice; the invertebrate/seed face counts as either) and dice outside it, bonus deck, the 4 goal tiles and which face is up, and the generator state
- Per player: board of 3 habitats × 5 slots, each slot holding a bird with its eggs, cached food by type and tucked-card count; hand; bonus cards; food supply by type
- `variant_state`: a dictionary plugins use for their own data, such as the current difficulty
- `decision_stack`: pending choices, including pink powers waiting to resolve

**Rules to implement**, following the official base-game rulebook:

- Setup: 5 birds, 2 bonus cards and 5 food per player. The player keeps some birds and pays 1 food for each, then keeps 1 bonus card. Four goal tiles are drawn with random faces
- The four actions: play a bird (food cost plus the egg cost for its column), gain food (forest), lay eggs (grassland) and draw cards (wetland). Each action's strength depends on how many birds are in that row. Brown powers activate right to left, and the optional discard-for-bonus slots work as printed
- The birdfeeder may be rerolled when all dice show one face, and is rerolled automatically when empty. The tray refills at the end of each turn
- Round end: score the goal, remove one action cube, clear and refill the tray, pass the first-player token
- Game end: score birds, bonus cards, goals, eggs, cached food and tucked cards. Ties are broken by leftover food
- Edge cases: where wingsearch carries a `rulings` entry for a bird, follow it, and cite it in that bird's test

**API** (the only way agents and plugins touch the game):

```
new_game(config, seed) -> State
pending_decision(state) -> Decision | None   # player, kind, legal options, context
apply(state, decision, choice) -> State       # raises on an illegal choice
observe(state, player) -> Observation         # what that player is allowed to see
is_over(state) / final_scores(state)
```

Pink powers resolve in turn order immediately after the action that triggers them, each through a decision request to its owner. A game is fully reproducible from its seed plus its list of choices, and the replay log depends on this (see Replay logging).

**Hidden information.** Agents receive an `Observation`, never the `State`. The deck order is always hidden. Other players' hands and bonus cards are hidden unless `open_hands` is on (default on; see Rule variants). Search agents fill in the hidden parts by sampling from what remains unseen.

## Rule variants (plugins)

Each house rule is a plugin module, turned on and configured from the experiment file. Plugins change the game only through the hooks below, so the base engine never contains variant logic.

**Hooks:**

| Hook | When it runs | What it can do |
| --- | --- | --- |
| `on_setup` | After normal setup | Initialize `variant_state` |
| `before_round` | Before rounds 1 to 4 | Raise group decisions |
| `extra_options` | Whenever a player's options are listed | Add legal options (for example a help action) |
| `on_event` | After every engine event | React to events such as food gained or a bird played |
| `round_end_scoring` | At round end | Replace or add to goal scoring |
| `final_scoring` | At game end | Add to individual scores and/or the group score |

A **group decision** is a decision request owned by the group rather than by one player. A group policy (see Agents) answers it.

### Plugin 1: cooperative round goals (`coop_goals`)

This plugin replaces normal goal scoring. Goals are drawn as usual and use the blue side of the goal board: each player's count for the round's goal is capped at 5, the blue side's maximum. No individual goal points are scored.

1. After setup, with all four goals visible, the group sets the difficulty *d*, from 1 to 5.
2. At the end of each round, each player's result is *c* = min(count, 5).
3. If every player has *c* ≥ *d*, the group score rises by mean(*c*) × *d*. Otherwise it falls by the configured penalty.
4. After rounds 1 to 3, the group picks the next difficulty from the allowed changes, kept within 1 to 5.

Example with 4 players at *d* = 3: counts 5, 4, 3, 3 all meet 3, so the group gains 3.75 × 3 = 11.25. Counts 5, 4, 3, 2 fail, so the group loses 3.5 × 3 = 10.5. Scores are kept unrounded.

| Setting | Default | Options |
| --- | --- | --- |
| `penalty` | `avg_x_d` (mean × *d*) | `d_x_d`, `flat:<n>` |
| `allowed_changes` | `[0, +1]` | `[-1, 0, +1]` |
| `difficulty_range` | 1 to 5 | Any range within 1 to 5 |

### Plugin 2: help action (`help_action`, off by default)

Once per round, a player may give 1 food from their supply or 1 card from their hand to another player, as a free action at the start or end of their own turn. Settings: `limit_per_round` (default 1), `what` (default `[food, card]`). It exists to test whether failures come from one player falling behind with no way for the others to help.

### Setting: open hands (`open_hands`, on by default)

All players can see every hand and every bonus card. The deck order stays hidden. This stands in for the table talk real cooperative players would have.

### Baseline

The comparison condition is the normal game with blue-side goal scoring: each player scores their capped count individually, with no group score. Every experiment runs this baseline on the same seeds as the variant.

## Scoring and win conditions

Every game records both individual scores and the team total. A setting picks which one the report headlines as the result.

- **Individual score:** points from birds, bonus cards, eggs, cached food and tucked cards, plus goal points in the baseline. Record each category separately.
- **Group score:** the running total from `coop_goals` (0 when the plugin is off).
- **Team total** = the sum of all individual scores + the group score.

| Setting | Options | Meaning |
| --- | --- | --- |
| `win_condition` | `individual` | Normal Wingspan: the highest individual score wins, ties broken by leftover food |
|  | `team_total` | The table plays for the biggest team total. An optional `team_target` turns it into win/lose against a threshold |

The win condition only changes how results are reported. What the bots actually try to maximize is set separately by each player's motivation weight (see Agents). That separation is deliberate: it lets us test the rule with selfish players at a table that is officially playing for the team.

## Agents

Agents are game-playing algorithms, not language models, apart from one optional adapter. Each agent maximizes an objective set by its motivation weight *w*. It works out what to do by simulating moves with the engine, never from built-in knowledge of cards.

**Objective.** For player *i*: utility = (1 − *w*) × own score + *w* × (team total ÷ number of players). Dividing by the player count keeps both terms on the same scale. *w* = 0 is purely selfish, *w* = 1 purely team-minded. *w* is set per player, so mixed tables (one selfish player among team players) are possible.

**Interface:**

```
class Agent:
    def start(self, config, player_index, objective): ...
    def choose(self, observation, decision) -> choice: ...
    def info(self) -> dict  # optional reasoning data for the replay log
```

**Agent types:**

1. **Random:** picks uniformly among legal options. Used for fuzz-testing the engine.
2. **Greedy:** applies each option to a copy of the game with hidden cards sampled, then scores the result with a generic value function. The function counts points banked plus weighted resources: food, cards, eggs, open slots, and engine value. Engine value is estimated by running the bird's power once on a copy of the game and counting what it produced, multiplied by the expected number of activations left. Both the agent's own position and the other players' positions are valued with the same function, combined by the objective.
3. **Tree search (main agent for behavior questions):** information-set Monte Carlo tree search. It samples hidden cards, plays games to the end using random or greedy moves, and scores the final state with the objective. Its budget per decision (iterations or milliseconds) is configurable.
4. **Language model (optional, spot checks only):** calls any OpenAI-compatible endpoint (OpenRouter, Ollama, LM Studio, vLLM) using a configured `base_url`, `model` and API-key environment variable. The prompt holds a rules summary, the objective in plain words, the observation as text, and a numbered list of legal options. The reply is parsed as an option number; if it can't be parsed, retry once, then pick at random and log it. Log all prompts and replies. Intended for a few dozen games as an independent cross-check.

**Tuning the greedy bot under each rule set.** Tune the value-function weights by self-play (hill-climbing or CMA-ES) separately for each condition, and save them per condition. How the tuned weights differ between baseline and variant is itself a result.

**Group policies** answer group decisions, such as setting the difficulty:

- `fixed(d)`: always *d*
- `ladder(start, on_success, on_fail)`: for example, start at 2, +1 after a success, 0 or −1 after a failure, limited to the allowed changes
- `estimate`: runs quick rollouts with the table's own agents to estimate the chance that every player reaches each *d*, then picks the *d* with the best expected group score

### Agent purity rules (hard requirements)

These stop the simulator from assuming the answers it is meant to find.

1. Agent code must not branch on a card's identity, name, power text or analysis tags. Everything an agent knows about a card comes from simulating it with the engine and from attributes printed on the card (points, cost, nest, egg limit, habitats, wingspan).
2. Agents must not check which plugins are active. They see only legal options, observations and their objective. Group policies are the exception, because they answer the plugin's own decisions.
3. The `agents` package must not import `analysis`. Enforce this with an import-contract test in CI, plus a test that greps `agents/` for bird names.
4. Before a "no effect" result is trusted, the agent must pass the positive and negative controls (see Validation and testing).

## Experiment runner and metrics

An experiment is one YAML file that defines a grid of conditions. Every cell of the grid is run on the same list of seeds, so the variant and the baseline start from identical shuffles and comparisons are paired.

```yaml
name: coop-goals-v1
seeds: {start: 1, count: 2000}
players: [2, 3, 4, 5]
conditions:
  baseline:  {plugins: {}, win_condition: individual}
  coop:      {plugins: {coop_goals: {penalty: avg_x_d, allowed_changes: [0, 1]}, open_hands: true},
              win_condition: team_total}
agents:      {type: greedy, weights: tuned/{condition}.json}
motivation:  [0.0, 0.5, 1.0]          # w, applied to every player
group_policy: ["fixed(2)", "fixed(3)", "ladder(2,+1,0)", estimate]
logging:     {level: summary, full_sample: 0.02, full_if: [group_fail_round_4, spread_gt_40]}
```

**Outputs:** a per-game table (Parquet) with seed, condition, player count, agent, *w*, policy, every score category per player, group score, team total, difficulty and counts per round, success flags and which players missed. A decision-level table is built from the replay logs. A generated report (Markdown plus charts) compares conditions using paired differences and 95% confidence intervals.

**Metrics:**

| Question | Metric |
| --- | --- |
| Outcomes | Team total; individual mean; score spread (max − min and standard deviation); goal success rate by round and difficulty; group score |
| Weakest link | For each failure: who missed, by how much, and whether it is the same player across rounds |
| Shared-benefit birds | Pick rate when available: among "play a bird" decisions where the bird was affordable and had a slot, how often it was chosen, for `shares_benefit` birds vs others with similar points and cost. The same for taking birds from the tray |
| Denial | When taking a feeder die or tray card, whether it was something another player needed (for a die: a food type another player needs to afford a bird in their hand) |
| Helping | Help actions used: who gave what to whom, and whether the receiver was the player furthest below the difficulty |
| Difficulty | Difficulty paths chosen, and expected group score by policy and player count |
| Sanity | First-player advantage, action mix, game length |

## Replay logging

Every game that is fully logged can be watched afterwards, turn by turn, without re-running the engine. Building the viewer is follow-on work. v1 only has to write logs that a viewer can render.

**Format:** one gzipped JSON Lines file per game, `logs/<experiment>/<condition>/<seed>-<players>p.jsonl.gz`.

- **Header line:** log format version, engine git hash, card-data commit, the full resolved config, seed, and each seat's agent type, settings and *w*.
- **Snapshot lines:** the complete game state at the start of every turn, including hidden information (deck order, every hand), since the log is for observers. A viewer can jump to any turn from these.
- **Decision lines:** sequence number, round, turn, deciding player (or `group`), decision kind, the options offered, the choice made, and the agent's `info()` (for example the tree search's visit counts and values for its top 3 options, or the language model's raw reply). A viewer can use this to show why a move was made.
- **Event lines:** what the choice caused, at the level a viewer animates: dice taken or rolled, food gained (by whom, from where), cards drawn or tucked, eggs laid, powers triggered (bird, owner, color), birdfeeder reset, tray refill, round-end scoring (counts, difficulty, success, group score change), and final scoring by category.

Events refer to birds by wingsearch `id`. A viewer resolves names and artwork from the same pinned card data.

**Replay check:** `replay(log)` rebuilds the game from the seed and the logged choices and compares a hash of each snapshot. A mismatch is a bug: hidden randomness or nondeterministic iteration order.

**Volume:** full logs for all games would be large. `logging.level` is `summary` or `full`; `full_sample` keeps a random fraction, and `full_if` always keeps games that look unusual. A single game can be re-run later with full logging from its seed, as long as the agents are seeded too.

## Validation and testing

No experiment result is trusted until the engine passes its rule tests and the agents pass both controls below.

| Check | What passes |
| --- | --- |
| Effect tests | Each of the \~43 templates and every override runs on a fixture state and produces exactly the expected change |
| Rule tests | Egg cost by column, birdfeeder reroll and reset, tray refill, pink powers once between turns, round-end cube removal, final scoring categories, tiebreak |
| Plugin tests | `coop_goals` reproduces the worked example (+11.25 and −10.5), penalty options, allowed changes, the 1 to 5 limit; `help_action` limits; `open_hands` observation contents |
| Fuzz | 10,000 random-agent games across 2 to 5 players with no exceptions |
| Invariants | All 180 birds always accounted for (deck + tray + hands + boards + tucked + discard); no negative food or eggs; egg limits respected; observations never contain hidden information the player shouldn't see |
| Determinism | Same seed and choices produce an identical log hash; `replay()` passes on every full log |
| Calibration | Base-game scores and action mix for greedy and tree-search bots look like experienced human play. Large gaps point to engine or agent bugs |
| Purity | The import contract and the bird-name grep from the agent purity rules pass in CI |
| Positive control | Fully team-minded (*w* = 1) tree-search bots in 5-player `coop_goals` games pick `shares_benefit` birds noticeably more often when available than selfish bots do. If they don't, the agent is too weak to detect the effect and its "no effect" results can't be trusted |
| Negative control | Selfish bots in the baseline show no special preference for `shares_benefit` birds over birds of similar points and cost |
| Cross-check | A few dozen language-model games per key condition. Treat agreement with the bots as supporting evidence, and disagreement as a reason to read those replays |

## Build order and follow-on work

Build in this order. Each milestone ends with its tests passing, and replay logging exists from milestone 2 onward so every bug can be watched.

1. **Card data:** vendor the files, write the converter and overrides, generate `effects.json` and review it by hand. Done when all 174 core powers have specs and template tests.
2. **Base engine:** state, rules, decision requests, observations, replay logging, random agent. Done when the fuzz, invariant and determinism checks pass.
3. **Greedy agent and baseline:** the value function, baseline runs, calibration.
4. **Plugins:** hooks, `coop_goals`, `open_hands`, group policies.
5. **Experiment runner:** YAML grid, paired seeds, parallel runs, per-game tables, report.
6. **Tree-search agent:** information-set Monte Carlo tree search, then the positive and negative controls.
7. **Per-condition tuning** of the greedy bot's weights.
8. **Language-model adapter** and cross-check runs.
9. **`help_action`** experiments.

Suggested layout:

```
wingsim/
  data/            raw/ (vendored wingsearch files), effect_overrides.yaml, effects.json
  engine/          state.py, rules.py, effects.py, api.py, observe.py, log.py
  plugins/         coop_goals.py, help_action.py, open_hands.py
  agents/          random.py, greedy.py, mcts.py, llm.py, group_policies.py
  analysis/        tags.py, metrics.py, report.py   # agents may not import this
  experiments/     *.yaml
  tests/
```

**Follow-on, not v1:** a replay viewer that renders the logs; expansions (Americas first, for its hummingbird cards); more cooperative rules as plugins.
