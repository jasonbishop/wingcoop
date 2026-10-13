// Bird cards, the face-down deck, a row of face-up cards, and the tucked-cards tab.
//
// Card size is CARD_W x CARD_H in table units, lying flat on y = 0, with the card's
// top edge toward -Z. Face-down = rotated 180° about the card's long (Z) axis.

import * as THREE from 'three';
import { loadTexture, loadImage } from '../../tabletop/src/assets.js';
import { roundedSlab, roundedFaceGeometry } from '../../tabletop/src/geometry.js';
import { fly, tweens } from '../../tabletop/src/tween.js';
import { drawCardFace, FACE_URL, FACE_SIZE } from './cardFace.js';

export const CARD_W = 1.5;
export const CARD_H = CARD_W * (FACE_SIZE[1] / FACE_SIZE[0]);
export const CARD_T = 0.012;
const CARD_R = 0.07;

const BACK_URL = new URL('../assets/card_back.jpg', import.meta.url).href;
const TUCK_URL = new URL('../assets/tuck_tab.jpg', import.meta.url).href;

export const FACE_UP = new THREE.Quaternion();
export const FACE_DOWN = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 0, 1), Math.PI);

const edgeMat = new THREE.MeshStandardMaterial({ color: 0xe9dcc2, roughness: 0.95 });
let backMat = null, blankMat = null;
const getBackMat = () => (backMat ||= new THREE.MeshStandardMaterial({ map: loadTexture(BACK_URL), roughness: 0.8 }));
const getBlankMat = () => (blankMat ||= new THREE.MeshStandardMaterial({ map: loadTexture(FACE_URL), roughness: 0.9 }));

// ============================================================================ BirdCard

export class BirdCard {
  /**
   * @param {import('./cardFace.js').Bird|null} bird  null for an anonymous face-down card
   * @param {{faceUp?: boolean}} [opts]
   */
  constructor(bird = null, { faceUp = false } = {}) {
    this.object3d = new THREE.Group();
    this.object3d.name = 'bird-card';
    this._faceMat = new THREE.MeshStandardMaterial({ map: getBlankMat().map, roughness: 0.9 });
    this._slab = roundedSlab(CARD_W, CARD_H, CARD_R, CARD_T, this._faceMat, getBackMat(), edgeMat);
    this.object3d.add(this._slab);
    this._faceUp = faceUp;
    this.object3d.quaternion.copy(faceUp ? FACE_UP : FACE_DOWN);
    this._slab.position.y = faceUp ? 0 : -CARD_T;   // keep the card resting on y=0 either way
    this.bird = null;
    if (bird) this.setBird(bird);
  }

  /** Change which bird this card shows. Resolves when the face has been drawn. */
  async setBird(bird) {
    this.bird = bird;
    this.object3d.userData.pick = { type: 'card', bird };
    const canvas = await drawCardFace(bird);
    if (this.bird !== bird) return;   // superseded
    const tex = new THREE.CanvasTexture(canvas);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.anisotropy = 8;
    this._faceMat.map?.userData?.ownedByCard && this._faceMat.map.dispose();
    tex.userData.ownedByCard = true;
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
   * @returns {Promise<BirdCard>}
   */
  async moveTo(parent, position, { faceUp = this._faceUp, rotationY = 0, ...opts } = {}) {
    this._faceUp = faceUp;
    const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), rotationY).multiply(faceUp ? FACE_UP : FACE_DOWN);
    this._slab.position.y = faceUp ? 0 : -CARD_T;
    await fly(this.object3d, parent, position, q, opts);
    return this;
  }

  dispose() {
    if (this._faceMat.map?.userData?.ownedByCard) this._faceMat.map.dispose();
    this._faceMat.dispose();
    this.object3d.parent?.remove(this.object3d);
  }
}

// ============================================================================ CardDeck

/** A face-down draw pile. Its height follows `count`. */
export class CardDeck {
  constructor({ count = 40, cardThickness = 0.01 } = {}) {
    this.object3d = new THREE.Group();
    this.object3d.name = 'card-deck';
    this.object3d.userData.pick = { type: 'deck' };
    this._t = cardThickness;

    const side = sideStripes();
    this._sideMat = new THREE.MeshStandardMaterial({ map: side, roughness: 0.95 });
    this._stack = roundedSlab(CARD_W, CARD_H, CARD_R, 1, getBackMat(), getBackMat(), this._sideMat);
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
    this.object3d.visible = this._count > 0;
  }

  /** Local position of the top of the pile. */
  get top() { return new THREE.Vector3(0, this._count * this._t, 0); }

  /**
   * Take the top card (count - 1) and fly it to a destination.
   * @param {object} bird   what the card is (null to keep it anonymous)
   * @param {THREE.Object3D} parent  where it goes
   * @param {THREE.Vector3} position local position in parent
   * @param {{faceUp?:boolean, animate?:boolean, duration?:number, arc?:number, rotationY?:number}} [opts]
   * @returns {Promise<BirdCard>}
   */
  async draw(bird, parent, position, opts = {}) {
    const card = new BirdCard(bird, { faceUp: false });
    this.object3d.add(card.object3d);
    card.object3d.position.copy(this.top);
    this.count = this._count - 1;
    await card.moveTo(parent, position, { faceUp: true, arc: 1.6, duration: 0.8, ...opts });
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
