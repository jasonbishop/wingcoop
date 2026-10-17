# Wingspan co-op replay viewer

Plays back games logged by the simulator in `../wingsim` on a 3D table: every player's mat around a round table, the shared pieces on a turntable in the middle, and a panel showing each decision, the options, what was chosen and why.

It reads the log format described in `../docs/replay-log-format.md` (version 2) and nothing else from the simulator: no engine code runs here. Places where that format falls short for a viewer are written up in `FORMAT-REQUESTS.md`.

Built on the birdtable components (Three.js and cannon-es), textured from the concept art in `art/source/`.

```bash
npm install
npm run dev        # http://<this machine>:5273/  (listens on all interfaces)
npm test           # log reader, event reducer and model-panel helpers, checked against the sample games
```

## Opening a game

- **From the list.** With `npm run dev` the opening screen lists every log under `../logs/` and `../docs/samples/`. Add other folders with `WINGSIM_LOGS=/some/dir:/another npm run dev`.
- **Drop a file** anywhere on the page: an exported `.json`, or a native `.jsonl.gz` / `.jsonl` (native logs need the dev server, which supplies the card reference from `../wingsim/data/cards.json`).
- **By address:** `/?log=docs/samples/coop-3p-greedy-every-decision.jsonl.gz&at=120` opens that log at position 120. The address bar follows you as you move, so a reload or a shared link comes back to the same spot. `&quality=low` halves shadow and card texture sizes.

Logs with a snapshot before every decision (`logging: {snapshots: decision}` in the experiment file) are shown exactly. Logs with per-turn snapshots work too: positions inside a turn are worked out from the events and marked "Board derived from events".

## What is on the screen

**The table.** Seats are clockwise in seat order. Each has the mat (the art has 7 columns; the game uses the first 5), food tokens, cubes for the turns left this round, a name plate, bonus cards and the hand. The middle is a lazy susan with the goal board, birdfeeder, deck, bird tray, discard pile and bonus deck; it turns to face whichever seat you are watching, so those always read the right way up.

**The goal board.** After a round is scored each player's cube sits on the square for their count, 0 to 5 from the left. With co-op goals a ring sits on the medallion for the difficulty: gold while the round is being played, green if every player reached it, red if not. The current round's goal tile is raised.

**Step tab.** One decision: who is deciding and with which agent, the options (the chosen one marked, with the agent's own value for the options it ranked), a language model's reply and the prompt it saw, and the events the choice caused. During playback the events light up as they happen on the table.

The starting-birds decision is shown as the 5 dealt birds with the kept ones ticked, instead of its 32 combinations (still one click away). For a language model the list matches its prompt: numbered 1-5 for a `compact` seat, which answers with bird numbers; otherwise the combination it picked is shown with its option number.

**Turns tab.** Every turn with its action; click to jump. **Game tab.** Settings, seats, round-goal results, final scores.

**Model tab** (games with a language-model seat). Follows the replay cursor: it shows the model decision at the cursor, or the latest one before it.
- Each reply split into its parts: hidden thinking (collapsed, from `info.thinking` or a `<think>…</think>` pair; a lone `<think>` is a server quirk and only the tag is dropped), the reasoning, the `ANSWER:` line, and in plan games the plan block. With two replies the second is marked *retry* and the first *not accepted*.
- **Random move** in a red box when `fallback` is `"random"`: the option played was not the model's choice.
- **Cut off** when `usage.completion_tokens` is within a few tokens of `max_tokens` (plus 600 at action decisions in plan games). The usage belongs to the last reply only, so a cut-off first reply can't be flagged yet (`FORMAT-REQUESTS.md`, L2).
- **Plan** (plan seats): the plan shown against the plan written back, line by line, with word-level highlights; and above the search, a timeline with a lane per plan line and a mark wherever it changed. Click a mark to go there.
- **Search** across the reasoning and hidden thinking (not the plan blocks, which all say "Round goal:"), and **filters**: fallbacks, retries, cut off, plan changed. Matches are listed with an excerpt; ◀ ▶ step through them.
- **Transcript**: every decision in order on one page, with options, replies, choice and plan diff side by side, and other players' decisions as one line each. Same search and filters. `&transcript=1` in the address opens it.
- **Rules**: a drawer with the seat's system prompt (its rules summary), search words marked, to compare what the model was told with how it reasons.

Drag the panel's left edge to widen it (double-click to reset); the width is remembered in this browser.

**Controls.** Play / pause, one decision forward or back, previous / next turn or round, a scrubber, speed. `Space` plays, `←` `→` step, `Shift`+arrows jump by turn. "Watch" chooses whose seat the camera sits behind (it follows the turn by default); Seat / Mat / Middle / Table are camera distances. Drag to orbit, scroll to zoom. Click a card to read it, a score chip or name plate to sit at that seat.

## Layout

```
index.html                 the viewer page
app/viewer/
  main.js                  opens a log, builds the table, wires the controls
  replay/log.js            log -> positions (board before a decision, the decision, its events)
  replay/reduce.js         applies events to a state (for per-turn logs and for mid-step states)
  replay/load.js           files, the dev server's log list
  data.js                  log conventions and card reference -> what components draw
  describe.js              sentences for events and decisions
  llm.js                   language-model decisions: reply parts, plans, word diffs, flags, search
  player.js                ReplayPlayer: step, scrub, autoplay, camera following
  scene/GameTable.js       the whole table: setState(state), animate(event), reconcile(state)
  scene/layout.js          where seats, shared pieces and cameras go
  ui/                      top bar, tabs, transport, inspector, opening screen, styles;
                           ui/model.js: the Model tab, transcript and rules drawer
  birdArt.js               finds bird illustrations by id or name
app/feeder.html, feeder/   the birdfeeder on its own (physics tuning)
components/                table pieces: no game rules, no HTML (see below)
server/api.js              dev-server routes: /api/runs, /api/log, /api/cards (read-only)
art/                       concept sheets, manifest.json, extract.py, find_boxes.py
tests/                     node tests for the log reader, reducer and language-model helpers
tools/                     headless screenshots and whole-game playthrough checks
FORMAT-REQUESTS.md         what the simulator's log should add or document
```

## How playback works

`buildReplay()` turns a log into **positions**. Position *i* is the state before decision *i + 1*, the decision line, and the events that choice caused; the last position is the final state. That is the "one step" of section 9 of the format document, so a live game could feed the same screen with the choice not yet made.

Moving around uses two paths, the same split the components have:

| | Used for | How |
| --- | --- | --- |
| Instant | scrubbing, jumping, stepping back | `game.setState(position.state, { decision })`: every component is set from the state; only what differs is rebuilt |
| Animated | Play and Step | for each event: `await game.animate(event, stateBefore)`, apply the event to a copy of the state, `game.reconcile(state)`; then `setState()` of the next position |

`reconcile()` after every event means an animation never has to be exactly right for the table to be right; `tools/playthrough.mjs` reports every event where it had to correct something. A card id of `-1` is drawn face down everywhere, as section 9 asks.

Stopping mid-step (scrubbing while it plays, or pressing Step again to skip) flushes the running animations until the chain of awaits has unwound, so every wait inside an animation must be a tween, a feeder roll or a camera move, never a bare `setTimeout`.

## Components

Each lives in `components/<name>/src` with an `index.js` of public exports and its generated art in `components/<name>/assets`. A component has an `object3d` and, if animated, `update(dt)`. Units are card-sized: a bird card is 1.5 × 2.17, the mat 18 × 10, the goal board 12 × 4.9. The table top is y = 0.

Every action has two forms: an animated method returning a promise, and `setState(data)` / `getState()` for the instant form.

### Tabletop (`components/tabletop`)
- `new Tabletop({ container, size, shape: 'rect' | 'round', shadows, shadowMapSize, views })`; `table.add(component, { position, rotationY, scale, parent })`
- `table.setView(nameOrView, { animate, duration, orbit })` returns a promise; `orbit: true` swings round the table's centre instead of cutting across it. `table.finishCamera()`, `table.cameraSpeed`
- `table.addEventListener('pick', e => e.detail)`: clicking anything whose `userData.pick` is set
- `LazySusan({ radius })`: put things on `susan.top`, `await susan.turnTo(angle)`
- `Plaque({ width, height })`: a name plate, `plaque.setText({ title, subtitle, color, highlight })`
- `tweens` (`to`, `wait`, `finishAll`, `speed`), `fly`, `worldPoint`, `loadTexture`, `loadImage`, `assetsReady()`

### PlayerMat (`components/player-mat`)
Habitats `'wetland' | 'forest' | 'grassland'`, slots `0..6` left to right.
- `playBird(habitat, i, birdCardOrBirdData)`, `removeBird(habitat, i)`
- `layEggs(habitat, i, count, kind | kinds[])`, `removeEggs(habitat, i, count)`
- `cacheFood(habitat, i, food, { fromSupply })`, `tuck(habitat, i, count, { from: [cards] })`
- `addFood(food, { from })`, `spendFood(food, { to })`; `mat.supply` is the group of food piles (move it where you like)
- `setState(state)` rebuilds only the slots and piles that differ; `getState()`

```js
{ wetland: [{ bird, eggs: ['blue', 'cream'], cached: ['fish'], tucked: 2 }, null, …],
  forest: […], grassland: […], supply: { fish: 2, seed: 1 } }
```

### GoalBoard (`components/goal-board`)
- `setGoal(round, key | { key, label, tint, image })`: without an image the tile is drawn from the label (symbols allowed: `'[egg] in bowl nests'`)
- `placeCube(round, { square: 0..5 } | { medallion: 1..5 }, color, { from })`, `removeCubes(filter)`
- `setMarker(round, medallion | null, { color })`: a ring round a medallion, one per round
- `setActiveRound(round | null)`: raises that round's tile
- `setState({ goals, cubes, markers, active })`, `getState()`

The board only knows positions; what squares and medallions mean is the app's call (`GameTable._boardState`).

### Cards (`components/cards`)
- `BirdCard(bird, { faceUp })`, `BonusCard(bonus, { faceUp })`: `setData`, `flip()`, `moveTo(parent, position, { faceUp })`. Faces are drawn at runtime and shared: cards with the same `id` use one texture. `setCardDetail(scale)` sets texture size.
- `CardDeck({ count, kind: 'bird' | 'bonus' })`: `count`, `await deck.draw(data, parent, position)`, `deck.lift(data)` (take the top card, move it yourself)
- `CardPile({ kind })`: a face-up pile; `setState({ count, top })`, `await pile.add(card)`
- `CardRow({ slots })`: `place(i, card)`, `take(i)`, `slotPosition(i)`
- `CardFan({ maxWidth, faceUp })`: a hand that overlaps when full; `add(key, card)`, `take(key)`, `setState(keys, create)`
- `TuckTab(count)`
- Bird data (`Bird` typedef in `cardFace.js`): `{ id, name, points, habitats, food, foodOr, nest, eggLimit, wingspan, power, powerColor, tags, image }`. `food` entries may be `'wild'`. Power text may contain symbols in brackets (`[fish]`, `[egg]`, `[card]`), drawn by `symbols.js`.
- Bonus data: `{ id, name, condition, points }`

### Pieces (`components/pieces`)
- `createFoodToken(food)`, `createEgg(kind)`, `createCube(color)`, `createMarker(color)`, `createFirstPlayerToken()`
- `FOODS`, `EGG_KINDS`, `PLAYER_COLORS`, `FOOD_ICONS`, `EGG_ICONS`

### BirdFeeder (`components/birdfeeder`)
See `components/birdfeeder/README.md`. Rigged rolls (`roll({ faces, random })`), `setDice`, `take`, `skip`, `dieWorldPosition`.

## Art

All component images are generated from the sheets in `art/source/` by `art/manifest.json`; don't edit them by hand.

```bash
uv venv .venv && uv pip install --python .venv/bin/python pillow numpy scipy
.venv/bin/python art/tools/find_boxes.py art/source/NEW.jpg --annotate   # list element boxes
# add entries to art/manifest.json -> outputs
.venv/bin/python art/tools/extract.py --preview                          # regenerate, write a contact sheet
```

**Bird illustrations.** Only two exist (song sparrow, osprey). Any image in `components/cards/assets/birds/` named after a bird's id (`136.jpg`) or its name (`great-horned-owl.jpg`) is used on that bird's card; the rest show a silhouette. Parchment backgrounds are fine: the art is multiplied onto the card.

**Text is never taken from the art**; names, numbers and rules text are drawn at runtime.

## Checking changes without a desktop browser

`tools/shot.mjs` takes screenshots and `tools/playthrough.mjs` runs whole games through the animation code, both in headless Chromium. The header of each file has the container command (`mcr.microsoft.com/playwright`). WebGL runs in software there, so allow a few seconds a frame.

## Not here yet

- Live goal counts during a round, and bonus points in the running scores. The log now has both (each snapshot's `goal_counts` and `scores`, `FORMAT-REQUESTS.md` N1 and N2); the goal board and score panel don't use them yet.
- Scientific names on the card footer: now in the card reference as `scientific` (N3), not yet drawn.
- Dice a predator rolls outside the feeder are reported in the panel and a banner, not rolled on the table.
- Live play. The screen is built for it (one step; a state-shaped board; face-down `-1` cards) but options are not clickable and there is nothing to connect to.
- Painted wooden bird meeples for the first-player marker and the action cubes (the way it's played at our table); `createFirstPlayerToken()` and `createCube()` in `components/pieces` are where they'd go.
- A static build (`npm run build`) opens exported `.json` files by drag and drop only; the run list and native logs need the dev server.

Three.js 0.160 and cannon-es 0.20. Browser needs WebGL. Card text belongs to Stonemaier Games and the card data comes from wingsearch (GPL-3.0); keep logs and builds that include it private.
