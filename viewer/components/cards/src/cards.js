// Bird cards, bonus cards, the face-down deck, a face-up pile, a row of face-up cards,
// a fanned hand, and the tucked-cards tab.
//
// Card size is CARD_W x CARD_H in table units, lying flat on y = 0, with the card's
// top edge toward -Z. Face-down = rotated 180° about the card's long (Z) axis.

import * as THREE from 'three';
import { loadTexture, loadImage } from '../../tabletop/src/assets.js';
import { roundedSlab, roundedFaceGeometry } from '../../tabletop/src/geometry.js';
import { fly, tweens } from '../../tabletop/src/tween.js';
import { drawCardFace, FACE_URL, FACE_SIZE } from './cardFace.js';
import { drawBonusFace, BONUS_FACE_URL } from './bonusFace.js';

export const CARD_W = 1.5;
export const CARD_H = CARD_W * (FACE_SIZE[1] / FACE_SIZE[0]);
export const CARD_T = 0.012;
const CARD_R = 0.07;

const BACK_URL = new URL('../assets/card_back.jpg', import.meta.url).href;
const BONUS_BACK_URL = new URL('../assets/bonus_back.jpg', import.meta.url).href;
const TUCK_URL = new URL('../assets/tuck_tab.jpg', import.meta.url).href;

export const FACE_UP = new THREE.Quaternion();
export const FACE_DOWN = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI);

const edgeMat = new THREE.MeshStandardMaterial({ color: 0xe9dcc2, roughness: 0.95 });
const mats = {};
const material = (key, url, roughness) =>
  (mats[key] ||= new THREE.MeshStandardMaterial({ map: loadTexture(url), roughness }));

// The two kinds of card: which back they show, and how their face is drawn.
const KINDS = {
  bird: {
    back: () => material('birdBack', BACK_URL, 0.8),
    blank: () => material('birdBlank', FACE_URL, 0.9),
    draw: drawCardFace,
  },
  bonus: {
    back: () => material('bonusBack', BONUS_BACK_URL, 0.8),
    blank: () => material('bonusBlank', BONUS_FACE_URL, 0.9),
    draw: drawBonusFace,
  },
};

// ============================================================================ face textures

// Drawing a face is the expensive part of a card, so faces are shared: every card showing
// the same thing (same `id`) uses one texture. A texture nobody is using is kept for a
// while in case a scrub brings the card straight back, then freed.

let faceScale = 0.6;
const faces = new Map();   // key -> { texture: Promise<THREE.Texture>, refs }
const idle = [];           // keys with refs === 0, oldest first
const IDLE_LIMIT = 64;

/**
 * Size of card face textures relative to the card art (1 = 910 x 1320). Lower it to
 * save memory on a table with many cards. Applies to faces drawn after the call.
 */
export function setCardDetail(scale) { faceScale = Math.min(1, Math.max(0.25, scale)); }

function acquireFace(kind, data) {
  const key = data.id == null ? null : `${kind}:${data.id}`;
  const make = () => KINDS[kind].draw(data, { scale: faceScale }).then(canvas => {
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    return tex;
  });
  if (key == null) return { key: null, texture: make() };
  let f = faces.get(key);
  if (!f) { f = { texture: make(), refs: 0 }; faces.set(key, f); }
  else if (f.refs === 0) idle.splice(idle.indexOf(key), 1);
  f.refs++;
  return { key, texture: f.texture };
}

function releaseFace(handle) {
  if (!handle) return;
  if (handle.key == null) { handle.texture.then(t => t.dispose()); return; }
  const f = faces.get(handle.key);
  if (!f || --f.refs > 0) return;
  idle.push(handle.key);
  while (idle.length > IDLE_LIMIT) {
    const old = idle.shift();
    faces.get(old)?.texture.then(t => t.dispose());
    faces.delete(old);
  }
}

// ============================================================================ Card

/** A card of either kind. Use BirdCard or BonusCard. */
class Card {
  constructor(kind, data, { faceUp = false } = {}) {
    this.kind = kind;
    this.object3d = new THREE.Group();
    this.object3d.name = `${kind}-card`;
    this._faceMat = new THREE.MeshStandardMaterial({ map: KINDS[kind].blank().map, roughness: 0.9 });
    this._slab = roundedSlab(CARD_W, CARD_H, CARD_R, CARD_T, this._faceMat, KINDS[kind].back(), edgeMat);
    this.object3d.add(this._slab);
    this._faceUp = faceUp;
    this.object3d.quaternion.copy(faceUp ? FACE_UP : FACE_DOWN);
    this._slab.position.y = faceUp ? 0 : -CARD_T;   // keep the card resting on y=0 either way
    this.data = null;
    this._face = null;
    if (data) this.setData(data);
  }

  /** Change what this card shows (null = anonymous). Resolves when the face has been drawn. */
  async setData(data) {
    if (data === this.data) return;
    this.data = data;
    this.object3d.userData.pick = { type: this.kind === 'bird' ? 'card' : 'bonus', [this.kind]: data };
    releaseFace(this._face);
    this._face = null;
    if (!data) {
      this._faceMat.map = KINDS[this.kind].blank().map;
      this._faceMat.needsUpdate = true;
      return;
    }
    const face = (this._face = acquireFace(this.kind, data));
    const tex = await face.texture;
    if (this._face !== face) return;   // superseded or disposed
    this._faceMat.map = tex;
    this._faceMat.needsUpdate = true;
  }

  get faceUp() { return this._faceUp; }

  /** Turn the card over in place (with a little hop when animated). */
  async flip(faceUp = !this._faceUp, { animate = true, duration = 0.45 } = {}) {
    if (faceUp === this._faceUp) return;
    this._faceUp = faceUp;
    const q = this.object3d.quaternion.clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI));
    if (animate) await tweens.to(this.object3d, { quaternion: q }, { duration });
    this.object3d.quaternion.copy(q);
    this._slab.position.y = faceUp ? 0 : -CARD_T;
  }

  /**
   * Fly the card into a parent at a local position, ending face up or down.
   * @returns {Promise<this>}
   */
  async moveTo(parent, position, { faceUp = this._faceUp, rotationY = 0, ...opts } = {}) {
    this._faceUp = faceUp;
    const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), rotationY).multiply(faceUp ? FACE_UP : FACE_DOWN);
    this._slab.position.y = faceUp ? 0 : -CARD_T;
    await fly(this.object3d, parent, position, q, opts);
    return this;
  }

  dispose() {
    releaseFace(this._face);
    this._face = null;
    this._faceMat.dispose();
    this.object3d.parent?.remove(this.object3d);
  }
}

export class BirdCard extends Card {
  /**
   * @param {import('./cardFace.js').Bird|null} bird  null for an anonymous card
   * @param {{faceUp?: boolean}} [opts]
   */
  constructor(bird = null, opts) { super('bird', bird, opts); }
  get bird() { return this.data; }
  /** Change which bird this card shows. Resolves when the face has been drawn. */
  setBird(bird) { return this.setData(bird); }
}

export class BonusCard extends Card {
  /**
   * @param {import('./bonusFace.js').Bonus|null} bonus  null for an anonymous card
   * @param {{faceUp?: boolean}} [opts]
   */
  constructor(bonus = null, opts) { super('bonus', bonus, opts); }
  get bonus() { return this.data; }
  setBonus(bonus) { return this.setData(bonus); }
}

const makeCard = (kind, data, opts) => (kind === 'bonus' ? new BonusCard(data, opts) : new BirdCard(data, opts));

// ============================================================================ CardDeck

/** A face-down draw pile. Its height follows `count`. */
export class CardDeck {
  /** @param {{count?:number, cardThickness?:number, kind?:'bird'|'bonus'}} [o] */
  constructor({ count = 40, cardThickness = 0.01, kind = 'bird' } = {}) {
    this.kind = kind;
    this.object3d = new THREE.Group();
    this.object3d.name = `${kind}-deck`;
    this.object3d.userData.pick = { type: 'deck', kind };
    this._t = cardThickness;

    const side = sideStripes();
    this._sideMat = new THREE.MeshStandardMaterial({ map: side, roughness: 0.95 });
    const back = KINDS[kind].back();
    this._stack = roundedSlab(CARD_W, CARD_H, CARD_R, 1, back, back, this._sideMat);
    // the slab's top face sits at y = 1 + epsilon; we scale the body and move the faces instead
    this.object3d.add(this._stack);
    this.count = count;
  }

  get count() { return this._count; }
  set count(n) {
    this._count = Math.max(0, n);
    const h = Math.max(this._count * this._t, 0.0001);
    const [body, top, bottom] = this._stack.children;
    body.scale.set(1, 1, h);   // extrude depth is along the body's local z (rotated to y)
    top.position.y = h + 0.0015;
    bottom.position.y = -0.0015;
    this._sideMat.map.repeat.set(1, Math.max(1, this._count / 8));
    this._stack.visible = this._count > 0;
  }

  /** Local position of the top of the pile. */
  get top() { return new THREE.Vector3(0, this._count * this._t, 0); }

  /**
   * Take the top card (count - 1) and fly it to a destination.
   * @param {object} data   what the card is (null to keep it anonymous)
   * @param {THREE.Object3D} parent  where it goes
   * @param {THREE.Vector3} position local position in parent
   * @param {{faceUp?:boolean, animate?:boolean, duration?:number, arc?:number, rotationY?:number}} [opts]
   * @returns {Promise<BirdCard|BonusCard>}
   */
  async draw(data, parent, position, opts = {}) {
    const card = this.lift(data);
    await card.moveTo(parent, position, { faceUp: true, arc: 1.6, duration: 0.8, ...opts });
    return card;
  }

  /** Take the top card off the pile without moving it anywhere yet (it stays face down on top). */
  lift(data = null) {
    const card = makeCard(this.kind, data, { faceUp: false });
    this.object3d.add(card.object3d);
    card.object3d.position.copy(this.top);
    this.count = this._count - 1;
    return card;
  }

  dispose() {
    this._sideMat.map.dispose();
    this._sideMat.dispose();
  }
}

function sideStripes() {
  const c = document.createElement('canvas');
  c.width = 8; c.height = 64;
  const g = c.getContext('2d');
  g.fillStyle = '#e8dcc4'; g.fillRect(0, 0, 8, 64);
  for (let y = 0; y < 64; y += 8) { g.fillStyle = 'rgba(80,70,55,0.35)'; g.fillRect(0, y, 8, 1); }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

// ============================================================================ CardPile

/** A face-up pile (a discard pile): a stack whose height follows `count`, with its top card showing. */
export class CardPile {
  /** @param {{cardThickness?:number, kind?:'bird'|'bonus'}} [o] */
  constructor({ cardThickness = 0.01, kind = 'bird' } = {}) {
    this.kind = kind;
    this.object3d = new THREE.Group();
    this.object3d.name = `${kind}-pile`;
    this._t = cardThickness;
    this._sideMat = new THREE.MeshStandardMaterial({ map: sideStripes(), roughness: 0.95 });
    const blank = KINDS[kind].blank();
    this._stack = roundedSlab(CARD_W, CARD_H, CARD_R, 1, blank, blank, this._sideMat);
    this.object3d.add(this._stack);
    this._count = 0;
    this._top = null;       // the card object on top
    this._resize();
  }

  get count() { return this._count; }

  /** Local position where the next card lands. */
  get top() { return new THREE.Vector3(0, this._count * this._t, 0); }

  /**
   * @param {{count?: number, top?: object|null}} state  `top` is the data of the card showing
   */
  setState({ count = 0, top = null } = {}) {
    this._count = Math.max(0, count);
    const same = this._top && this._top.data && top && sameCard(this._top.data, top);
    if (!same) {
      this._top?.dispose();
      this._top = this._count && top ? makeCard(this.kind, top, { faceUp: true }) : null;
      if (this._top) this.object3d.add(this._top.object3d);
    }
    if (!this._count && this._top) { this._top.dispose(); this._top = null; }
    this._resize();
  }

  getState() { return { count: this._count, top: this._top?.data ?? null }; }

  /** Put a card on the pile (it flies there and becomes the top card). */
  async add(card, opts = {}) {
    const at = this.top;
    this._count++;
    const old = this._top;
    this._top = card;
    await card.moveTo(this.object3d, at, { faceUp: true, duration: 0.6, arc: 1.2, ...opts });
    old?.dispose();
    this._resize();
  }

  _resize() {
    // the stack is every card but the top one, which is a real card
    const under = Math.max(0, this._count - (this._top ? 1 : 0));
    const h = Math.max(under * this._t, 0.0001);
    const [body, top, bottom] = this._stack.children;
    body.scale.set(1, 1, h);
    top.position.y = h + 0.0015;
    bottom.position.y = -0.0015;
    this._sideMat.map.repeat.set(1, Math.max(1, under / 8));
    this._stack.visible = under > 0;
    if (this._top) this._top.object3d.position.set(0, under * this._t, 0);
  }

  dispose() {
    this._top?.dispose();
    this._sideMat.map.dispose();
    this._sideMat.dispose();
  }
}

const sameCard = (a, b) => a === b || (a.id != null && a.id === b.id);

// ============================================================================ CardRow

/** A row of card positions, e.g. the three face-up cards of the bird tray. */
export class CardRow {
  constructor({ slots = 3, gap = 0.3 } = {}) {
    this.object3d = new THREE.Group();
    this.object3d.name = 'card-row';
    this.slots = new Array(slots).fill(null);
    this.gap = gap;
  }

  /** Local position of slot i (row is centred on the origin). */
  slotPosition(i) {
    const n = this.slots.length, step = CARD_W + this.gap;
    return new THREE.Vector3((i - (n - 1) / 2) * step, 0, 0);
  }

  /** Index of the first empty slot, or -1. */
  firstEmpty() { return this.slots.indexOf(null); }

  /** Put a card in slot i (flies there unless animate:false). */
  async place(i, card, opts = {}) {
    this.slots[i] = card;
    await card.moveTo(this.object3d, this.slotPosition(i), { faceUp: true, ...opts });
    return card;
  }

  /** Remove and return the card in slot i (it stays where it is until you move it). */
  take(i) {
    const c = this.slots[i];
    this.slots[i] = null;
    return c;
  }
}

// ============================================================================ CardFan

/**
 * A hand: any number of cards side by side, overlapping once they no longer fit in
 * `maxWidth`. Cards are told apart by a key you give (an id), so one can be taken out
 * to fly somewhere else. Later cards lie on top of earlier ones.
 */
export class CardFan {
  /**
   * @param {{maxWidth?:number, gap?:number, faceUp?:boolean|null}} [o]
   *   faceUp: true/false turns every card that way; null leaves each card as it is
   */
  constructor({ maxWidth = 12, gap = 0.12, faceUp = null } = {}) {
    this.object3d = new THREE.Group();
    this.object3d.name = 'card-fan';
    this.maxWidth = maxWidth;
    this.gap = gap;
    this.faceUp = faceUp;
    this._items = [];   // { key, card }
  }

  get count() { return this._items.length; }
  get keys() { return this._items.map(it => it.key); }
  get cards() { return this._items.map(it => it.card); }

  /** Local position of card i in a fan of n cards. */
  positionOf(i, n = this._items.length) {
    const step = n > 1 ? Math.min(CARD_W + this.gap, (this.maxWidth - CARD_W) / (n - 1)) : 0;
    return new THREE.Vector3((i - (n - 1) / 2) * step, i * CARD_T * 1.2, 0);
  }

  /** Add a card at the right-hand end; it flies in from wherever it is. */
  async add(key, card, opts = {}) {
    this._items.push({ key, card });
    await this._layout(opts, card);
    return card;
  }

  /**
   * Remove and return the first card with this key (null if there is none). The card stays
   * where it is until you move it; the rest close the gap.
   */
  take(key, opts = {}) {
    const i = this._items.findIndex(it => it.key === key);
    if (i < 0) return null;
    const [{ card }] = this._items.splice(i, 1);
    this._layout({ duration: 0.3, ...opts });
    return card;
  }

  /**
   * Make the fan hold exactly these keys, instantly. Cards already here are kept;
   * `create(key)` makes the missing ones and the rest are disposed.
   */
  setState(keys, create) {
    if (keys.length === this._items.length && keys.every((k, i) => k === this._items[i].key)) return;
    const pool = new Map();
    for (const it of this._items) {
      if (!pool.has(it.key)) pool.set(it.key, []);
      pool.get(it.key).push(it.card);
    }
    this._items = keys.map(key => ({ key, card: pool.get(key)?.shift() ?? create(key) }));
    for (const left of pool.values()) for (const card of left) card.dispose();
    this._layout({ animate: false });
  }

  getState() { return this.keys; }

  _layout(opts = {}, incoming = null) {
    const n = this._items.length;
    return Promise.all(this._items.map(({ card }, i) => {
      const to = this.positionOf(i, n);
      const here = card.object3d.parent === this.object3d;
      const faceUp = (card === incoming ? opts.faceUp : null) ?? this.faceUp ?? card.faceUp;
      if (here && card.object3d.position.distanceToSquared(to) < 1e-8 && card.faceUp === faceUp) return null;
      // cards already in the fan slide; a card arriving flies in an arc
      const arc = card === incoming || !here ? (opts.arc ?? 1.2) : 0;
      return card.moveTo(this.object3d, to, { duration: 0.6, ...opts, faceUp, arc });
    }));
  }

  dispose() {
    for (const { card } of this._items) card.dispose();
    this._items = [];
  }
}

// ============================================================================ TuckTab

/** The "tucked cards" tab from the art, with a live count. Lies flat, CARD_W wide. */
export class TuckTab {
  constructor(count = 0) {
    const h = CARD_W * (300 / 1670);
    this.canvas = document.createElement('canvas');
    this.canvas.width = 835; this.canvas.height = 150;
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.object3d = new THREE.Mesh(roundedFaceGeometry(CARD_W, h, 0.03), new THREE.MeshStandardMaterial({ map: this.texture, roughness: 0.9 }));
    this.object3d.name = 'tuck-tab';
    this.object3d.castShadow = this.object3d.receiveShadow = true;
    this._img = loadImage(TUCK_URL);
    this.setCount(count);
  }

  async setCount(n) {
    this.count = n;
    const img = await this._img;
    if (this.count !== n) return;
    const g = this.canvas.getContext('2d');
    const { width: W, height: H } = this.canvas;
    if (img) g.drawImage(img, 0, 0, W, H); else { g.fillStyle = '#e3d2b0'; g.fillRect(0, 0, W, H); }
    g.fillStyle = '#2b2620';
    g.font = '700 74px "Alegreya SC", Georgia, serif';
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(`${n} tucked`, W * 0.6, H * 0.52);
    this.texture.needsUpdate = true;
    this.object3d.visible = n > 0;
  }

  dispose() {
    this.texture.dispose();
    this.object3d.material.dispose();
  }
}
