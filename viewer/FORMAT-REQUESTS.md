# Replay log format: requests from the viewer

For whoever works on the simulator (`wingsim/`). The viewer treats `docs/replay-log-format.md` (version 2) as the contract and was built from it without changing anything under `wingsim/`. This file lists the places where the log does not say enough for a viewer, or says it only if you read the engine source. Nothing here has been worked around by teaching the viewer game rules; where the viewer copes, the note says how, so you can tell what gets better when a request is done.

How these were found: `viewer/app/viewer/replay/reduce.js` applies events to a state exactly as sections 4.6 and 8 describe, and `viewer/tests/reduce.test.mjs` checks that every snapshot can be rebuilt from the one before it plus the events between. That check passes on the three sample games and on 320 generated games (2 to 5 players, both conditions), apart from the gaps R1 and R2 below. To run it on your own logs:

```
cd viewer && WINGSIM_LOGS=../logs npm test
```

Sequence numbers below refer to `docs/samples/coop-3p-greedy-every-decision.jsonl.gz` unless another file is named.

## Status (13 October 2026)

All of these are done on the simulator side, in the same version 2 format (fields and events were only added, apart from `card_tucked` gaining the source `"look"`). The format document marks each addition *(added)*, and its section 8 now lists what every event changes. `wingsim/tests/reduce_log.py` rebuilds every snapshot from the events on hundreds of games, reshuffles and the Oystercatcher draft included, and this viewer's `npm test` passes on the same kind of logs with the known-gap exemptions switched off for new logs.

The viewer's reducer and table handle the new events and still read older logs (told apart by whether snapshots have `state.set_aside`). Older logs can be rewritten in the new form with `.venv/bin/python -m wingsim.engine.log relog <old> <new>`. Not yet used by the viewer: N1 (`goal_counts`), N2 (`scores`), N3 (`scientific`).

| # | Done as |
| --- | --- |
| R1 | `bonus_drawn` event; `bonus_kept.discarded` (setup too) |
| R2 | `card_set_aside` event; `draw_card` and the tray rule documented |
| R3 | `state.set_aside` `{birds, bonus}`, also in a player's view |
| R4 | `card_tucked` source `"look"`; `card_discarded` why `"predator_miss"`; documented |
| R5 | `turn_end` event, plus a new `tray_cleared` event at round end; the order of end-of-turn and end-of-round events documented |
| R6 | `deck_reshuffled.deck` (new order); `bonus_reshuffled` event. A tray refill or bonus draw that runs into a reshuffle is now reported in two parts so the events apply in order |
| N1, N2 | snapshot fields `goal_counts` and `scores` |
| N3 | `scientific` in the card reference |
| N4 | documented |
| N5 | `card_tucked.card` always present |
| N6 | `vp_text` corrected to `7+ birds` |
| Corrections | all three made in the document |

## Table talk and the harness (17 October 2026)

Built from section 6 on `llm-glm-pair-talk` (talk only) and a game played against a local stand-in model with talk, coach and digest on (no real coach log yet). Nothing is missing; two things the viewer relies on that the document could say:

| # | Request | Kind | Viewer today |
| --- | --- | --- | --- |
| T1 | When a coach "flags" a problem | documentation, or a field | counts notes as flagged unless they start "No problems", the wording `wingsim/prompts/coach.md` asks for. A `flagged` boolean on the coach call would make it exact |
| T2 | What a digest read | documentation | rebuilds it from the `said` of other seats since this seat's previous digest. Worth one sentence in section 6 confirming that is exactly the set the digest saw (or log it, e.g. `aux[].read` as decision indexes) |

## Language-model data (14 October 2026)

Found while building the model panel (`app/viewer/llm.js`, `ui/model.js`) on the three games in `llm-prompts-moe-brief` (`default`, `plan`, `plan_after`, seed 101, 2 players). Sequence numbers refer to those files.

| # | Request | Kind | Viewer today |
| --- | --- | --- | --- |
| L1 | `parse_plan` / `strip_reply` match `plan:` anywhere, in any case | agent bug | shows the replies and the logged plans as they are |
| L2 | `usage` covers only the last call | missing field | "cut off" can only be judged for the last reply |
| L3 | The token limit of each call is not logged | missing field | judges against `max_tokens` (+600 at action decisions in plan games) |
| L4 | Plan fields and where `plan_updated` comes from | documentation | follows `PLAN_FORM` in `llm.py` |

**Status (simulator side, 14 October 2026):**

| # | Done |
| --- | --- |
| L1 | Fixed: a block starts only at a line beginning `PLAN:` (capitals; `**PLAN:**` allowed), the *last* block is the plan, and the answer is read outside blocks. Logs written before this fix keep the old behaviour: `llm-prompts-moe-brief` and `llm-prompts-moe/default` seed 101. |
| L2 | `info.usage_all`, one entry per reply; `usage` stays as the last call's |
| L3 | `info.limits`, the token limit of each call |
| L4 | Section 6 of the format document now says all of this |

Games in `llm-prompts-moe` started after this change carry `usage_all` and `limits`; older games don't, so keep the fallback.

**L1. A reply that mentions "plan:" in its reasoning loses its answer and can corrupt the plan.** `wingsim/agents/llm.py` finds the plan block with `re.search(r"PLAN:\s*(.*?)\s*(END PLAN|$)", reply, re.S | re.IGNORECASE)` (in `parse_plan`) and removes it the same way (in `strip_reply`). The models often quote their plan in the reasoning, e.g. `Let's consider the "Need next" in my plan: "…"`. Then:

- `strip_reply` cuts from that phrase to the final `END PLAN`, taking the `ANSWER:` line with it, so a reply with a valid answer is read as having none and the model is asked again. In these three games that happened at `plan` seq 43 and 62 and `plan_after` seq 93, 96, 135 and 143: each first reply has a valid `ANSWER:` and a retry follows. (The same match, e.g. `So, Plan:` or `my plan:`, also appears in `default` 33 and `plan_after` 37, 112 and 124, where the first reply had no answer anyway.)
- `parse_plan` returns the text after the first match. At `plan` seq 43 `plan_updated` is a run of reasoning that starts `"Invertebrate/Seed food to play…` and has none of the five fields, and from seq 43 that text is the plan shown in the next prompts (`info.plan`) until the model writes another.

Suggested fix: match the block only at the start of a line and in capitals (`^PLAN:` with `re.M`, no `IGNORECASE`), take the *last* such block, and look for the answer outside it. The viewer splits replies that way for display.

**L2. `usage` is for the last call only.** When there are two replies, `usage.completion_tokens` is the retry's count (e.g. `plan` seq 2: a long first reply with no answer, then `ANSWER: 1`, and `completion_tokens: 6`). The first reply, which is the one usually cut off, has no count, so "cut off" is flagged on only one decision per game. Suggested: `usage` as a list parallel to `replies` (or a `usage_all` list beside the current field, so older readers keep working). The format document should also say which call `usage` describes.

**L3. The token limit of each call.** The first call's limit is `max_tokens`, or `max_tokens + 600` at action decisions of plan seats (`plan_max_tokens`), and a reasoning seat's "finish now" retry gets `RETRY_LIMIT` = 300. None of these are in the log except `max_tokens`, so a viewer has to know the agent's code to judge a cut-off retry. Since `finish_reason` is `"stop"` even for cut-off replies on this server, logging the limit (say `limits`, parallel to `replies`) would make "cut off" a simple comparison.

**L4. Documentation.** Section 6 could say: the plan has five lines (`Engine:`, `Bonus target:`, `Round goal:`, `Need next:`, `Pivot if:`); it is only written at `kind == "action"` decisions; `plan_updated` is taken from the first reply's plan block, or the retry's if the first has none; `chosen` is the random option's number when `fallback` is `"random"`.

**L5. Documentation: the keep-birds prompt (16 October 2026).** With `compact` on, a `setup_keep_birds` prompt lists the 5 dealt birds numbered 1-5 and the model answers with bird numbers (`ANSWER: 4, 5`); without it, the prompt lists all 32 options and the model answers with one option number. The viewer now shows this decision as the 5 birds with the kept ones ticked, numbered only for `compact` seats, so its answer lines up. Section 6 could say what `compact` changes here, and section 4.5 that the birds are numbered in hand order, which is also the order of the option keeping all 5 (true in all 85 keep-birds decisions in the logs tested; the viewer relies on it).

The original requests follow, unchanged.

## Summary

| # | Request | Kind | Viewer today |
| --- | --- | --- | --- |
| R1 | Events for bonus cards drawn and discarded by a power | missing events | cards appear with no movement; pile heights lag in per-turn logs |
| R2 | Events for cards taken into the American Oystercatcher draft | missing events | nothing moves until `cards_revealed` |
| R3 | A state field for cards set aside for a pending choice | missing state | read from the pending decision's options instead |
| R4 | Say what a predator "look" does to the deck and discard pile | undocumented | infers it from the event order |
| R5 | A `turn_end` event, or say that `tray_refill` ends the turn | undocumented | treats `tray_refill` during a round as the end of the turn |
| R6 | Shuffles: meaning of `deck_reshuffled.cards`; an event for the bonus deck | undocumented / missing event | deck order unknown after a reshuffle; bonus reshuffle inferred |
| N1 | Live goal counts in each snapshot | nice to have | goal board shows counts only at round end |
| N2 | Bonus-card points in each snapshot | nice to have | running scores leave bonus cards out until the end |
| N3 to N6 | Small additions and one data typo | nice to have | see below |

"Version 3" is not needed for any of this if events and fields are only added; the viewer ignores events and fields it does not know (it lists unknown event names in its Game tab).

## Requests

### R1. Bonus cards drawn by a power have no events

When a power says "draw 2 bonus cards and keep 1", the two cards leave `bonus_deck` as soon as the power is used, and the one not kept goes to `bonus_discard` when the choice is made. Neither movement is an event.

Evidence: decision 44 (`activate_power`, bird 65) causes one event, `power`. Between the snapshots before 44 and before 45, `bonus_deck` goes from 20 cards (ending `…, 1022, 1006, 1028`) to 18. Decision 45 (`keep_bonus`) causes `bonus_kept` with `bonus: 1028`; 1006 turns up in `bonus_discard` with no event naming it.

Asked for:

- `bonus_drawn`: `p`, `bird` (the bird whose power drew them), `cards` (the ids, in the order they came off the deck), emitted with the `power` event.
- The discard: either a field on `bonus_kept` (`discarded: [ids]`) or a `bonus_discarded` event. The same field would also cover setup, where the bonus card not kept goes to `bonus_discard`.

Viewer today: shows the two cards held up in the middle from the options of the pending `keep_bonus` decision, with no flight from the bonus deck. With per-turn snapshots the bonus deck's height is wrong from the power until the card is kept.

### R2. Cards taken for the American Oystercatcher draft have no events

The owner takes one card per player plus one, each by a `draw_card` decision. Those decisions cause no event: the card leaves the tray or the deck and is in no state list. Only after the last one does `cards_revealed` name them all. When one source is left the last card is taken with no decision at all (one legal option).

Evidence (no sample game has this bird; from a generated game: baseline, 3 players, seed 11, tuned greedy bots at w = 0.5): decisions 188, 189 and 190 are `draw_card` with choices `["tray", 63]`, `["tray", 22]`, `["tray", 70]`. 188 and 189 have no events. The tray goes `[63, 22, 70]`, `[22, 70]`, `[70]`, `[]` in the snapshots. 190 causes `cards_revealed` with `birds: [63, 22, 70, 189]`, where 189 came off the deck with no decision. Then `draft_pick` decisions give `cards_drawn` with `source: "draft"`.

This also contradicts two lines of the format document: section 4.5 describes `draw_card` as "drawing a bird card", and section 8 says a `cards_drawn` event is what removes a card from the tray.

Asked for: one event per card as it is taken, for example `card_set_aside` with `p`, `source` (`"tray"` or `"deck"`) and `bird`. A sentence in section 4.6 saying the tray is not refilled until the end of the turn would help too.

Viewer today: the tray and deck do not change on screen during those decisions. At `cards_revealed` the cards jump to a row in the middle; the reducer removes each from the tray if it is still there, otherwise from the deck. With per-turn snapshots the tray is stale for the two or three positions in between.

### R3. Cards set aside for a pending choice are not in the state

While a `keep_bonus` or `draft_pick` decision is pending, the cards on offer are in no field of `state` (they sit in `stack`, which viewers are told to ignore). A board drawn only from a state-shaped object, which is what section 9 recommends for live play, cannot show them.

Evidence: snapshot before decision 45: 1006 and 1028 are in neither `bonus_deck`, `bonus_discard` nor any player's `bonus`.

Asked for: a state field such as `set_aside: {"birds": [...], "bonus": [...]}` (empty lists most of the time), and the same field in a live player's view.

Viewer today: takes the cards from the options of the decision line (`["bonus", id]`, `["card", bird]`). That works for replays because the options are documented; it would not work in a live view where `pending[2]` can be `null`.

### R4. What a predator "look" does

Section 4.6 says `predator` with `kind: "look"` has `card`, "the deck card looked at". Not said:

- The card has left the deck at that point.
- On a hit, a `card_tucked` event for the same card follows (`source: "deck"`, with `card`). Applying both events as section 8 describes takes two cards off the deck.
- On a miss, the card goes to the discard pile and no event says so.

Evidence: decision 221: `predator` (`kind: "look"`, `card: 16`, `success: true`) then `card_tucked` (`card: 16`, `source: "deck"`); the deck is one card shorter afterwards, not two.

Asked for: say this in sections 4.6 and 8. Cleaner still: give the following `card_tucked` a distinct `source` (for example `"look"`), and emit `card_discarded` with `why: "predator_miss"` on a miss.

Viewer today: remembers the card a predator has just looked at and does not draw again when the next `card_tucked` names the same card; on a miss it moves the card to the discard pile.

### R5. The end of a turn

Three state fields change when a turn ends and the document does not say when: `actions_left[p]` goes down by one, `turn` moves to the next seat and `turn_no` goes up by one. All three happen with the end-of-turn `tray_refill` (which is emitted every turn, changed or not), not with `action` or the next `turn_start`.

The round boundary has more of the same:

- `round_start` sets `actions_left` to 8, 7, 6 or 5 for everyone and `turn` to `first`.
- `round_end` moves `first` one seat on and adds one to `round`, including after round 4.
- Between `round_end` and the second `tray_refill`, the old tray goes to the discard pile.

Asked for: a `turn_end` event with `p`, or one paragraph in section 8 with the above.

Viewer today: treats a `tray_refill` that arrives while a round is in progress as the end of the turn. It works on every log tested but it is a reading of the engine, not of the document.

### R6. Shuffles

- `deck_reshuffled` has a `cards` field with no description. It is a count. The new order is not given, so after a reshuffle a viewer of a per-turn log knows which cards are in the deck but not their order (it only matters for showing the top card, which is face down anyway). Asked for: describe the field; optionally add the new order as `deck`, since the log is for observers.
- The bonus deck is reshuffled from `bonus_discard` when it runs out, with no event. Evidence: generated game `fuzz/coop/33-5p`, decision 600: `bonus_discard` goes from 13 cards to none on a `power` event alone. Asked for: `bonus_reshuffled` with `cards` (count).

Viewer today: keeps the reshuffled deck as "these cards, order unknown" and finds each card when it is drawn. Infers a bonus reshuffle when a card offered by a power can only have come from the discard pile.

## Nice to have

### N1. Live goal counts

Add each player's current count for the round's goal to every snapshot, for example `goal_counts: [2, 0, 1]`. The language-model prompt already carries it ("counts so far [0, 0]"). The goal board could then show each player's cube moving along the squares during the round, against the difficulty marker, which is the heart of the co-op rule. The viewer does not compute this itself: the card reference gives `kind` and `param`, but counting them is rules (star nests, egg sets) and belongs in the engine.

Viewer today: cubes go on the squares at `round_end`, from `counts`.

### N2. Bonus-card points during the game

Section 5.3 says bonus points "are easiest to show only at the end". A `bonus_points` number per player in each snapshot (or a whole `scores` object in the shape of section 5.3) would let the running scores match the final table at every step.

Viewer today: running scores are birds + eggs + cached + tucked + goal points, and jump when the game ends.

### N3. Scientific names

The card art has a footer for the scientific name. `scientific` in `cards.birds` would fill it.

### N4. Pile order

Say that the last element of `discard` and `bonus_discard` is the top of the pile (most recently discarded). The viewer assumes so in order to show the top card face up.

### N5. Identity of cards tucked from the deck

`card_tucked` with `source: "deck"` has no `card` unless a predator looked at it. The log is unredacted elsewhere (`state.tucked` has the ids), so `card` could always be present. The viewer would then show which card went under.

### N6. A typo in the card data

Bonus card 1001 (Backyard Birder): `vp_text` is `"5 to 6 birds: 3[point]; 6+ birds: 6[point]"` but `tiers` is `[[5, 3], [7, 6]]`. The second tier should read `7+ birds`. The viewer prints `vp_text` on the card.

## Small corrections to the document

- Section 5.1 says `variant` holds `{"coop.d": null}` before the difficulty is first set. During setup it is `{}`; the key appears (as `null`) at the first `round_start`.
- Section 5.1 lists the phases `pre_round` and `round_end`; no snapshot in any log tested has them (they do not last until a decision). Worth saying, so nobody builds a view for them.
- Section 4.6, `bird_moved`: the bird that moves is always the rightmost in its row and goes to the right-hand end of the new row. Stated, it would save a viewer from handling a gap in the middle of a row.
