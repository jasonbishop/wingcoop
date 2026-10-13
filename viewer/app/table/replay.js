// A short scripted replay: what a game log turned into component calls looks like.
//
// Each step is { label, run(game) }. `game` holds the components (see table.js).
// In your real viewer these steps would be generated from your game's event log.

import { seededRandom } from '../../components/birdfeeder/src/index.js';
import { SAMPLE_BIRDS } from '../../components/cards/src/index.js';

const bird = id => SAMPLE_BIRDS.find(b => b.id === id);

/** The state before step 1. Shape matches snapshot()/restore() in table.js. */
export const START = {
  mat: {
    wetland: [{ bird: bird('osprey'), eggs: ['blue'] }],
    supply: { invertebrate: 1, fish: 1 },
  },
  board: { goals: ['wetland_total', 'cave_dwellers', 'wetland_total', 'cave_dwellers'], cubes: [] },
  feeder: ['fish', 'seed', 'seed', 'rodent', 'invertebrate_seed'],
  deck: 36,
  tray: ['song-sparrow', 'savannah-sparrow', 'bald-eagle'],
};

export const STEPS = [
  {
    label: 'Gain food: take a fish from the birdfeeder',
    async run(g) { await takeFromFeeder(g, 'fish'); },
  },
  {
    label: 'Gain food: take a seed from the birdfeeder',
    async run(g) { await takeFromFeeder(g, 'seed'); },
  },
  {
    label: 'Play Song Sparrow in the forest (pay 1 seed)',
    async run(g) {
      const card = g.tray.take(0);
      await Promise.all([
        g.mat.playBird('forest', 0, card),
        g.mat.spendFood('seed'),
      ]);
    },
  },
  {
    label: 'Lay eggs: 2 on Song Sparrow, 1 on Osprey',
    async run(g) {
      await g.mat.layEggs('forest', 0, 2, 'speckled');
      await g.mat.layEggs('wetland', 0, 1, 'blue');
    },
  },
  {
    label: 'Refill the bird tray from the deck',
    async run(g) {
      const i = g.tray.firstEmpty();
      const card = await g.deck.draw(bird('chipping-sparrow'), g.tray.object3d, g.tray.slotPosition(i));
      g.tray.slots[i] = card;
    },
  },
  {
    label: 'Song Sparrow power: tuck 1 card',
    async run(g) { await g.mat.tuck('forest', 0, 1); },
  },
  {
    label: 'Osprey: cache a fish from the supply',
    async run(g) { await g.mat.cacheFood('wetland', 0, 'fish', { fromSupply: true }); },
  },
  {
    label: 'Feeder empty of choices: reroll all 5 dice',
    async run(g) {
      await g.feeder.roll({ faces: ['fruit', 'fish', 'rodent', 'seed', 'invertebrate'], random: seededRandom(8) });
    },
  },
  {
    label: 'End of round 1: score the wetland goal',
    async run(g) {
      await g.board.placeCube(1, { medallion: 4 }, 'blue', { from: g.mat.supply.localToWorld(g.mat.pilePosition('fish').setY(1)) });
      await g.board.placeCube(1, { medallion: 2 }, 'red');
    },
  },
];

async function takeFromFeeder(g, face) {
  const die = g.feeder.getDice().find(d => !d.taken && d.face === face);
  if (!die) return;
  const from = g.feeder.dieWorldPosition(die.index);
  g.feeder.take(die.index);
  await g.mat.addFood(face === 'invertebrate_seed' ? 'seed' : face, { from });
}
