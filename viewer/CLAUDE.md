# Notes for Claude Code

Replay viewer for the simulator's game logs: a 3D table (Three.js components) plus HTML panels. Read README.md first, then `../docs/replay-log-format.md`, then the file you're touching.

## Ground rules
- **The log format document is the contract.** Build from `../docs/replay-log-format.md`, not from the engine source, and never edit anything under `../wingsim` from here. If the log lacks something the viewer needs, or the document is silent on it, write it up in `FORMAT-REQUESTS.md` for the simulator side (reading the engine to pin down what actually happens is fine for that); don't work around it by re-implementing game rules in the viewer.
- **Components render; the app decides.** Nothing in `components/` knows game rules, log conventions or has HTML UI. Those live in `app/viewer/`.
- **Every action needs both forms.** An animated method (`await mat.doThing()`) and a `setState()`/`getState()` that reproduces its result instantly. `setState()` should rebuild only what differs.
- **The state is the truth, animations are best effort.** `GameTable.animate(event)` moves pieces; `reconcile(state)` then makes the table agree. A new event needs a line in `replay/reduce.js` (and its test still passing) before it needs an animation.
- **Use `fly()` / `tweens`** for movement and `tweens.wait()` for pauses, so speed, skip and scrub keep working. No `setTimeout` or own requestAnimationFrame loop inside an animation.
- **Never hand-edit generated images** in `components/*/assets`. Edit `art/manifest.json` (or add an op to `art/tools/extract.py`) and re-run it. Bird illustrations dropped into `components/cards/assets/birds/` are the exception: they are inputs.
- **Image URLs stay literal**: `new URL('../assets/x.jpg', import.meta.url).href`, so Vite bundles them.
- **Text is rendered, not cropped.** Draw names, numbers and rules text at runtime (canvas textures for 3D, HTML for 2D).
- Birdfeeder rolls are simulate-then-playback; don't make them depend on live physics.

## Checking your work
- `npm test`: reducer and log reader against `../docs/samples`. `WINGSIM_LOGS=<dir> npm test` adds every log under a folder.
- `npm run build` must succeed (viewer page and feeder demo).
- `npm run dev` serves on port 5273 (5173 is often taken on this machine). The page exposes `window.viewer` (`replay`, `game`, `player`, `hud`, `tweens`).
- No desktop browser here: use `tools/shot.mjs` for screenshots and `tools/playthrough.mjs` to run whole games through the animations (page errors, and events whose animation ended somewhere the state disagrees with). Both run in the `mcr.microsoft.com/playwright` podman image; the command is in each file's header. Run them one at a time: software WebGL uses every core.
- To see a frame mid-animation, freeze tween time: `viewer.tweens.speed = 0; viewer.player.step()`, then advance by hand with `viewer.tweens.speed = 1; viewer.tweens.update(0.3); viewer.tweens.speed = 0` between screenshots.

## Adding a new element from concept art
1. Copy the sheet into `art/source/`, register it under `sheets` in `art/manifest.json`.
2. `.venv/bin/python art/tools/find_boxes.py art/source/<sheet> --annotate`; check the `.boxes.jpg` and pick boxes.
3. Add `outputs` entries with `out` paths into the right component's `assets/`; run `.venv/bin/python art/tools/extract.py --preview`; look at `art/tools/preview.jpg`.
4. If the element has positions inside it (slots, spaces), record them as image fractions in that component's `layout.js` (or the `REGIONS` of its face-drawing file).
5. New 3D piece: follow `components/pieces/src/pieces.js` (shared geometry, origin on y = 0, `userData.piece`). New board-like thing: follow `GoalBoard` (slab + layout + setState/getState).
