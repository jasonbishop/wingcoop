// Small game pieces: food tokens, eggs and player cubes.
//
// Each create*() returns a THREE.Object3D resting on y = 0 at its origin, tagged with
// userData.piece so you can tell what it is later. Geometry and materials are shared.

import * as THREE from 'three';
import { loadTexture } from '../../tabletop/src/assets.js';

export const FOODS = ['invertebrate', 'seed', 'fish', 'fruit', 'rodent'];
export const EGG_KINDS = ['blue', 'speckled', 'cream'];

/** Player colours for cubes (watercolour-muted to sit with the art). Keys are free-form. */
export const PLAYER_COLORS = {
  red: 0xb8534a,
  yellow: 0xd9b23e,
  blue: 0x4f7fae,
  green: 0x5f8a4a,
  purple: 0x7e62a6,
};

const FOOD_URLS = {
  invertebrate: new URL('../assets/food_invertebrate.jpg', import.meta.url).href,
  seed:         new URL('../assets/food_seed.jpg', import.meta.url).href,
  fish:         new URL('../assets/food_fish.jpg', import.meta.url).href,
  fruit:        new URL('../assets/food_fruit.jpg', import.meta.url).href,
  rodent:       new URL('../assets/food_rodent.jpg', import.meta.url).href,
};

/** 2D egg icons (transparent PNG) for UI. */
export const EGG_ICONS = {
  blue:     new URL('../assets/egg_blue.png', import.meta.url).href,
  speckled: new URL('../assets/egg_speckled.png', import.meta.url).href,
  cream:    new URL('../assets/egg_cream.png', import.meta.url).href,
};

/** 2D food icons (the same round token art) for UI. */
export const FOOD_ICONS = FOOD_URLS;

// ---------------------------------------------------------------- food tokens

export const TOKEN_RADIUS = 0.42, TOKEN_HEIGHT = 0.09;
const tokenGeo = new THREE.CylinderGeometry(TOKEN_RADIUS, TOKEN_RADIUS, TOKEN_HEIGHT, 48);
tokenGeo.translate(0, TOKEN_HEIGHT / 2, 0);
const tokenEdge = new THREE.MeshStandardMaterial({ color: 0x4a4338, roughness: 0.9 });
const tokenFaces = {};

export function createFoodToken(food) {
  if (!FOOD_URLS[food]) throw new Error(`[pieces] unknown food "${food}". Use one of: ${FOODS.join(', ')}`);
  tokenFaces[food] ||= new THREE.MeshStandardMaterial({ map: loadTexture(FOOD_URLS[food]), roughness: 0.85 });
  // CylinderGeometry groups: 0 side, 1 top, 2 bottom
  const m = new THREE.Mesh(tokenGeo, [tokenEdge, tokenFaces[food], tokenFaces[food]]);
  m.castShadow = m.receiveShadow = true;
  m.name = `food-${food}`;
  m.userData.piece = { type: 'food', food };
  return m;
}

// ---------------------------------------------------------------- eggs

export const EGG_HEIGHT = 0.42;
const eggGeo = (() => {
  const pts = [];
  const H = EGG_HEIGHT, R = H * 0.36;
  for (let i = 0; i <= 24; i++) {
    const a = (i / 24) * Math.PI;                       // 0 at the base, PI at the tip
    const r = Math.sin(a) * R * (1 + 0.14 * Math.cos(a)); // wider toward the base
    pts.push(new THREE.Vector2(Math.max(r, 1e-4), (1 - Math.cos(a)) * H / 2));
  }
  return new THREE.LatheGeometry(pts, 32);
})();

// Colours sampled from the egg art (see art/manifest.json egg_* entries).
const EGG_COLORS = { blue: '#b1c7bc', speckled: '#e4c5a8', cream: '#f0dfc5' };
const eggMats = {};

function eggMaterial(kind) {
  if (eggMats[kind]) return eggMats[kind];
  const c = document.createElement('canvas');
  c.width = 256; c.height = 128;
  const g = c.getContext('2d');
  g.fillStyle = EGG_COLORS[kind];
  g.fillRect(0, 0, 256, 128);
  // soft watercolour mottling
  let seed = kind.length * 97;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let i = 0; i < 40; i++) {
    g.fillStyle = `rgba(255,255,255,${0.05 + rnd() * 0.06})`;
    g.beginPath(); g.ellipse(rnd() * 256, rnd() * 128, 10 + rnd() * 30, 6 + rnd() * 16, 0, 0, Math.PI * 2); g.fill();
  }
  if (kind === 'speckled') {
    for (let i = 0; i < 220; i++) {
      const s = rnd() < 0.15 ? 2.5 + rnd() * 3 : 0.8 + rnd() * 1.6;
      g.fillStyle = `rgba(${100 + rnd() * 20},${76 + rnd() * 16},${56 + rnd() * 12},${0.55 + rnd() * 0.4})`;
      g.beginPath(); g.ellipse(rnd() * 256, 10 + rnd() * 108, s * 1.4, s, rnd() * 3, 0, Math.PI * 2); g.fill();
    }
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  eggMats[kind] = new THREE.MeshStandardMaterial({ map: tex, roughness: 0.55 });
  return eggMats[kind];
}

export function createEgg(kind = 'cream') {
  if (!EGG_COLORS[kind]) throw new Error(`[pieces] unknown egg "${kind}". Use one of: ${EGG_KINDS.join(', ')}`);
  const m = new THREE.Mesh(eggGeo, eggMaterial(kind));
  m.castShadow = m.receiveShadow = true;
  m.name = `egg-${kind}`;
  m.userData.piece = { type: 'egg', kind };
  return m;
}

// ---------------------------------------------------------------- cubes

export const CUBE_SIZE = 0.36;
const cubeGeo = new THREE.BoxGeometry(CUBE_SIZE, CUBE_SIZE, CUBE_SIZE);
cubeGeo.translate(0, CUBE_SIZE / 2, 0);
const cubeMats = {};

/** A player cube. `color` is a PLAYER_COLORS key or any CSS/hex colour. */
export function createCube(color = 'blue') {
  const key = String(color);
  cubeMats[key] ||= new THREE.MeshStandardMaterial({ color: PLAYER_COLORS[color] ?? color, roughness: 0.6 });
  const m = new THREE.Mesh(cubeGeo, cubeMats[key]);
  m.castShadow = m.receiveShadow = true;
  m.name = `cube-${key}`;
  m.userData.piece = { type: 'cube', color };
  return m;
}
