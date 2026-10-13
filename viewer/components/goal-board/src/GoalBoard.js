// GoalBoard — the round-end goals grid (blue side), the goal tile for each round,
// and player cubes placed on its squares or numbered medallions.
//
// What the squares vs the medallions mean is up to your rules; the board only
// knows positions:  placeCube(round, { square: 0..5 })  or  placeCube(round, { medallion: 1..5 }).

import * as THREE from 'three';
import { loadTexture } from '../../tabletop/src/assets.js';
import { roundedSlab } from '../../tabletop/src/geometry.js';
import { tweens, fly } from '../../tabletop/src/tween.js';
import { createCube, createMarker, CUBE_SIZE } from '../../pieces/src/pieces.js';
import { drawGoalTile } from './goalTile.js';
import { BOARD_IMAGE, ROUNDS, SQUARES, MEDALLIONS, squareUV, medallionUV, rowUV } from './layout.js';
import { GOALS } from './goals.js';

const BOARD_URL = new URL('../assets/board.jpg', import.meta.url).href;

export const BOARD_W = 12;
export const BOARD_H = BOARD_W * (BOARD_IMAGE[1] / BOARD_IMAGE[0]);
const BOARD_T = 0.06;
const TILE = 0.95, TILE_T = 0.05;

const edgeMat = new THREE.MeshStandardMaterial({ color: 0xe8e2d4, roughness: 1 });
const tileMats = {};
const ACTIVE_LIFT = 0.16;   // how far the current round's tile is raised

// Material for a goal: its tile art if it has some, otherwise a tile drawn from its label.
function tileMaterial(goal) {
  if (tileMats[goal.key]) return tileMats[goal.key];
  const mat = new THREE.MeshStandardMaterial({ roughness: 0.9 });
  if (goal.image) mat.map = loadTexture(goal.image);
  else {
    mat.color.set(0xf4ecdb);
    drawGoalTile(goal).then(canvas => {
      const tex = new THREE.CanvasTexture(canvas);
      tex.colorSpace = THREE.SRGBColorSpace;
      tex.anisotropy = 8;
      mat.map = tex; mat.color.set(0xffffff); mat.needsUpdate = true;
    });
  }
  return (tileMats[goal.key] = mat);
}

// several cubes on one spot sit side by side
const SPREAD = [[0, 0], [-0.17, -0.17], [0.17, 0.17], [0.17, -0.17], [-0.17, 0.17]];

export class GoalBoard {
  constructor() {
    this.object3d = new THREE.Group();
    this.object3d.name = 'goal-board';
    const top = new THREE.MeshStandardMaterial({ map: loadTexture(BOARD_URL), roughness: 0.95 });
    this.object3d.add(roundedSlab(BOARD_W, BOARD_H, 0.12, BOARD_T, top, edgeMat, edgeMat));
    this._goals = new Array(ROUNDS).fill(null);    // { key, goal, mesh }
    this._cubes = [];                              // { round, square?, medallion?, color, mesh }
    this._markers = new Array(ROUNDS).fill(null);  // { medallion, color, mesh }
    this._active = null;                           // round whose tile is raised
  }

  /** Local position of a square (round 1..4, i 0..5) on the board surface. */
  squarePosition(round, i) { return this._pos(squareUV(round, i)); }

  /** Local position of a numbered medallion (round 1..4, n 1..5). */
  medallionPosition(round, n) { return this._pos(medallionUV(round, n)); }

  /** Where round N's goal tile sits (left of the board). */
  goalPosition(round) {
    const p = this._pos(rowUV(round));
    p.x -= TILE / 2 + 0.25;
    p.y = 0;
    return p;
  }

  /**
   * Show a goal tile for a round. `goal` is a GOALS key (see goals.js), or your own
   * { key, label, tint?, image? }: with no image the tile is drawn from the label
   * (symbols in brackets allowed, e.g. "[egg] in bowl nests"). null removes it.
   * Animated tiles drop in from above.
   */
  async setGoal(round, goal, { animate = true } = {}) {
    this._check(round);
    const old = this._goals[round - 1];
    if (old) old.mesh.parent?.remove(old.mesh);
    this._goals[round - 1] = null;
    if (!goal) return;
    if (typeof goal === 'string') {
      if (!GOALS[goal]) throw new Error(`[GoalBoard] unknown goal "${goal}". Known: ${Object.keys(GOALS).join(', ')}`);
      goal = { key: goal, ...GOALS[goal] };
    }
    const mesh = roundedSlab(TILE, TILE, 0.06, TILE_T, tileMaterial(goal), edgeMat, edgeMat);
    mesh.name = `goal-${goal.key}`;
    mesh.userData.pick = { type: 'goal', round, goal: goal.key, label: goal.label };
    this.object3d.add(mesh);
    this._goals[round - 1] = { key: goal.key, goal, mesh };
    const at = this.goalPosition(round);
    if (round === this._active) at.y += ACTIVE_LIFT;
    if (!animate) { mesh.position.copy(at); return; }
    mesh.position.copy(at).add(new THREE.Vector3(0, 2, 0));
    await tweens.to(mesh, { position: at }, { duration: 0.5, ease: 'out' });
  }

  /** Raise one round's goal tile to show it is the current round (null lowers them all). */
  async setActiveRound(round, { animate = true } = {}) {
    this._active = round ?? null;
    await Promise.all(this._goals.map((g, i) => {
      if (!g) return null;
      const at = this.goalPosition(i + 1);
      if (i + 1 === this._active) at.y += ACTIVE_LIFT;
      if (!animate) { g.mesh.position.copy(at); return null; }
      return tweens.to(g.mesh, { position: at }, { duration: 0.35 });
    }));
  }

  /**
   * Put a ring marker around a round's medallion (1..5), or remove it with null.
   * One marker per round; setting it again moves it.
   * @param {{color?:string, animate?:boolean}} [opts] color: 'gold' | 'green' | 'red' | any colour
   */
  async setMarker(round, medallion, { color = 'gold', animate = true } = {}) {
    this._check(round);
    const old = this._markers[round - 1];
    if (old && old.medallion === medallion && old.color === color) return;
    if (old) old.mesh.parent?.remove(old.mesh);
    this._markers[round - 1] = null;
    if (medallion == null) return;
    const at = this.medallionPosition(round, medallion);
    const mesh = createMarker(color);
    mesh.userData.pick = { type: 'goal-marker', round, medallion, color };
    this.object3d.add(mesh);
    this._markers[round - 1] = { medallion, color, mesh };
    if (!animate) { mesh.position.copy(at); return; }
    // a marker that only changes colour or slides along the row starts where the old one was
    if (old) { mesh.position.copy(old.mesh.position); await tweens.to(mesh, { position: at }, { duration: 0.4 }); }
    else { mesh.position.copy(at).add(new THREE.Vector3(0, 1.5, 0)); await tweens.to(mesh, { position: at }, { duration: 0.45, ease: 'out' }); }
  }

  /**
   * Place a player cube.
   * @param {number} round 1..4
   * @param {{square?:number, medallion?:number}} where
   * @param {string} color  PLAYER_COLORS key or any colour
   * @param {{from?:THREE.Vector3, animate?:boolean}} [opts] from = world point it flies from (else drops in)
   */
  async placeCube(round, where, color, { from = null, animate = true } = {}) {
    this._check(round);
    const base = this._spot(round, where);
    const sameSpot = this._cubes.filter(c => c.round === round && c.square === where.square && c.medallion === where.medallion);
    const [dx, dz] = SPREAD[sameSpot.length % SPREAD.length];
    const at = base.clone().add(new THREE.Vector3(dx, Math.floor(sameSpot.length / SPREAD.length) * CUBE_SIZE, dz));
    const mesh = createCube(color);
    mesh.userData.pick = { type: 'goal-cube', round, ...where, color };
    this._cubes.push({ round, square: where.square, medallion: where.medallion, color, mesh });
    if (from) {
      let root = this.object3d; while (root.parent) root = root.parent;
      root.add(mesh); mesh.position.copy(from);
      await fly(mesh, this.object3d, at, undefined, { animate, duration: 0.7, arc: 1.5 });
    } else {
      this.object3d.add(mesh);
      if (!animate) { mesh.position.copy(at); return mesh; }
      mesh.position.copy(at).add(new THREE.Vector3(0, 1.5, 0));
      await tweens.to(mesh, { position: at }, { duration: 0.45, ease: 'out' });
    }
    return mesh;
  }

  /** Remove cubes matching a filter, e.g. { round: 2 } or { round: 2, color: 'red' }. */
  removeCubes(filter = {}) {
    this._cubes = this._cubes.filter(c => {
      const hit = Object.entries(filter).every(([k, v]) => c[k] === v);
      if (hit) c.mesh.parent?.remove(c.mesh);
      return !hit;
    });
  }

  /**
   * Make the board show this, instantly:
   * { goals: ['wetland_total', { key: 'g7', label: '[egg] in bowl nests' }, null, null],
   *   cubes: [{ round: 1, medallion: 4, color: 'red' }, { round: 1, square: 0, color: 'blue' }],
   *   markers: [{ round: 1, medallion: 2, color: 'gold' }],
   *   active: 1 }
   */
  setState({ goals = [], cubes = [], markers = [], active = null } = {}) {
    this._active = active;
    for (let r = 1; r <= ROUNDS; r++) {
      const g = goals[r - 1] || null;
      const key = typeof g === 'string' ? g : g?.key ?? null;
      const cur = this._goals[r - 1];
      if ((cur?.key ?? null) !== key) this.setGoal(r, g, { animate: false });
      else if (cur) {
        const at = this.goalPosition(r);
        if (r === active) at.y += ACTIVE_LIFT;
        cur.mesh.position.copy(at);
      }
    }
    const want = cubes.map(c => ({ round: c.round, square: c.square, medallion: c.medallion, color: c.color }));
    const have = this._cubes.map(c => ({ round: c.round, square: c.square, medallion: c.medallion, color: c.color }));
    if (JSON.stringify(want) !== JSON.stringify(have)) {
      this.removeCubes();
      for (const c of cubes) {
        const where = c.square != null ? { square: c.square } : { medallion: c.medallion };
        this.placeCube(c.round, where, c.color, { animate: false });
      }
    }
    for (let r = 1; r <= ROUNDS; r++) {
      const m = markers.find(x => x.round === r);
      this.setMarker(r, m ? m.medallion : null, { color: m?.color, animate: false });
    }
  }

  getState() {
    return {
      goals: this._goals.map(g => (g ? (GOALS[g.key] ? g.key : g.goal) : null)),
      cubes: this._cubes.map(({ round, square, medallion, color }) => ({ round, color, ...(square != null ? { square } : { medallion }) })),
      markers: this._markers.map((m, i) => (m ? { round: i + 1, medallion: m.medallion, color: m.color } : null)).filter(Boolean),
      active: this._active,
    };
  }

  _pos([u, v]) { return new THREE.Vector3((u - 0.5) * BOARD_W, BOARD_T, (v - 0.5) * BOARD_H); }

  _spot(round, where) {
    if (where.square != null) {
      if (where.square < 0 || where.square >= SQUARES) throw new Error(`[GoalBoard] square ${where.square} out of range 0..${SQUARES - 1}`);
      return this.squarePosition(round, where.square);
    }
    if (where.medallion != null) {
      if (where.medallion < 1 || where.medallion > MEDALLIONS) throw new Error(`[GoalBoard] medallion ${where.medallion} out of range 1..${MEDALLIONS}`);
      return this.medallionPosition(round, where.medallion);
    }
    throw new Error('[GoalBoard] placeCube needs { square } or { medallion }');
  }

  _check(round) {
    if (!(round >= 1 && round <= ROUNDS)) throw new Error(`[GoalBoard] round ${round} out of range 1..${ROUNDS}`);
  }
}
