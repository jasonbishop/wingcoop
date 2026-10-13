// Demo wiring. Everything game-specific (tally, buttons, log) lives here, outside the module:
// the module only renders the feeder and reports what happened.
import { BirdFeeder, FACES, TOKEN_ICONS, seededRandom } from '../../components/birdfeeder/src/index.js';

const $ = id => document.getElementById(id);

const feeder = new BirdFeeder({ container: $('feeder') });
feeder.ready.then(() => { $('loading').hidden = true; });

// ---- tally of dice in the tray, built from module events ----
function renderTally() {
  const dice = feeder.getDice().filter(d => !d.taken);
  const parts = ['<span class="label">In the tray</span>'];
  if (feeder.rolling) parts.push('<span class="empty">Dice falling…</span>');
  else if (!dice.length) parts.push('<span class="empty">Feeder empty: roll to refill</span>');
  else for (const d of dice) {
    const f = FACES[d.face];
    const icons = f.foods.map(food => `<img src="${TOKEN_ICONS[food]}" alt="">`).join('');
    parts.push(`<div class="chip${f.foods.length > 1 ? ' double' : ''}"><span class="icons">${icons}</span>${f.label}</div>`);
  }
  $('tally').innerHTML = parts.join('');
}

function log(text) {
  const li = document.createElement('li');
  li.textContent = text;
  $('log').prepend(li);
}

feeder.addEventListener('rollstart', e => {
  $('roll').disabled = true; $('skip').hidden = false;
  log(`rollstart: ${e.detail.count} dice${e.detail.rigged ? ' (rigged)' : ''}`);
  renderTally();
});
feeder.addEventListener('settled', e => {
  $('roll').disabled = false; $('roll').textContent = 'Roll again'; $('skip').hidden = true;
  log(`settled: ${e.detail.dice.map(d => d.face).join(', ')}`);
  renderTally();
});
feeder.addEventListener('take', e => { log(`take: die ${e.detail.index} (${e.detail.face})`); renderTally(); });

// ---- controls ----
$('roll').addEventListener('click', () => feeder.roll());
$('skip').addEventListener('click', () => feeder.skip());
$('xray').addEventListener('click', () => {
  feeder.setXray(!feeder.xray);
  $('xray').setAttribute('aria-pressed', String(feeder.xray));
});

// A replay knows what was rolled; the animation is generated to match it.
// The seed makes the tumble itself identical every time this turn is viewed.
const RECORDED_ROLLS = [
  { turn: 3, seed: 3, faces: ['fish', 'seed', 'seed', 'rodent', 'invertebrate_seed'] },
  { turn: 7, seed: 7, faces: ['fruit', 'fruit', 'fruit', 'fish', 'invertebrate'] },
  { turn: 12, seed: 12, faces: ['rodent', 'seed', 'invertebrate'] },
];
let next = 0;
const describe = r => `Turn ${r.turn}: ${r.faces.map(f => FACES[f].label).join(', ')}`;
$('rigged-faces').textContent = describe(RECORDED_ROLLS[0]);
$('rigged').addEventListener('click', async () => {
  const r = RECORDED_ROLLS[next];
  next = (next + 1) % RECORDED_ROLLS.length;
  $('rigged-faces').textContent = describe(RECORDED_ROLLS[next]);
  const result = await feeder.roll({ faces: r.faces, random: seededRandom(r.seed) });
  const ok = result.map(d => d.face).join() === r.faces.join();
  log(`replay turn ${r.turn}: ${ok ? 'matches the record' : 'MISMATCH'}`);
});

$('place').addEventListener('click', () => {
  feeder.setDice(['seed', 'fish', 'invertebrate_seed']);
  log('setDice: seed, fish, invertebrate_seed');
  renderTally();
});

// open with a roll so the feeder starts full
renderTally();
feeder.ready.then(() => feeder.roll());

// handy in the browser console
window.feeder = feeder;
