# Replay log format (version 2)

This document describes the files the Wingspan co-op simulator writes for every fully logged game. It is written so that someone (or a model) who has never seen the simulator can build a play-by-play viewer from it. Everything a viewer needs is in the log plus one card reference; the game engine does not have to be run.

Sample files are in `docs/samples/`:

| File | What it is |
| --- | --- |
| `coop-3p-greedy-every-decision.jsonl.gz` | 3 players, co-op goals rule, a snapshot before every decision |
| `coop-3p-greedy-every-decision.json` | the same game exported as one plain JSON file with the card reference included |
| `baseline-2p-greedy-per-turn.jsonl.gz` / `.json` | 2 players, normal rules, a snapshot at the start of each turn only |
| `coop-2p-haiku-vs-greedy.jsonl.gz` / `.json` | 2 players, co-op goals: seat 0 is a language model (Claude Haiku 5.5, asked to explain briefly), seat 1 the greedy bot; a snapshot before every decision. Seat 0's decisions carry the full prompt and reply in `info` |

## 1. Files

**Native form:** one gzipped JSON Lines file per game, `logs/<experiment>/<condition>/<seed>-<players>p-<cell>.jsonl.gz`. Each line is one JSON object with a `"t"` field giving its type: `header`, `snapshot`, `decision` or `event`. Lines are in the order things happened.

**Exported form (easier in a browser):**

```
.venv/bin/python -m wingsim.engine.log export <log.jsonl.gz> <out.json>
```

writes `{"cards": {...}, "lines": [...]}`. `lines` is the same list of objects as the native file. `cards` is the card reference from section 7, so the viewer needs only this one file.

**Checking a log:** `.venv/bin/python -m wingsim.engine.log check <log.jsonl.gz>` rebuilds the game from the seed and the logged choices and compares every snapshot hash.

## 2. Conventions

| Thing | Encoding |
| --- | --- |
| Players (seats) | integers `0` to `n-1`, seated clockwise in that order. Group decisions belong to the player `"group"` |
| Food | index `0` invertebrate, `1` seed, `2` fish, `3` fruit, `4` rodent. A "food vector" is a list of 5 counts in that order |
| Habitat | index `0` forest, `1` grassland, `2` wetland |
| Die face | `0`-`4` are the five foods; `5` is the invertebrate/seed face |
| Bird cards | integer ids from wingsearch (2 to 261, not contiguous). Each bird exists once, so an id also identifies a bird on a mat |
| Bonus cards | ids 1000 to 1030 |
| Round goals | ids 2000 to 2024; `state.goals[r-1]` is the goal for round `r` |
| Nest types | `"bowl"`, `"cavity"`, `"ground"`, `"platform"`, `"wild"` (the star nest: counts as every type), `"none"` |
| Rounds | 1 to 4; each player takes 8, 7, 6, 5 turns. `round` is 5 once the game is over |
| `turn_no` | counts finished turns from 0. It is 0 throughout setup and round 1's first turn |
| `seq` | decision number, from 1. An event's `seq` is the decision that caused it; events before the first decision have `seq` 0 |

## 3. Line order

```
header
event (seq 0)                 the deal: goals, first player, tray, birdfeeder
snapshot (before_seq 1)       state before the first decision
decision (seq 1)
event, event, ... (seq 1)     everything that choice caused, up to the next decision
[snapshot (before_seq 2)]     present if this is a turn start, or if the log has a snapshot before every decision
decision (seq 2)
...
decision (seq N)              the last choice of the game
event ... (seq N)             includes round_end for round 4 and final_scoring
snapshot (before_seq null)    the final state
```

A decision with only one legal option is never asked, so it does not appear as a decision line; its effects appear as events under the decision before it. A single choice can therefore cause a long run of events (for example the last choice of a turn causes the tray refill, the next player's `turn_start`, and perhaps a whole round end).

## 4. Line types

### 4.1 `header` (always the first line)

| Field | Meaning |
| --- | --- |
| `version` | log format version, `2` |
| `engine_git` | git hash of the simulator (`+dirty` if there were uncommitted changes) |
| `card_commit` | wingsearch commit the card data came from |
| `config` | `players`; `plugins` (house rules in play and their settings, e.g. `{"coop_goals": {"penalty": "avg_x_d", "allowed_changes": [0, 1], "difficulty_range": [1, 5]}}`; empty for the normal game); `open_hands`; `win_condition` (`"individual"` or `"team_total"`); `team_target` |
| `seed` | the game's seed |
| `seats` | one entry per seat, in seat order: `type` (`"greedy"`, `"mcts"`, `"llm"`, `"random"`), `settings` (see section 6), `w` (motivation weight: 0 selfish, 1 team-minded), `group_share` |
| `group_policy` | text of the policy that answered group decisions (e.g. `"ladder(2,+1,0)"`), or `null` |
| `experiment`, `condition` | where the game came from |
| `snapshots` | `"turn"` or `"decision"`: how often snapshots were written (section 4.2) |

### 4.2 `snapshot`

The complete game state, hidden information included, at one moment. The log is for observers, so nothing is redacted.

| Field | Meaning |
| --- | --- |
| `before_seq` | the `seq` of the decision that is pending in this state; `null` for the final state |
| `turn_no`, `round` | as in section 2 |
| `player` | whose turn it is (`null` in the final snapshot). During setup this is not meaningful; use `state.pending[0]` |
| `turn_start` | `true` if this is the first decision of a turn |
| `hash` | checksum used by the replay check; a viewer can ignore it |
| `state` | the state object, section 5 |

When snapshots are written:

- Always: before the first decision, at the start of every turn, and at the end of the game.
- With `"snapshots": "decision"` in the header: before every decision as well. Then every decision line is preceded by a snapshot with the same `before_seq`.

To get per-decision snapshots, put `snapshots: decision` in the experiment file's `logging` section.

### 4.3 `decision`

One choice made by a player or by the group.

| Field | Meaning |
| --- | --- |
| `seq` | decision number |
| `round`, `turn_no` | when it happened |
| `player` | seat index, or `"group"` |
| `kind` | what was being decided (table in section 4.5) |
| `options` | the legal options, each a JSON array whose first element is a tag (section 4.5) |
| `labels` | one human-readable sentence per option, in the same order. A viewer can show these directly |
| `choice` | index into `options` (and `labels`) of the option chosen |
| `info` | the agent's reasoning data, or `null` (section 6) |

### 4.4 `event`

Something that happened as a result of a choice, at the level a viewer would animate. Fields: `seq`, `e` (the event name) and the event's own fields (section 4.6).

### 4.5 Decision kinds and option shapes

`bird`, `card` and `bonus` values are card ids. Use `labels` for display; use this table when the viewer needs to know what an option refers to (for example to highlight a card).

| `kind` | Asked when | Options |
| --- | --- | --- |
| `setup_keep_birds` | setup: which of the 5 dealt birds to keep | `["keep", [bird ids]]`: one option per subset (32) |
| `setup_discard_food` | setup: 1 food discarded per bird kept | `["discard_food", [food indexes]]` |
| `setup_keep_bonus` | setup: which of 2 bonus cards to keep | `["bonus", id]` |
| `set_difficulty` | co-op goals: group sets the difficulty before a round | `["difficulty", d]` |
| `action` | start of a turn | `["play", bird, habitat]`, `["food"]`, `["eggs"]`, `["cards"]` |
| `pay_food` | paying a bird's food cost, when there is more than one way | `["pay", food vector]` |
| `pay_egg` | removing an egg for the column cost | `["bird", id]` (the bird losing the egg) |
| `take_die` | taking food from the birdfeeder | `["die", face, food]`; `["skip"]` where declining is allowed |
| `reroll_feeder` | all dice in the feeder show one face | `["keep"]`, `["reroll"]` |
| `draw_card` | drawing a bird card | `["tray", bird]`, `["deck"]` |
| `lay_egg` | laying one egg | `["bird", id]`; `["skip"]` where declining is allowed |
| `bonus_trade` | the row's optional trade for one extra | `["skip"]`, `["discard_card", bird]` (forest), `["discard_food", food]` (grassland), `["discard_egg", bird]` (wetland) |
| `activate_power` | a brown, white or pink power may be used | `["activate", bird]`, `["skip"]` |
| `cache_food` | "you may cache it" | `["cache"]`, `["keep"]` |
| `optional_lay` | "you may also lay an egg on this bird" | `["lay"]`, `["skip"]` |
| `tuck_card` | tucking a card from hand | `["card", bird]` |
| `discard_card` | discard owed at the end of the turn | `["card", bird]` |
| `discard_egg` | an egg as the cost of a power | `["bird", id]` |
| `discard_food` | a food as the cost of a power | `["food", food]` |
| `choose_food` | choosing a food from the supply | `["food", food]` |
| `choose_first_player` | "starting with the player of your choice" | `["player", seat]` |
| `repeat_power` | which bird's power to repeat | `["bird", id]` |
| `move_bird` | moving a bird to another habitat | `["habitat", habitat]` |
| `play_extra` | "play an additional bird" | `["skip"]`, `["play", bird, habitat]` |
| `keep_bonus` | "draw 2 bonus cards and keep 1" | `["bonus", id]` |
| `draft_pick` | American Oystercatcher: each player takes one revealed card | `["card", bird]` |
| `end_turn` | only with plugins that add end-of-turn options | `["pass"]` plus plugin options |

Decisions inside one turn can belong to other players: pink powers, and powers that give every player a choice. Always read `player` from the decision line.

### 4.6 Events

`p` is the player affected.

| `e` | Fields | Meaning |
| --- | --- | --- |
| `setup` | `goals`, `first`, `tray`, `feeder` | the deal. `goals`: the 4 goal ids in round order; `first`: first player of round 1; `feeder`: list of die faces |
| `setup_kept_birds` | `p`, `birds` | starting birds kept (the rest were discarded) |
| `setup_discarded_food` | `p`, `food` | list of food indexes discarded |
| `bonus_kept` | `p`, `bonus` | a bonus card was kept (setup, or a bird's power) |
| `group_decision` | `kind`, `choice` | the group's answer, e.g. `choice: ["difficulty", 2]` |
| `round_start` | `round`, `first`, `goal` | a round begins |
| `turn_start` | `p`, `round`, `turn_no` | a turn begins |
| `action` | `p`, `action`, and for plays `bird`, `habitat` | `action` is `"play"`, `"food"`, `"eggs"`, `"cards"` or `"play_extra"` |
| `food_spent` | `p`, `food` (vector), `why`, sometimes `bird` | `why`: `"bird_cost"` (with `bird`), `"bonus_trade"`, `"power_cost"` |
| `egg_discarded` | `p`, `bird`, `why` | an egg left `bird`. `why`: `"bird_cost"`, `"bonus_trade"`, `"power_cost"` |
| `card_discarded` | `p`, `bird`, `why` | a card went from hand to the discard pile. `why`: `"bonus_trade"`, `"end_of_turn"` |
| `bird_played` | `p`, `bird`, `habitat`, `slot` | a bird entered a mat; `slot` is its position from the left, from 0 |
| `die_taken` | `p`, `face`, `food` | a die left the birdfeeder and the player gained that food |
| `feeder_reset` | `dice`, `why` | all 5 dice were rolled into the feeder. `why`: `"empty"`, `"all_same"` |
| `food_gained` | `p`, `food`, `n`, `source` | food from the supply (`source` is `"supply"`). Food from the feeder is reported by `die_taken` |
| `cards_drawn` | `p`, `source`, `birds` | cards entered a hand. `source`: `"deck"`, `"tray"`, `"draft"` |
| `cards_revealed` | `p`, `birds` | American Oystercatcher: the cards everyone picks from |
| `card_tucked` | `p`, `bird`, `source`, sometimes `card` | a card was tucked behind `bird`. `source`: `"hand"` or `"deck"`; `card` is given when its identity was seen |
| `eggs_laid` | `p`, `bird`, `n` | eggs were laid on `bird` |
| `food_cached` | `p`, `bird`, `food`, `n`, `source` | food was cached on `bird`. `source` `"supply"`: it came from the general supply; `"player"`: the player moved food they had just gained onto the bird, so it leaves their supply |
| `power` | `p`, `bird`, `color`, sometimes `repeated_by` | a power was used. `color`: `"brown"`, `"white"`, `"pink"` |
| `predator` | `p`, `bird`, `kind`, `success`, and `dice` or `card` | a predator hunted. `kind` `"roll"` has `dice` (faces rolled outside the feeder); `kind` `"look"` has `card` (the deck card looked at) |
| `bird_moved` | `p`, `bird`, `source`, `to` | a bird moved between habitats (indexes) |
| `tray_refill` | `tray` | the tray after refilling, at the end of a turn or round |
| `deck_reshuffled` | `cards` | the discard pile became the deck |
| `round_end` | `round`, `goal`, `counts`, `points`, `group_delta`, `group_score`, `info` | round-goal scoring. `counts`: each player's raw count; `points`: individual goal points awarded; `group_delta`: change in group score. With co-op goals `info` is `["coop", difficulty, success]`; otherwise `null` |
| `final_scoring` | `scores` | the final result, in the shape of section 5.3 |

## 5. The state object

### 5.1 Fields

| Field | Meaning |
| --- | --- |
| `phase` | `"setup"`, `"pre_round"`, `"turns"`, `"round_end"`, `"over"` |
| `round`, `turn_no` | as in section 2 |
| `first` | the first player of the current round |
| `turn` | whose turn it is |
| `actions_left` | turns each player still has this round |
| `deck` | bird ids; the **last** element is the top card |
| `discard` | the discard pile |
| `tray` | the face-up birds (up to 3) |
| `feeder` | die faces currently in the birdfeeder (1 to 5 of them; the other dice are outside it) |
| `bonus_deck`, `bonus_discard` | bonus card ids; last element is the top |
| `tucked` | ids of every tucked card in the game, in no useful order (which bird each sits behind is not recorded; see `players[].board[][].tucked` for counts) |
| `goals` | the 4 goal ids, in round order |
| `goal_points` | individual goal points banked so far, per player (always 0 with co-op goals) |
| `group_score` | the shared group score (0 without co-op goals) |
| `goal_log` | one entry per finished round: `[round, counts, points, group_delta, info]`, as in the `round_end` event |
| `players` | one object per seat, section 5.2 |
| `variant` | house-rule data. With co-op goals: `{"coop.d": difficulty}` (`null` before it is first set) |
| `pending` | `[player, kind, options]` for the decision about to be made (`player` is `-1` for the group); `null` when the game is over |
| `rng`, `stack`, `registers` | engine internals; a viewer should ignore them. `rng` is a 64-bit integer, larger than JavaScript numbers hold exactly |

### 5.2 A player

| Field | Meaning |
| --- | --- |
| `board` | three lists (forest, grassland, wetland), each up to 5 birds, left to right. A bird is `{"bird": id, "eggs": n, "cached": n, "tucked": n}` |
| `hand` | bird ids in hand |
| `bonus` | bonus card ids held |
| `food` | food vector |
| `pink_used` | ids of this player's pink-power birds already used since their last turn |

`cached` is a count; the food type is fixed by the bird and is given as `caches` in the card reference.

### 5.3 Scores

The `final_scoring` event carries:

```json
{"players": [{"birds": 31, "bonus": 3, "eggs": 14, "cached": 2, "tucked": 5, "goals": 0.0, "total": 55.0}, ...],
 "group": -4.5, "team_total": 160.5}
```

- A player's `total` is the sum of the six categories. `goals` is 0 under co-op goals.
- `team_total` = sum of the players' totals + `group`.
- A running score for any snapshot can be computed the same way from the state: for each bird on the mat add its printed points (`vp` in the card reference), its `eggs`, `cached` and `tucked`; add `goal_points`. Bonus-card points need the bonus rules and are easiest to show only at the end.

## 6. Agent data: `seats[].settings` and `decision.info`

`info` is `null` for random agents and for group policies that have nothing to say.

| Agent | `settings` in the header | `info` on its decisions |
| --- | --- | --- |
| `greedy` | `seed`, `chain_budget`, `weights` (its value-function weights) | `values`: up to 3 `[option, value]` pairs, best first, where value is the agent's estimate of its objective after that option; `options`: how many options there were |
| `mcts` | `iterations`, `minor_iterations`, `c`, `rollout`, `seed` | `iterations`: simulations run; `top`: up to 3 `[option, visits, mean value]`, most visited first |
| `llm` | `model`, `base_url`, `prompt` (template name), `reasoning` (whether it was asked to explain briefly before answering), `thinking` (hidden model-side reasoning effort, or `null` for off), `temperature`, `max_tokens`, `system_prompt` (the full system prompt this seat was given) | `model`; `prompt`: the full user message (the position as text plus numbered options); `replies`: the model's raw replies (two if the first could not be parsed); `chosen`: the option number picked, 1-based; `fallback`: `"random"` if no reply could be parsed, else `null`; `usage`: `prompt_tokens`, `completion_tokens`, `cost`, `reasoning_tokens`, `finish_reason` |
| group policy `estimate` | - | `estimates`: `[difficulty, expected change in group score]` pairs |

The option arrays inside `info` are the same arrays as in `options`.

## 7. Card reference

In an exported file this is the top-level `cards` object. Otherwise read `wingsim/data/cards.json`, which has the same information as lists. Keys are ids as strings.

| Section | Fields |
| --- | --- |
| `birds` | `name`; `color` (`"brown"`, `"white"`, `"pink"` or `null` for no power); `vp` (printed points); `nest`; `egg_limit`; `wingspan` (cm); `habitats` (list of habitat indexes it may be played in); `cost` (food vector); `wild` (number of any-food symbols in the cost); `either` (`true` if the cost is one food chosen from those marked in `cost`); `predator`; `flocking`; `text` (printed power text, with symbols written like `[fish]`); `caches` (food name this bird's power caches on it, or `null`) |
| `bonus` | `name`, `condition`, `vp_text` |
| `goals` | `text` (printed form, e.g. `"[egg] in [bowl]"`), `kind`, `param` |

Goal `kind` values: `birds_in_habitat` and `eggs_in_habitat` (`param` is a habitat name), `nest_birds_with_egg` and `eggs_in_nest` (`param` is a nest type), `egg_sets`, `total_birds`.

The card text belongs to Stonemaier Games and the data comes from wingsearch (GPL-3.0). Keep exported files private.

## 8. How to build a play-by-play view

**Simplest (logs with a snapshot before every decision).** Step through the decision lines. For decision `k`:

1. Draw the board from the snapshot whose `before_seq` is `k`.
2. Show who is deciding (`player`), what (`kind`), the `labels`, and which one was chosen (`choice`).
3. Show `info`: for an `llm` seat the prompt and replies; for `greedy` or `mcts` the top options and their values.
4. List the events with `seq` = `k` as "what happened next".
5. The next snapshot (`before_seq` = `k+1`, or `null` at the end) shows the result.

**Logs with per-turn snapshots only.** Start each turn from its snapshot (`turn_start: true`) and apply events to move forward inside the turn. Each event in section 4.6 says exactly what changed, with these details:

- `die_taken` removes one die showing `face` from `feeder` and adds 1 `food` to the player.
- `cards_drawn` with source `"tray"` removes the cards from `tray`; with `"deck"` it pops from the end of `deck`.
- `bird_played` removes the bird from the hand and appends it to the row.
- `card_tucked` with source `"hand"` removes `card` from the hand; either way add 1 to the bird's `tucked`.
- `food_cached` adds `n` to the bird's `cached`; when `source` is `"player"` also subtract it from the player's food.
- `tray_refill` and `feeder_reset` give the new tray and feeder outright.

If exactness inside a turn matters, ask for `snapshots: decision` logs instead; they are about twice as large (about 75 KB gzipped for a 3-player game against about 40 KB) and remove the need to apply events.

**Useful views for comparing agents:** a turn list with each player's action (`action` events); a per-seat panel showing the agent type and motivation weight from the header; the chosen option against the agent's own ranking in `info`; round summaries from `round_end` (counts, difficulty, success, group score change); and the final table from `final_scoring`.
