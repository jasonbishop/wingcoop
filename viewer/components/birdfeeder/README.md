# BirdFeeder

A 3D birdhouse dice tower for a Wingspan-style game: five food dice drop in through the lifted roof, tumble down three hidden baffles, and roll out into the tray. Built with Three.js and cannon-es, textured entirely from the Gemini concept art in `assets/source/`.

It is made for a **game replay UI**: rolls can be rigged to land on recorded faces, skipped, sped up, made repeatable with a seed, and the tray can be set to any state instantly for scrubbing.

```
src/
  BirdFeeder.js   the component (geometry, physics, playback, picking)
  faces.js        the six die faces and their food(s)
  textures.js     URLs of all images (bundler-friendly)
  random.js       seededRandom() for repeatable tumbles
  index.js        public exports
assets/           generated textures (from art/ at the repo root; don't hand-edit)
```

On the shared table it runs in embedded mode; see the root README and `app/table/table.js`.

## Quick start

`app/feeder.html` (run `npm run dev` at the repo root, then open `/app/feeder.html`) shows it on its own.

```js
import { BirdFeeder } from '../components/birdfeeder/src/index.js';

const feeder = new BirdFeeder({ container: document.getElementById('feeder') });
await feeder.ready;               // textures loaded
const dice = await feeder.roll(); // [{ index: 0, face: 'fish', taken: false }, …]
```

The container just needs a size; the canvas fills it and follows resizes. Its background shows through (the canvas is transparent), so style the container for the table colour.

## Two modes

**Standalone** (`container`): the feeder creates its own renderer, camera, orbit controls, lights, shadow-catching ground and render loop.

**Embedded** (`scene`): you already have a Three.js scene, e.g. a whole 3D table. The feeder adds a Group and you drive it:

```js
const feeder = new BirdFeeder({ scene, camera, domElement: renderer.domElement });
feeder.object3d.position.set(10, 0, -4);   // place it on your table
feeder.object3d.scale.setScalar(0.5);

function loop(dt) {
  feeder.update(dt);              // seconds
  renderer.render(scene, camera);
}
```

Embedded mode adds no lights; enable `renderer.shadowMap` yourself if you want shadows. `camera` and `domElement` are only needed for clicking dice.

## API

| Call | What it does |
| --- | --- |
| `new BirdFeeder(options)` | See options below. |
| `feeder.ready` | Promise, resolves when textures have loaded. |
| `feeder.roll()` | Drop `diceCount` (default 5) random dice. Resolves with the dice once settled. |
| `feeder.roll(['fish','seed'])` | **Rigged**: drop 2 dice that land showing exactly these faces, in this order. |
| `feeder.roll({ faces, count, speed, random })` | Full form. `speed` 2 = twice as fast. `random` is a `() => [0,1)` function; pass `seededRandom(n)` for a repeatable tumble. |
| `feeder.skip()` | Jump the current roll to its settled end. Resolves its promise. |
| `feeder.rolling` | `true` while a roll is playing. |
| `feeder.setDice(['fish','rodent'])` | Put dice straight into the tray showing these faces, no animation. `[]` empties it. Use for scrubbing. |
| `feeder.take(index)` | Lift a die out of the tray. Returns its face, or `null`. |
| `feeder.dieWorldPosition(index)` | World position of a die: the start point for a food token flying to a player. |
| `feeder.clear()` | Remove all dice. |
| `feeder.getDice()` | `[{ index, face, taken }]` for the current dice. |
| `feeder.setXray(bool)` / `feeder.xray` | Hide the right wall to show the baffles and falling dice. |
| `feeder.resetCamera()` | Standalone: back to the default view. |
| `feeder.update(dt)` | Embedded: advance animations. |
| `feeder.object3d` | The THREE.Group containing everything. |
| `feeder.renderer`, `.scene`, `.camera`, `.controls` | Standalone-mode internals, if you need them. |
| `feeder.dispose()` | Free GPU resources, stop the loop, remove listeners. |

**Options**: `container` or `scene` (one is required) · `camera`, `domElement` (embedded picking) · `diceCount` = 5 · `clickToTake` = true · `speed` = 1 · `shadows` = true · `controls` = true · `textures` = `{ key: url }` overrides (keys in `src/textures.js`).

**Events** (`feeder.addEventListener(type, e => e.detail)`):

| Event | `detail` |
| --- | --- |
| `rollstart` | `{ count, rigged }` |
| `settled` | `{ dice }` (same as `getDice()`) |
| `pick` | `{ index, face }`: a resting die was clicked |
| `take` | `{ index, face }`: a die was taken (by click or `take()`) |

## Faces

Keys used everywhere (`src/faces.js`):

| Key | Label | Foods |
| --- | --- | --- |
| `invertebrate` | Invertebrate | invertebrate |
| `seed` | Seed | seed |
| `fish` | Fish | fish |
| `fruit` | Fruit | fruit |
| `rodent` | Rodent | rodent |
| `invertebrate_seed` | Invertebrate or seed | invertebrate, seed |

`TOKEN_ICONS[food]` gives a round transparent PNG of each food for 2D UI (tallies, logs).

## Using it in a replay

A replay log already says what was rolled. Feed that in and the animation is generated to match:

```js
// turn record: { seed: 1234, faces: ['fish','seed','seed','rodent','fruit'] }
await feeder.roll({ faces: turn.faces, random: seededRandom(turn.seed) });
```

- **Playing forward**: `roll({ faces, random })` per roll event, `take(i)` per food-gain event. Map a taken face to a die with `getDice().find(d => !d.taken && d.face === face)`.
- **Scrubbing / jumping to a turn**: `setDice(facesInTrayAtThatPoint)`. Never replay every roll to get there.
- **Fast-forward**: `roll({ faces, speed: 4 })`, or `roll(faces)` then `skip()`.
- **Same tumble on every viewing**: give each roll a stable seed (e.g. the turn number). Seeded rolls are identical within the same browser; across different browsers or devices the tumble may differ slightly, but the final faces are always the ones you asked for.
- Turn off `clickToTake` in a replay viewer so clicks don't change the record.

### How rigging works

`roll()` runs the whole physics simulation up front (~20 ms; up to ~250 ms on a rare roll that needs nudging), records every frame, and then plays the recording back. Before playback starts it looks at which side of each die ended up on top and **rearranges that die's face images** so the requested food is on that side. Each die still has all six faces exactly once, and nothing changes while it moves, so the result is indistinguishable from a fair roll.

## Art

The textures in `assets/` are generated from the concept sheets by the repo-wide pipeline (`art/manifest.json`, `art/tools/extract.py`); see the root README. To swap art without regenerating (e.g. a seasonal skin), pass `textures: { front: url, … }` to the constructor.

**Notes on the current art**
- The texture sheet drew the front as a short rectangle and the sides as peaked; the model uses peaked front/back ends (like the concept drawing), so the front panel is extended downward and the sides are cropped below their slanted tops.
- The perch dowel is placed under the hole painted on `front.jpg` (`PERCH_Y` in `BirdFeeder.js`). If you replace that texture, move it.

## Tuning the physics

Constants at the top of `src/BirdFeeder.js`: `DIMENSIONS`, `RAMPS` (baffle positions), timeline values, and contact materials in `_buildPhysics()`. Two things were found by testing and are easy to break:

- Baffle **vertical clearances are about 3 units** so two stacked dice (2 units, up to ~2.8 tilted) can't wedge between baffles.
- Baffles are **frictionless**. cannon-es scales friction with contact-point count, so a die lying flat on a sloped box can lock in place even with low friction.

After changing either, run a few dozen rolls (`roll()` then `skip()` in a loop) and check every die ends in the tray.

