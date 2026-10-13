# Birdtable

3D tabletop components for a Wingspan-style **game replay viewer**, built with Three.js and cannon-es and textured entirely from the Gemini concept art in `art/source/`.

```bash
npm install
npm run dev            # opens app/index.html: the whole table + a scripted replay
                       # app/feeder.html: the birdfeeder on its own
```

## Layout

```
art/
  source/            the concept sheets (inputs)
  manifest.json      every generated image: sheet, pixel box, processing, output path
  tools/extract.py   regenerates all component art from the manifest
  tools/find_boxes.py  finds element boxes on a new sheet
components/
  tabletop/          shared scene: renderer, camera views, lights, table cloth, picking, tweens, asset loading
  birdfeeder/        dice tower + physics food dice (has its own README)
  player-mat/        habitat mat: bird cards, eggs, cached food, tucked cards, food supply
  goal-board/        round-end goal grid, goal tiles, player cubes
  cards/             bird card (face drawn at runtime), face-down deck, card row, tuck tab, sample birds
  pieces/            food tokens, eggs, player cubes
app/
  index.html, table/ the table demo: setup, snapshot/restore, replay steps (replay.js)
  feeder.html, feeder/ standalone feeder demo
```

Each component lives in `components/<name>/src` with an `index.js` of public exports, and its generated art in `components/<name>/assets`. Components import each other by relative path; there is no build step except for the demo pages.

## How the pieces fit

Every component has an `object3d` (add it to the scene) and, if animated, `update(dt)`. `Tabletop` does both for you:

```js
import { Tabletop } from './components/tabletop/src/index.js';
import { PlayerMat } from './components/player-mat/src/index.js';

const table = new Tabletop({ container: document.getElementById('table') });
const mat = table.add(new PlayerMat({ name: 'alice' }), { position: [0, 0, 5.4] });
```

Units are card-sized: a bird card is 1.5 × 2.17, the mat 18 × 10, the goal board 12 × 4.9, the feeder is scaled 0.55 on the table. The table top is y = 0; +z points toward the default camera.

Every game action has two forms:

| | Use for | Example |
| --- | --- | --- |
| **Animated** methods returning promises | playing a replay forward | `await mat.layEggs('forest', 0, 2, 'speckled')` |
| **`setState(data)`** (instant) + **`getState()`** | jumping / scrubbing to any point | `mat.setState(snapshot.mat)` |

`app/table/table.js` shows the full pattern: take a `snapshot()` (every component's `getState()`) before each step; going back is `restore(snapshot)`. Skipping animations is `tweens.finishAll()` + `feeder.skip()`; `tweens.speed = 4` fast-forwards everything.

Moving pieces between components (feeder → supply, deck → tray → mat, supply → card) uses `fly(object, toParent, localPosition, localQuaternion)` from `tabletop/src/tween.js`, which animates in world space and reparents at the end. Most methods accept a `from` world point to start the flight at, e.g. `mat.addFood('fish', { from: feeder.dieWorldPosition(i) })`.

## Component APIs

### Tabletop (`components/tabletop`)
- `new Tabletop({ container, views?, size?, shadows? })`; `table.add(component, { position, rotationY, scale })`
- `table.views.name = { position, target }`; `table.setView(name, { animate })`
- `table.addEventListener('pick', e => e.detail)`: clicking any object whose `userData.pick` is set. Cards on the mat report `{ type: 'slot', habitat, slot, bird }`, tray/deck cards `{ type: 'card', bird }`, goal tiles `{ type: 'goal', round, goal, label }`.
- `tweens` (`to`, `wait`, `finishAll`, `speed`), `fly`, `worldPoint`, `loadTexture`, `loadImage`, `assetsReady()`

### PlayerMat (`components/player-mat`)
Habitats `'wetland' | 'forest' | 'grassland'`, slots `0..6` left to right.
- `playBird(habitat, i, birdCardOrBirdData)`: an existing `BirdCard` flies in; bird data drops a new card in
- `layEggs(habitat, i, count, kind | kinds[])`, `removeEggs(habitat, i, count)`
- `cacheFood(habitat, i, food, { fromSupply })`, `tuck(habitat, i, count)` (cards peek out above with a count tab)
- `addFood(food, { from })`, `spendFood(food, { to })`: the food supply in front of the mat
- `setState(state)`, `getState()`, `firstEmpty(habitat)`, `slotPosition(habitat, i)`, `slotGroup(habitat, i)`

State shape:
```js
{ wetland: [{ bird, eggs: ['blue', 'cream'], cached: ['fish'], tucked: 2 }, null, …],
  forest: […], grassland: […], supply: { fish: 2, seed: 1 } }
```

### GoalBoard (`components/goal-board`)
- `setGoal(round, key)`: goal tile beside round 1–4; keys in `goals.js` (`wetland_total`, `cave_dwellers`)
- `placeCube(round, { square: 0..5 } | { medallion: 1..5 }, color, { from })`, `removeCubes(filter)`
- `setState({ goals: [k1, k2, k3, k4], cubes: [{ round, medallion | square, color }] })`, `getState()`

The board only knows positions; what squares vs medallions mean is your rules' call.

### Cards (`components/cards`)
- `new BirdCard(bird, { faceUp })`, `card.setBird(bird)`, `card.flip()`, `card.moveTo(parent, position, { faceUp })`
- `new CardDeck({ count })`, `deck.count`, `await deck.draw(bird, toParent, position)`
- `new CardRow({ slots: 3 })`, `row.place(i, card)`, `row.take(i)`, `row.slotPosition(i)`, `row.firstEmpty()`
- `new TuckTab(count)`, `tab.setCount(n)`
- Bird data (`Bird` typedef in `cardFace.js`): `{ name, scientific, points, habitats, food, foodOr, nest, eggLimit, wingspan, power, powerColor, image }`. The face is drawn onto the blank card art at runtime, so any bird works with real, readable text. `SAMPLE_BIRDS` has five examples.

### Pieces (`components/pieces`)
- `createFoodToken(food)`, `createEgg(kind)`, `createCube(color)` → meshes resting on y = 0
- `FOODS`, `EGG_KINDS` (`blue`, `speckled`, `cream`), `PLAYER_COLORS`
- `FOOD_ICONS`, `EGG_ICONS`: 2D images for HTML UI

### BirdFeeder (`components/birdfeeder`)
See `components/birdfeeder/README.md`. On the table it runs embedded: `new BirdFeeder({ scene, camera, domElement, clickToTake: false })`. Rigged rolls (`roll({ faces, random })`), `setDice`, `take`, `skip`, `dieWorldPosition`.

## Art pipeline

All component images are generated; don't edit them by hand.

```bash
pip install pillow numpy scipy
python3 art/tools/find_boxes.py art/source/NEW.jpg --annotate   # list element boxes (+ an annotated copy)
# add entries to art/manifest.json → outputs
python3 art/tools/extract.py --preview                          # regenerate everything, write a contact sheet
```

Ops available in `extract.py`: `upscale`, `extend_down`, `patch`, `circle_mask`, `outline_cutout` (cut out an object with a dark outline, e.g. eggs). Positions *inside* images (mat card slots, goal grid squares and medallions, card-face text regions) live in each component's `layout.js` / `cardFace.js REGIONS` as fractions of the image, so re-measure them if you replace that art.

Generated text in the concept art is unreliable (the sample cards are gibberish), so text is always rendered at runtime; the art supplies frames, textures and illustrations.

## What's not here yet
- Hands of cards, bonus cards, the round tracker, multiple players' mats (create more `PlayerMat`s and place them around the table).
- Only two bird illustrations (sparrow, osprey) and two goal tiles exist; crop more art via the manifest.
- Eggs on cards are capped visually at 6 per layer (extras stack a second layer).

Three.js 0.160 and cannon-es 0.20. Browser needs WebGL.
