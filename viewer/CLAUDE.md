# Notes for Claude Code

3D tabletop components for a Wingspan-style replay viewer. Read README.md first, then the component you're touching (`components/birdfeeder/README.md` has the most detail).

## Ground rules
- **Components render; the app decides.** Nothing in `components/` knows game rules or has HTML UI. Game logic, logs and buttons belong in the app (see `app/table/`).
- **Every action needs both forms.** If you add an animated method (`await mat.doThing()`), make sure `setState()`/`getState()` can reproduce its result instantly; replays depend on scrubbing.
- **Use `fly()` / `tweens`** for movement so `tweens.speed` and `tweens.finishAll()` keep working. Never animate with your own requestAnimationFrame loop.
- **Never hand-edit generated images** in `components/*/assets`. Edit `art/manifest.json` (or add an op to `art/tools/extract.py`) and run `python3 art/tools/extract.py`.
- **Image URLs stay literal**: `new URL('../assets/x.jpg', import.meta.url).href`, so Vite bundles them.
- **Text is rendered, not cropped.** The image generator's text is gibberish; draw names, numbers and rules text at runtime (canvas textures for 3D, HTML for 2D).
- Birdfeeder rolls are simulate-then-playback; rigging swaps face materials before playback. Don't make it depend on live physics.

## Checking your work
- `npm run dev`: `app/index.html` exposes `window.game` (`table`, `mat`, `board`, `feeder`, `deck`, `tray`).
- Round-trip test for any state change: `const s = game.mat.getState(); game.mat.setState(s);` should leave the board looking identical.
- Feeder physics: see "Tuning the physics" in `components/birdfeeder/README.md`.
- `npm run build` must succeed (it builds both demo pages).

## Adding a new element from concept art
1. Copy the sheet into `art/source/`, register it under `sheets` in `art/manifest.json`.
2. `python3 art/tools/find_boxes.py art/source/<sheet> --annotate`; check the `.boxes.jpg` and pick boxes.
3. Add `outputs` entries with `out` paths into the right component's `assets/`; run `python3 art/tools/extract.py --preview`; look at `art/tools/preview.jpg`.
4. If the element has positions inside it (slots, spaces), record them as image fractions in that component's `layout.js`.
5. New 3D piece: follow `components/pieces/src/pieces.js` (shared geometry, origin on y = 0, `userData.piece`). New board-like thing: follow `GoalBoard` (slab + layout + setState/getState).
