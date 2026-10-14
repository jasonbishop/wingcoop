// URLs of every image the feeder uses.
//
// Written as `new URL('…', import.meta.url)` with literal paths so that bundlers
// (Vite, webpack 5, esbuild, Parcel) copy the files and fingerprint them in builds.
// Keep each path a string literal — a computed path will not be picked up.
//
// To swap art at runtime instead, pass `textures: { front: '/my/front.jpg', … }`
// to `new BirdFeeder()`. Keys are the same as below.

export const DEFAULT_TEXTURES = {
  front:     new URL('../assets/front.jpg', import.meta.url).href,
  back:      new URL('../assets/back.jpg', import.meta.url).href,
  sideA:     new URL('../assets/sideA.jpg', import.meta.url).href,
  sideB:     new URL('../assets/sideB.jpg', import.meta.url).href,
  roofA:     new URL('../assets/roofA.jpg', import.meta.url).href,
  roofB:     new URL('../assets/roofB.jpg', import.meta.url).href,
  cap:       new URL('../assets/cap.jpg', import.meta.url).href,
  trayFloor: new URL('../assets/trayFloor.jpg', import.meta.url).href,
  trayRim:   new URL('../assets/trayRim.jpg', import.meta.url).href,

  die_invertebrate:      new URL('../assets/die_invertebrate.jpg', import.meta.url).href,
  die_seed:              new URL('../assets/die_seed.jpg', import.meta.url).href,
  die_fish:              new URL('../assets/die_fish.jpg', import.meta.url).href,
  die_fruit:             new URL('../assets/die_fruit.jpg', import.meta.url).href,
  die_rodent:            new URL('../assets/die_rodent.jpg', import.meta.url).href,
  die_invertebrate_seed: new URL('../assets/die_invertebrate_seed.jpg', import.meta.url).href,
};

// Round food-token icons (transparent PNG, 160px) for your 2D UI — tallies, logs, tooltips.
export const TOKEN_ICONS = {
  invertebrate: new URL('../assets/token_invertebrate.png', import.meta.url).href,
  seed:         new URL('../assets/token_seed.png', import.meta.url).href,
  fish:         new URL('../assets/token_fish.png', import.meta.url).href,
  fruit:        new URL('../assets/token_fruit.png', import.meta.url).href,
  rodent:       new URL('../assets/token_rodent.png', import.meta.url).href,
};
