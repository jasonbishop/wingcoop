// The six faces of a food die.
//
// FACE_KEYS is also the default order of a die's faces in Three.js BoxGeometry
// material slots: +x, -x, +y, -y, +z, -z. Rigged rolls swap entries per die,
// so never assume a fixed slot -> face mapping outside BirdFeeder.js.

export const FACE_KEYS = ['invertebrate', 'seed', 'fish', 'fruit', 'rodent', 'invertebrate_seed'];

export const FACES = {
  invertebrate:      { label: 'Invertebrate',         foods: ['invertebrate'] },
  seed:              { label: 'Seed',                 foods: ['seed'] },
  fish:              { label: 'Fish',                 foods: ['fish'] },
  fruit:             { label: 'Fruit',                foods: ['fruit'] },
  rodent:            { label: 'Rodent',               foods: ['rodent'] },
  invertebrate_seed: { label: 'Invertebrate or seed', foods: ['invertebrate', 'seed'] },
};

export function isFaceKey(key) {
  return Object.prototype.hasOwnProperty.call(FACES, key);
}
