// Demo: every component on one table, driven by a scripted replay (replay.js).
//
// The pattern for a real replay viewer:
//   * Play forward: run each step's animated calls in order.
//   * Jump/scrub:   restore() a snapshot with every component's setState() — instant, no animation.
//   * Skip:         tweens.finishAll() + feeder.skip().

import * as THREE from 'three';
import { Tabletop, tweens, assetsReady } from '../../components/tabletop/src/index.js';
import { BirdFeeder } from '../../components/birdfeeder/src/index.js';
import { PlayerMat } from '../../components/player-mat/src/index.js';
import { GoalBoard } from '../../components/goal-board/src/index.js';
import { CardDeck, CardRow, BirdCard, SAMPLE_BIRDS } from '../../components/cards/src/index.js';
import { START, STEPS } from './replay.js';

const $ = id => document.getElementById(id);

// ------------------------------------------------------------------ build the table

const table = new Tabletop({
  container: $('table'),
  views: {
    overview: { position: [3, 31, 27], target: [3, 0, 1.5] },
    mat: { position: [0, 15, 17.5], target: [0, 0, 5.5] },
    feeder: { position: [18.5, 10, 3.5], target: [10.5, 2.5, -5.5] },
    goals: { position: [-4.5, 11, 4.5], target: [-4.5, 0, -4.8] },
  },
});
table.setView('overview', { animate: false });

const mat = table.add(new PlayerMat({ name: 'you' }), { position: [0, 0, 5.4] });
const board = table.add(new GoalBoard(), { position: [-3.6, 0, -4.8] });
const feeder = table.add(
  new BirdFeeder({ scene: table.scene, camera: table.camera, domElement: table.renderer.domElement, clickToTake: false }),
  { position: [10.5, 0, -7], scale: 0.55 },
);
const deck = table.add(new CardDeck({ count: START.deck }), { position: [12, 0, 3.6] });
const tray = table.add(new CardRow({ slots: 3, gap: 0.25 }), { position: [16.3, 0, 3.6] });

const game = { table, mat, board, feeder, deck, tray };
window.game = game;   // poke at it from the console

// ------------------------------------------------------------------ snapshots (for scrubbing back)

function snapshot() {
  return {
    mat: mat.getState(),
    board: board.getState(),
    feeder: feeder.getDice().filter(d => !d.taken).map(d => d.face),
    deck: deck.count,
    tray: tray.slots.map(c => c?.bird?.id ?? null),
  };
}

function restore(s) {
  tweens.finishAll();
  feeder.skip();
  mat.setState(s.mat);
  board.setState(s.board);
  feeder.setDice(s.feeder);
  deck.count = s.deck;
  tray.slots.forEach((c, i) => { c?.dispose(); tray.slots[i] = null; });
  s.tray.forEach((id, i) => {
    const b = typeof id === 'string' ? SAMPLE_BIRDS.find(x => x.id === id) : id;
    if (b) tray.place(i, new BirdCard(b, { faceUp: true }), { animate: false });
  });
}

// ------------------------------------------------------------------ replay controls

const snapshots = [];   // snapshots[i] = state before step i
let current = 0, busy = false;

const stepsEl = $('steps');
STEPS.forEach(s => {
  const li = document.createElement('li');
  li.textContent = s.label;
  stepsEl.append(li);
});

function render() {
  [...stepsEl.children].forEach((li, i) => {
    li.className = i < current ? 'done' : i === current ? 'current' : '';
  });
  $('prev').disabled = busy || current === 0;
  $('next').disabled = busy || current >= STEPS.length;
  $('all').disabled = busy || current >= STEPS.length;
  $('next').textContent = current >= STEPS.length ? 'Done' : 'Next ▶';
}

async function playStep() {
  if (current >= STEPS.length) return;
  snapshots[current] = snapshot();
  busy = true; render();
  await STEPS[current].run(game);
  current++;
  busy = false; render();
}

$('next').addEventListener('click', playStep);
$('all').addEventListener('click', async () => { while (current < STEPS.length) await playStep(); });
$('prev').addEventListener('click', () => {
  if (current === 0) return;
  current--;
  restore(snapshots[current]);
  render();
});
$('speed').addEventListener('change', e => {
  tweens.speed = Number(e.target.value);
  feeder.options.speed = Number(e.target.value);
});
document.querySelectorAll('[data-view]').forEach(b => b.addEventListener('click', () => table.setView(b.dataset.view)));

// ------------------------------------------------------------------ inspecting cards

table.addEventListener('pick', e => {
  const b = e.detail.bird;
  const el = $('inspect');
  if (!b) { el.hidden = true; return; }
  el.innerHTML = `<h3>${b.name}</h3><div class="sci">${b.scientific || ''}</div>
    <dl><dt>Points</dt><dd>${b.points ?? '–'}</dd>
    <dt>Habitat</dt><dd>${(b.habitats || []).join(', ')}</dd>
    <dt>Food</dt><dd>${(b.food || []).join(b.foodOr ? ' or ' : ' + ')}</dd>
    <dt>Eggs</dt><dd>${b.eggLimit ?? '–'} (${b.nest || '–'} nest)</dd>
    <dt>Power</dt><dd>${b.power || '–'}</dd></dl>`;
  el.hidden = false;
});

// ------------------------------------------------------------------ start

restore(START);
render();
Promise.all([assetsReady(), feeder.ready]).then(() => { $('loading').hidden = true; });
