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

**Older logs:** logs written before 13 October 2026 are also version 2 but lack the events and fields marked *(added)* below. `.venv/bin/python -m wingsim.engine.log relog <old.jsonl.gz> <new.jsonl.gz>` writes the same game again in the current form, keeping every choice and all agent data (language-model prompts and replies included), without calling any agent.

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
| `goal_counts` | *(added)* each player's count so far for the current round's goal, during the turns of a round; `null` during setup and in the final snapshot. A count includes everything on the mat right now, so it can go down (an egg spent) as well as up |
| `scores` | *(added)* the score as it stands, in the shape of section 5.3, bonus cards included. Before the game ends it is provisional: goal points are only those banked at earlier round ends |
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
| `draw_card` | drawing a bird card into the hand (followed by `cards_drawn`), or taking one for the American Oystercatcher draft (followed by `card_set_aside`) | `["tray", bird]`, `["deck"]` |
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
| `bonus_drawn` | `p`, `bird`, `cards` | *(added)* a power (on `bird`) took bonus cards off the top of `bonus_deck`, in the order listed, and set them aside (`state.set_aside.bonus`) until one is kept. If the bonus deck runs out part way, this event comes once before `bonus_reshuffled` and once after it |
| `bonus_reshuffled` | `cards`, `deck` | *(added)* the bonus deck was empty, so `bonus_discard` was shuffled to become it. `cards` is how many; `deck` the new order (last element on top) |
| `bonus_kept` | `p`, `bonus`, `discarded` | a bonus card was kept, at setup (from the player's 2 dealt cards) or by a power (from `set_aside.bonus`). *(added)* `discarded`: the cards not kept, which go on top of `bonus_discard` in that order |
| `group_decision` | `kind`, `choice` | the group's answer, e.g. `choice: ["difficulty", 2]` |
| `round_start` | `round`, `first`, `goal` | a round begins |
| `turn_start` | `p`, `round`, `turn_no` | a turn begins. The player's `pink_used` is emptied |
| `turn_end` | `p` | *(added)* a turn is over: `actions_left[p]` goes down by 1, `turn` moves to the next seat and `turn_no` up by 1. It follows the end-of-turn `tray_refill` |
| `action` | `p`, `action`, and for plays `bird`, `habitat` | `action` is `"play"`, `"food"`, `"eggs"`, `"cards"` or `"play_extra"` |
| `food_spent` | `p`, `food` (vector), `why`, sometimes `bird` | `why`: `"bird_cost"` (with `bird`), `"bonus_trade"`, `"power_cost"` |
| `egg_discarded` | `p`, `bird`, `why` | an egg left `bird`. `why`: `"bird_cost"`, `"bonus_trade"`, `"power_cost"` |
| `card_discarded` | `p`, `bird`, `why` | `bird` went on top of the discard pile. `why` `"bonus_trade"` or `"end_of_turn"`: from the hand. *(added)* `"predator_miss"`: the deck card a predator looked at and missed (it had already left the deck at the `predator` event) |
| `bird_played` | `p`, `bird`, `habitat`, `slot` | a bird entered a mat; `slot` is its position from the left, from 0 |
| `die_taken` | `p`, `face`, `food` | a die left the birdfeeder and the player gained that food |
| `feeder_reset` | `dice`, `why` | all 5 dice were rolled into the feeder. `why`: `"empty"`, `"all_same"` |
| `food_gained` | `p`, `food`, `n`, `source` | food from the supply (`source` is `"supply"`). Food from the feeder is reported by `die_taken` |
| `cards_drawn` | `p`, `source`, `birds` | cards entered a hand. `source`: `"deck"` (off the top), `"tray"`, or `"draft"` (from `set_aside.birds`) |
| `card_set_aside` | `p`, `source`, `bird` | *(added)* American Oystercatcher: the owner took `bird` from `source` (`"tray"` or `"deck"`) for the draft; it is in `set_aside.birds` until someone picks it. The tray is not refilled until the end of the turn |
| `cards_revealed` | `p`, `birds` | American Oystercatcher: all the cards set aside are shown; players then take them with `draft_pick` decisions (`cards_drawn` with source `"draft"`), the owner last |
| `card_tucked` | `p`, `bird`, `source`, `card` | `card` was tucked behind `bird`. `source`: `"hand"`, `"deck"` (off the top), or *(added)* `"look"` (the card a predator just looked at, already off the deck). *(added)* `card` is always given |
| `eggs_laid` | `p`, `bird`, `n` | eggs were laid on `bird` |
| `food_cached` | `p`, `bird`, `food`, `n`, `source` | food was cached on `bird`. `source` `"supply"`: it came from the general supply; `"player"`: the player moved food they had just gained onto the bird, so it leaves their supply |
| `power` | `p`, `bird`, `color`, sometimes `repeated_by` | a power was used. `color`: `"brown"`, `"white"`, `"pink"` |
| `predator` | `p`, `bird`, `kind`, `success`, and `dice` or `card` | a predator hunted. `kind` `"roll"` has `dice` (faces rolled outside the feeder; the feeder is unchanged). `kind` `"look"` has `card`: the top card of the deck, which leaves the deck now. Next comes `card_tucked` with source `"look"` on a hit, or `card_discarded` with why `"predator_miss"` on a miss |
| `bird_moved` | `p`, `bird`, `source`, `to` | a bird moved between habitats (indexes). It is always the rightmost bird of row `source` and goes to the right-hand end of row `to`, keeping its eggs, cache and tucked cards |
| `tray_cleared` | `birds` | *(added)* at the end of a round, the birds left in the tray go on top of the discard pile, in the order listed |
| `tray_refill` | `tray` | the tray after refilling from the top of the deck, at the end of a turn or round (emitted every time, even if nothing changed). The cards already there keep their places and new ones are added at the end. If the deck runs out part way, one `tray_refill` comes before `deck_reshuffled` and another after it |
| `deck_reshuffled` | `cards`, *(added)* `deck` | the deck was empty, so the discard pile was shuffled to become it. `cards` is how many; `deck` is the new order (last element on top) |
| `round_end` | `round`, `goal`, `counts`, `points`, `group_delta`, `group_score`, `info` | round-goal scoring. `counts`: each player's raw count; `points`: individual goal points awarded; `group_delta`: change in group score. With co-op goals `info` is `["coop", difficulty, success]`; otherwise `null` |
| `final_scoring` | `scores` | the final result, in the shape of section 5.3 |

## 5. The state object

### 5.1 Fields

| Field | Meaning |
| --- | --- |
| `phase` | `"setup"`, `"turns"` or `"over"` in every snapshot. (The engine also has `"pre_round"` and `"round_end"`, but no decision is ever pending in them, so no snapshot shows them) |
| `round`, `turn_no` | as in section 2 |
| `first` | the first player of the current round |
| `turn` | whose turn it is |
| `actions_left` | turns each player still has this round |
| `deck` | bird ids; the **last** element is the top card |
| `discard` | the discard pile; the **last** element is the top (most recently discarded) |
| `tray` | the face-up birds (up to 3) |
| `feeder` | die faces currently in the birdfeeder (1 to 5 of them; the other dice are outside it) |
| `bonus_deck`, `bonus_discard` | bonus card ids; the last element is the top (for `bonus_discard`, the most recently discarded) |
| `tucked` | ids of every tucked card in the game, in no useful order (which bird each sits behind is not recorded; see `players[].board[][].tucked` for counts) |
| `goals` | the 4 goal ids, in round order |
| `goal_points` | individual goal points banked so far, per player (always 0 with co-op goals) |
| `group_score` | the shared group score (0 without co-op goals) |
| `goal_log` | one entry per finished round: `[round, counts, points, group_delta, info]`, as in the `round_end` event |
| `players` | one object per seat, section 5.2 |
| `variant` | house-rule data. With co-op goals: `{"coop.d": difficulty}`. It is `{}` during setup, `{"coop.d": null}` from the first `round_start` until the group first sets the difficulty |
| `set_aside` | *(added)* `{"birds": [...], "bonus": [...]}`: cards in no pile, hand or mat because a choice about them is pending: the bonus cards a power drew (until `bonus_kept`) and the birds taken for the American Oystercatcher draft (until each is picked). Both lists are empty almost all the time |
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
- Every snapshot carries the running score in this shape as `scores` (section 4.2), bonus cards included, so a viewer never needs to compute one. Between snapshots, the parts that events change are easy to keep up: a bird's printed points (`vp` in the card reference), its `eggs`, `cached` and `tucked`, and `goal_points`; bonus points need the bonus rules, so take them from the next snapshot.

## 6. Agent data: `seats[].settings` and `decision.info`

`info` is `null` for random agents and for group policies that have nothing to say.

| Agent | `settings` in the header | `info` on its decisions |
| --- | --- | --- |
| `greedy` | `seed`, `chain_budget`, `weights` (its value-function weights) | `values`: up to 3 `[option, value]` pairs, best first, where value is the agent's estimate of its objective after that option; `options`: how many options there were |
| `mcts` | `iterations`, `minor_iterations`, `c`, `rollout`, `seed` | `iterations`: simulations run; `top`: up to 3 `[option, visits, mean value]`, most visited first |
| `llm` | `model`, `base_url`, `prompt` (template name), `reasoning` (whether it was asked to explain briefly before answering; *(added)* `"full"`: asked for a few short paragraphs), `thinking` (hidden model-side reasoning effort, or `null` for off), `temperature`, `max_tokens`, *(added)* `plan`, `outcomes`, `compact`, `goal_status`, `talk`, `coach`, `digest` (prompt features, see `wingsim/agents/llm.py`), `system_prompt` (the full system prompt this seat was given), *(added)* `coach_system_prompt` (the coach call's system prompt, or `null` without `coach`; missing in logs before 2026-10-17 evening), *(added)* `reply_format` (`"lines"`: the reply ends with `ANSWER:`, `SAY:` and `TO COACH:` lines; `"json"`: with one JSON object such as `{"answer": 2, "say": "...", "to_coach": "..."}`, the keep-birds answer as a list; a JSON reply without one is still read the line way), `votes` (`true` when the seat helps set the difficulty under the `talk` group policy; its system prompt then has a SETTING THE DIFFICULTY section). Both are missing in logs before 2026-10-18, which are `"lines"` and `false` | `model`; `prompt`: the full user message (the position as text plus numbered options); `replies`: the model's raw replies (two if the first could not be parsed); `chosen`: the option number picked, 1-based; `fallback`: `"random"` if no reply could be parsed, else `null`; `usage`: `prompt_tokens`, `completion_tokens`, `cost`, `reasoning_tokens`, `finish_reason`, for the *last* call only. *(added)* `usage_all`: the same, one entry per reply (parallel to `replies`); `limits`: the token limit each call was given (`max_tokens`; `max_tokens + 600` at action decisions of a plan seat; 300 for a reasoning seat's "finish now" retry). A reply whose `completion_tokens` reaches its limit was cut off: some local servers report `finish_reason: "stop"` even then. When `fallback` is `"random"`, `chosen` is the randomly picked option. *(added)* `thinking`: present only when the endpoint returned hidden thinking apart from the answer (thinking mode on); a list parallel to `replies`, each entry the thinking text or `null`. A reply may also begin with a lone `<think>` tag and no closing tag (a local-server quirk with thinking off); that text is the visible reasoning, not hidden thinking. *(added)* With `plan` on: `plan` (the plan shown in this prompt, or `null`) and `plan_updated` (the plan the reply wrote, at action decisions; `null` if none). A plan is written only at `kind == "action"` decisions, as a block from a line starting `PLAN:` to `END PLAN` (when the model leaves `END PLAN` out, the block ends where an `ANSWER:` or the next `PLAN:` line begins, or at the end of the reply), with five lines: `Engine:`, `Bonus target:`, `Round goal:`, `Need next:`, `Pivot if:` (the model may not keep to them). `plan_updated` is the last such block in the first reply, or in the retry if the first has none; it then becomes the `plan` of later prompts. The answer is read outside plan blocks. *(added)* With `talk` on: `said` at `kind == "action"` decisions, the message the reply left for the other players (its last line starting `SAY:`, at most 300 characters), or `null`. The seats with `talk` share one table: each one's prompt shows the 10 most recent messages, oldest first, with the round, `turn_no` and player of each, so the table at any decision can be rebuilt from the `said` of the decisions before it. *(added)* With `coach` or `digest` on, every `kind == "action"` decision also has `aux`: the extra calls made before it, in order, each `{role, prompt, reply, thinking, usage, limit, notes}`. `role` is `"digest"` (made only when another seat said something since this seat's last digest; it gets the seat's own system prompt) or `"coach"` (its system prompt is `wingsim/prompts/coach.md` with the seat's objective and the rules); `notes` is what the call wrote under `TALK NOTES:` or `NOTES:`. `coach` and `digest` repeat this decision's notes (or `null`). The coach's notes are shown in the seat's prompts for the rest of its turn, the talk notes until the next digest. `to_coach`: the reply's `TO COACH:` line, shown to the coach at its next review with its own last notes, or `null`. These calls are counted in the row's `llm_*` totals but not in `usage_all`. Notes are kept to 1,000 characters, cut at a line end, with any `ANSWER:` line or JSON answer the call gave taken out (600 characters, cut anywhere and answers kept, in logs before 2026-10-18). In the `json` format, `said` and `to_coach` come from the JSON object's `say` and `to_coach` fields (or from `SAY:`/`TO COACH:` lines when it has none), and a plan block also ends where the JSON answer starts. Logs written before this rule (to 2026-10-17) cut a block without `END PLAN` only at the end of the reply: an `ANSWER:` after such a block was missed (the retry gave the same move), and its `plan_updated` can hold the earlier plan, the `ANSWER:` line and the new plan run together. |
| group policy `estimate` | - | `estimates`: `[difficulty, expected change in group score]` pairs |
| *(added)* group policy `talk` | - | The seats with `talk` set the difficulty (`kind == "set_difficulty"`). `votes`: each proposal in order, `{pass, player, d, round, turn_no}` plus that seat's usual `llm` info for the call (`prompt`, `replies`, `chosen`, `said`, `usage_all`, ...) and `posted`, the message it put on the table: `(proposes d = N)` followed by its message, if any. In pass 1 each seat proposes in seat order, seeing the proposals before its own in the table talk; if they disagree there is a pass 2, and then the lowest proposal is set. `agreed`: whether the last pass agreed; `d`: the difficulty set. The posted messages are part of the table talk, so rebuilding the table at a decision takes the `said` of action decisions and the `posted` of the votes before it. |

The option arrays inside `info` are the same arrays as in `options`.

## 7. Card reference

In an exported file this is the top-level `cards` object. Otherwise read `wingsim/data/cards.json`, which has the same information as lists. Keys are ids as strings.

| Section | Fields |
| --- | --- |
| `birds` | `name`; *(added)* `scientific` (scientific name); `color` (`"brown"`, `"white"`, `"pink"` or `null` for no power); `vp` (printed points); `nest`; `egg_limit`; `wingspan` (cm); `habitats` (list of habitat indexes it may be played in); `cost` (food vector); `wild` (number of any-food symbols in the cost); `either` (`true` if the cost is one food chosen from those marked in `cost`); `predator`; `flocking`; `text` (printed power text, with symbols written like `[fish]`); `caches` (food name this bird's power caches on it, or `null`) |
| `bonus` | `name`, `condition`, `vp_text` (printed scoring, symbols written like `[point]`) |
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

**Logs with per-turn snapshots only.** Start each turn from its snapshot (`turn_start: true`) and apply the events in order to move forward inside the turn. Applying every event after one snapshot gives exactly the next snapshot; `wingsim/tests/reduce_log.py` is a short reference implementation, and the tests check it on hundreds of games. What each event changes:

| Event | Change to the state |
| --- | --- |
| `setup_kept_birds` | the hand becomes `birds`; the other dealt birds go on top of `discard`, in hand order |
| `setup_discarded_food` | subtract 1 of each listed food |
| `bonus_drawn` | pop each of `cards` off the end of `bonus_deck` into `set_aside.bonus` |
| `bonus_reshuffled`, `deck_reshuffled` | the deck becomes `deck`; its discard pile becomes empty |
| `bonus_kept` | add `bonus` to the player's `bonus`; move `discarded` to the end of `bonus_discard`. Take both from `set_aside.bonus` if they are there (a power), otherwise from the player's `bonus` (setup) |
| `group_decision` | for `set_difficulty`, set `variant["coop.d"]` |
| `round_start` | set `round` and `first`; `turn` = `first`; `actions_left` = 8, 7, 6 or 5 for everyone; `phase` = `"turns"`; with co-op goals, `variant["coop.d"]` exists from now on |
| `turn_start` | set `turn`, `turn_no`, `round`; empty the player's `pink_used` |
| `turn_end` | `actions_left[p]` − 1; `turn` = next seat; `turn_no` + 1 |
| `food_spent` | subtract the food vector |
| `egg_discarded` | the bird's `eggs` − 1 |
| `card_discarded` | append `bird` to `discard`; unless `why` is `"predator_miss"`, remove it from the hand |
| `bird_played` | remove the bird from the hand; insert it in row `habitat` at position `slot` with no eggs, cache or tucked cards |
| `die_taken` | remove one die showing `face` from `feeder`; add 1 `food` |
| `feeder_reset` | `feeder` = `dice` |
| `food_gained` | add `n` of `food` |
| `cards_drawn` | for each bird: source `"tray"` removes it from `tray`, `"deck"` pops it off the end of `deck`, `"draft"` removes it from `set_aside.birds`; then append it to the hand |
| `card_set_aside` | remove `bird` from `tray`, or pop it off `deck`; append it to `set_aside.birds` |
| `card_tucked` | source `"hand"` removes `card` from the hand, `"deck"` pops it off `deck`, `"look"` takes nothing; append `card` to `tucked`; the bird's `tucked` + 1 |
| `eggs_laid` | the bird's `eggs` + `n` |
| `food_cached` | the bird's `cached` + `n`; with source `"player"`, also subtract `n` of `food` from the player |
| `power` | if `color` is `"pink"`, add `bird` to the player's `pink_used` |
| `predator` | with `kind` `"look"`, pop `card` off `deck` (its next event says where it went) |
| `bird_moved` | move the last bird of row `source` to the end of row `to` |
| `tray_cleared` | append the tray to `discard`; the tray becomes empty |
| `tray_refill` | pop each card beyond the current tray's length off `deck`; `tray` = `tray` |
| `round_end` | append `[round, counts, points, group_delta, info]` to `goal_log`; add `points` to `goal_points`; set `group_score`; `first` moves one seat on; `round` + 1 (it is 5 after round 4) |
| `final_scoring` | `phase` = `"over"` |
| `setup`, `action`, `cards_revealed` | nothing (they announce; other events make the changes) |

The events that make up the end of a turn come in this order: `tray_refill`, `turn_end`, then either the next `turn_start` or, after a round's last turn, `round_end`, `tray_cleared`, `tray_refill` and (unless the game is over) the group's decision and `round_start`. `goal_counts`, `scores`, `players[].board[][]` and the rest can be shown from the snapshots; between snapshots, `scores` are not kept up by events.

If exactness inside a turn matters, ask for `snapshots: decision` logs instead; they are about twice as large (about 75 KB gzipped for a 3-player game against about 40 KB) and remove the need to apply events.

**Useful views for comparing agents:** a turn list with each player's action (`action` events); a per-seat panel showing the agent type and motivation weight from the header; the chosen option against the agent's own ranking in `info`; round summaries from `round_end` (counts, difficulty, success, group score change); and the final table from `final_scoring`.

## 9. Keeping the viewer ready for live play

The simulator does not support interactive play yet, and this file format will not change for it: a finished game will still be saved exactly as described above. Two choices in the viewer keep the door open for humans playing live alongside the bots.

**Build the display around one step.** A step is: the board before the decision, who is deciding, the labelled options, the option chosen, and what happened next (the events). A replay shows all five. Live play is the same screen with no option chosen yet and the labels clickable; the events arrive after the click.

**Draw the board from a state-shaped object, and tolerate hidden cards.** In a live game each player would be sent their own view instead of a full snapshot. That view has the same shape as `state` in section 5, with what the player may not see blanked out:

| In a player's view | Value |
| --- | --- |
| `deck`, `tucked`, `bonus_deck`, `bonus_discard` | the right length, but every entry is `-1` |
| another player's `hand` and `bonus`, when hands are closed | the right length, every entry `-1` |
| `pending[2]` (the options), when it is another player's decision that lists their hidden cards | `null` |
| `rng` | `0` |
| everything else (mats, food, tray, birdfeeder, discard pile, goals, scores) | as in a snapshot |

`set_aside` is visible too, except that with closed hands the bonus cards another player is choosing between are `-1`.

So a board renderer that draws card id `-1` as a face-down card, and copes with `pending` options being `null`, works for replays and for a live player's view alike. With open hands (the default) only the deck, tucked cards and bonus decks are hidden.

The events in section 4.6 are written for observers and can name cards a player should not see (a card drawn from the deck, for example). A live mode would need them filtered per player; that is work for the simulator, not the viewer.
