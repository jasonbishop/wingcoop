// PlayerMat — a player's board: three habitat rows of seven card slots, plus the
// food supply in front of it. It owns everything sitting on it: bird cards, eggs,
// cached food, tucked cards.
//
// Every action has an animated form (await mat.layEggs(...)) and the whole board can be
// set instantly from plain data (mat.setState(...)) for scrubbing a replay.

import * as THREE from 'three';
import { loadTexture } from '../../tabletop/src/assets.js';
import { roundedSlab } from '../../tabletop/src/geometry.js';
import { tweens, fly } from '../../tabletop/src/tween.js';
import { BirdCard, TuckTab, CARD_W, CARD_H, CARD_T, FACE_UP } from '../../cards/src/cards.js';
import { createEgg, createFoodToken, FOODS, TOKEN_HEIGHT } from '../../pieces/src/pieces.js';
import { HABITATS, SLOTS_PER_ROW, MAT_IMAGE, slotCenterUV } from './layout.js';

const MAT_URL = new URL('../assets/mat.jpg', import.meta.url).href;

export const MAT_W = 18;
export const MAT_H = MAT_W * (MAT_IMAGE[1] / MAT_IMAGE[0]);
const MAT_T = 0.05;

// Positions on a bird card, relative to its centre (x right, z toward the card's bottom edge).
const EGG_SPOTS = [[-0.18, 0.22], [0.12, 0.22], [0.42, 0.22], [-0.18, 0.52], [0.12, 0.52], [0.42, 0.52]];
const CACHE_SPOT = [0.42, -0.35];      // cached food stacks here
const TUCK_PEEK = 0.16;                // how far each tucked card shows above the bird card

const edgeMat = new THREE.MeshStandardMaterial({ color: 0xd9ccb0, roughness: 1 });

export class PlayerMat {
  /**
   * @param {{name?: string}} [opts] name is just stored, for your own bookkeeping
   */
  constructor({ name = 'player' } = {}) {
    this.name = name;
    this.object3d = new THREE.Group();
    this.object3d.name = `player-mat-${name}`;
    const top = new THREE.MeshStandardMaterial({ map: loadTexture(MAT_URL), roughness: 0.95 });
    this._board = roundedSlab(MAT_W, MAT_H, 0.25, MAT_T, top, edgeMat, edgeMat);
    this.object3d.add(this._board);

    // one group per slot, sitting on the mat surface
    this._slots = {};
    for (const h of HABITATS) {
      this._slots[h] = [];
      for (let i = 0; i < SLOTS_PER_ROW; i++) {
        const g = new THREE.Group();
        g.name = `${h}-${i}`;
        g.position.copy(this.slotPosition(h, i));
        this.object3d.add(g);
        this._slots[h].push({ group: g, card: null, eggs: [], cached: [], tucked: [], tab: null });
      }
    }

    // food supply in front of the mat: one pile per food type
    this.supply = new THREE.Group();
    this.supply.name = 'supply';
    this.supply.position.set(0, 0, MAT_H / 2 + 0.75);
    this.object3d.add(this.supply);
    this._piles = Object.fromEntries(FOODS.map(f => [f, []]));
  }

  // ------------------------------------------------------------------ layout

  /** Local position of a slot's centre on the mat surface. */
  slotPosition(habitat, i) {
    const [u, v] = slotCenterUV(habitat, i);
    return new THREE.Vector3((u - 0.5) * MAT_W, MAT_T, (v - 0.5) * MAT_H);
  }

  /** The THREE.Group for a slot (cards, eggs etc. are its children). */
  slotGroup(habitat, i) { return this._slot(habitat, i).group; }

  /** Local position of the top of a food pile in the supply. */
  pilePosition(food, height = this._piles[food].length) {
    const i = FOODS.indexOf(food);
    return new THREE.Vector3((i - (FOODS.length - 1) / 2) * 1.15, height * TOKEN_HEIGHT, 0);
  }

  // ------------------------------------------------------------------ birds

  /**
   * Play a bird into a slot.
   * @param {string} habitat 'wetland' | 'forest' | 'grassland'
   * @param {number} i       slot 0..6 (left to right)
   * @param {BirdCard|object} cardOrBird  an existing BirdCard (it flies from wherever it is) or bird data (a new card drops in)
   * @param {{animate?:boolean, duration?:number}} [opts]
   * @returns {Promise<BirdCard>}
   */
  async playBird(habitat, i, cardOrBird, opts = {}) {
    const s = this._slot(habitat, i);
    if (s.card) throw new Error(`[PlayerMat] ${habitat} slot ${i} already has a bird`);
    let card = cardOrBird;
    if (!(card instanceof BirdCard)) {
      card = new BirdCard(cardOrBird, { faceUp: true });
      s.group.add(card.object3d);
      card.object3d.position.set(0, opts.animate === false ? 0 : 3, 0);
    }
    s.card = card;
    card.object3d.userData.pick = { type: 'slot', habitat, slot: i, bird: card.bird, mat: this.name };
    await card.moveTo(s.group, new THREE.Vector3(0, s.tucked.length * CARD_T, 0), { faceUp: true, ...opts });
    return card;
  }

  /** Remove the bird card from a slot (and everything on it). Returns the BirdCard, still in the scene. */
  removeBird(habitat, i) {
    const s = this._slot(habitat, i);
    const card = s.card;
    this._clearSlot(s, { keepCard: true });
    return card;
  }

  // ------------------------------------------------------------------ eggs

  /**
   * Lay eggs on a bird. Eggs drop in from above, or fly from `from` (a world-space Vector3).
   * @param {string|string[]} kind  egg kind for all, or one per egg ('blue' | 'speckled' | 'cream')
   */
  async layEggs(habitat, i, count = 1, kind = 'cream', { from = null, animate = true, stagger = 0.12 } = {}) {
    const s = this._slot(habitat, i);
    const jobs = [];
    for (let k = 0; k < count; k++) {
      const egg = createEgg(Array.isArray(kind) ? kind[k] : kind);
      const spot = this._eggSpot(s, s.eggs.length);
      s.eggs.push(egg);
      if (!animate) { s.group.add(egg); egg.position.copy(spot); continue; }
      if (from) {
        this._root().add(egg);
        egg.position.copy(from);
        jobs.push(fly(egg, s.group, spot, undefined, { delay: k * stagger, duration: 0.6, arc: 1 }));
      } else {
        s.group.add(egg);
        egg.position.copy(spot).add(new THREE.Vector3(0, 1.6, 0));
        egg.scale.setScalar(0.01);
        jobs.push(tweens.to(egg, { position: spot, scale: 1 }, { delay: k * stagger, duration: 0.45, ease: 'out' }));
      }
    }
    await Promise.all(jobs);
  }

  /** Remove eggs from a bird (they lift and vanish). Returns the kinds removed. */
  async removeEggs(habitat, i, count = 1, { animate = true } = {}) {
    const s = this._slot(habitat, i);
    const gone = s.eggs.splice(Math.max(0, s.eggs.length - count), count);
    await Promise.all(gone.map((egg, k) => this._vanish(egg, animate, k * 0.08)));
    return gone.map(e => e.userData.piece.kind);
  }

  // ------------------------------------------------------------------ cached food & tucked cards

  /** Cache a food token on a bird (from the supply pile if `fromSupply`, else from `from` or above). */
  async cacheFood(habitat, i, food, { from = null, fromSupply = false, animate = true } = {}) {
    const s = this._slot(habitat, i);
    let token;
    if (fromSupply && this._piles[food].length) token = this._piles[food].pop();
    else {
      token = createFoodToken(food);
      if (from) { this._root().add(token); token.position.copy(from); }
      else { s.group.add(token); token.position.set(CACHE_SPOT[0], 2, CACHE_SPOT[1]); }
    }
    const spot = new THREE.Vector3(CACHE_SPOT[0], this._cardTop(s) + s.cached.length * TOKEN_HEIGHT, CACHE_SPOT[1]);
    s.cached.push(token);
    await fly(token, s.group, spot, undefined, { animate, duration: 0.6, arc: 0.8 });
  }

  /**
   * Tuck cards behind a bird. Each tucked card peeks out above it; a tab shows the count.
   * @param {{from?:BirdCard[]}} [opts] existing cards to tuck (e.g. from a hand); otherwise blank ones appear
   */
  async tuck(habitat, i, count = 1, { from = [], animate = true } = {}) {
    const s = this._slot(habitat, i);
    const jobs = [];
    for (let k = 0; k < count; k++) {
      const card = from[k] || new BirdCard(null, { faceUp: true });
      if (!from[k]) { s.group.add(card.object3d); card.object3d.position.set(0, 2.5, -CARD_H / 2); }
      const n = s.tucked.length;
      s.tucked.push(card);
      const pos = new THREE.Vector3(0, n * CARD_T, -TUCK_PEEK * (n + 1));
      jobs.push(card.moveTo(s.group, pos, { faceUp: true, animate, delay: k * 0.15, duration: 0.55, arc: 0.6 }));
    }
    await Promise.all(jobs);
    this._restack(s, animate);
  }

  // ------------------------------------------------------------------ supply

  /** Add a food token to the supply, flying from `from` (world Vector3) or dropping in. */
  async addFood(food, { from = null, animate = true } = {}) {
    const token = createFoodToken(food);
    const pile = this._piles[food];
    const spot = this.pilePosition(food, pile.length);
    pile.push(token);
    if (from) { this._root().add(token); token.position.copy(from); }
    else { this.supply.add(token); token.position.copy(spot).add(new THREE.Vector3(0, 1.5, 0)); }
    await fly(token, this.supply, spot, undefined, { animate, duration: 0.7, arc: from ? 2 : 0 });
    return token;
  }

  /** Remove a food token from the supply (it vanishes, or flies `to` a world point). Returns false if none. */
  async spendFood(food, { to = null, animate = true } = {}) {
    const token = this._piles[food].pop();
    if (!token) return false;
    if (to && animate) {
      const root = this._root();
      root.attach(token);
      await tweens.to(token, { position: to }, { duration: 0.6, arc: 1.5 });
      token.parent.remove(token);
    } else await this._vanish(token, animate);
    return true;
  }

  // ------------------------------------------------------------------ state

  /**
   * Replace everything on the mat instantly. Shape (all keys optional):
   * {
   *   wetland:   [ { bird, eggs: ['cream','blue'] | 2, cached: ['fish'], tucked: 3 }, null, … ],
   *   forest:    [ … ],
   *   grassland: [ … ],
   *   supply:    { fish: 2, seed: 1 }
   * }
   */
  setState(state = {}) {
    for (const h of HABITATS) {
      (this._slots[h]).forEach((s, i) => {
        this._clearSlot(s);
        const d = state[h]?.[i];
        if (!d || !d.bird) return;
        if (d.tucked) this.tuck(h, i, d.tucked, { animate: false });
        this.playBird(h, i, d.bird, { animate: false });
        const eggs = typeof d.eggs === 'number' ? new Array(d.eggs).fill('cream') : (d.eggs || []);
        if (eggs.length) this.layEggs(h, i, eggs.length, eggs, { animate: false });
        for (const f of d.cached || []) this.cacheFood(h, i, f, { animate: false });
      });
    }
    for (const f of FOODS) {
      for (const t of this._piles[f]) t.parent?.remove(t);
      this._piles[f] = [];
      for (let k = 0; k < (state.supply?.[f] || 0); k++) this.addFood(f, { animate: false });
    }
  }

  /** Current contents as plain data (same shape as setState). */
  getState() {
    const out = {};
    for (const h of HABITATS) {
      out[h] = this._slots[h].map(s => (s.card ? {
        bird: s.card.bird,
        eggs: s.eggs.map(e => e.userData.piece.kind),
        cached: s.cached.map(t => t.userData.piece.food),
        tucked: s.tucked.length,
      } : null));
    }
    out.supply = Object.fromEntries(FOODS.map(f => [f, this._piles[f].length]).filter(([, n]) => n));
    return out;
  }

  /** First empty slot index in a habitat row, or -1. */
  firstEmpty(habitat) { return this._slots[habitat].findIndex(s => !s.card); }

  dispose() {
    for (const h of HABITATS) this._slots[h].forEach(s => this._clearSlot(s));
  }

  // ------------------------------------------------------------------ internals

  _slot(habitat, i) {
    const row = this._slots[habitat];
    if (!row) throw new Error(`[PlayerMat] unknown habitat "${habitat}". Use one of: ${HABITATS.join(', ')}`);
    if (!row[i]) throw new Error(`[PlayerMat] slot ${i} out of range 0..${SLOTS_PER_ROW - 1}`);
    return row[i];
  }

  _cardTop(s) { return (s.tucked.length + 1) * CARD_T + 0.002; }

  _eggSpot(s, k) {
    const [x, z] = EGG_SPOTS[k % EGG_SPOTS.length];
    const layer = Math.floor(k / EGG_SPOTS.length);   // more than 6: stack a second layer offset a little
    return new THREE.Vector3(x + layer * 0.08, this._cardTop(s), z - layer * 0.08);
  }

  // keep the bird card on top of tucked cards, and the eggs/food/tab on top of the bird
  _restack(s, animate) {
    const y = s.tucked.length * CARD_T;
    if (s.card) {
      if (animate) tweens.to(s.card.object3d, { position: new THREE.Vector3(0, y, 0) }, { duration: 0.2 });
      else s.card.object3d.position.y = y;
    }
    s.eggs.forEach((e, k) => e.position.copy(this._eggSpot(s, k)));
    s.cached.forEach((t, k) => t.position.set(CACHE_SPOT[0], this._cardTop(s) + k * TOKEN_HEIGHT, CACHE_SPOT[1]));
    if (s.tucked.length) {
      if (!s.tab) { s.tab = new TuckTab(0); s.group.add(s.tab.object3d); }
      s.tab.setCount(s.tucked.length);
      const peek = -CARD_H / 2 - TUCK_PEEK * s.tucked.length / 2 - 0.02;
      s.tab.object3d.position.set(0, s.tucked.length * CARD_T + 0.004, Math.max(peek, -CARD_H / 2 - 0.2));
    }
  }

  _clearSlot(s, { keepCard = false } = {}) {
    for (const o of [...s.eggs, ...s.cached]) o.parent?.remove(o);
    for (const c of s.tucked) c.dispose();
    if (s.card && !keepCard) s.card.dispose();
    if (s.tab) { s.tab.dispose(); s.tab.object3d.parent?.remove(s.tab.object3d); }
    Object.assign(s, { card: null, eggs: [], cached: [], tucked: [], tab: null });
  }

  async _vanish(obj, animate, delay = 0) {
    if (animate) await tweens.to(obj, { position: obj.position.clone().add(new THREE.Vector3(0, 1.2, 0)), scale: 0.01 }, { duration: 0.4, delay });
    obj.parent?.remove(obj);
  }

  _root() { let r = this.object3d; while (r.parent) r = r.parent; return r; }
}

export { HABITATS, SLOTS_PER_ROW };
export { FACE_UP };
