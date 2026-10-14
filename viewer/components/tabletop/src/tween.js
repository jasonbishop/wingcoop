// Minimal tween engine for moving game pieces.
//
// All components share the `tweens` singleton. Tabletop advances it every frame;
// if you run your own loop, call `tweens.update(dt)` yourself.
//
//   await tweens.to(obj, { position, quaternion, scale }, { duration: 0.6, arc: 1.5 })
//   await fly(card, mat.object3d, slotPosition, slotQuaternion)   // reparents across components
//   tweens.speed = 4        // fast-forward everything
//   tweens.finishAll()      // jump every running tween to its end (for skip/scrub)

import * as THREE from 'three';

const ease = {
  linear: t => t,
  inOut: t => (t < 0.5 ? 2 * t * t : 1 - Math.pow(-2 * t + 2, 2) / 2),
  out: t => 1 - Math.pow(1 - t, 3),
  outBack: t => { const c = 1.4; return 1 + (c + 1) * Math.pow(t - 1, 3) + c * Math.pow(t - 1, 2); },
};

class Tweens {
  constructor() {
    this.active = new Set();
    /** Global playback speed for every tween (2 = twice as fast). */
    this.speed = 1;
  }

  /**
   * Animate an object's local transform.
   * @param {THREE.Object3D} obj
   * @param {{position?:THREE.Vector3, quaternion?:THREE.Quaternion, scale?:THREE.Vector3|number}} to
   * @param {{duration?:number, delay?:number, arc?:number, ease?:'linear'|'inOut'|'out'|'outBack', onUpdate?:Function}} opts
   *   arc: height of a parabolic hop added to y along the way (0 = straight line)
   */
  to(obj, to, opts = {}) {
    const t = {
      obj,
      p0: obj.position.clone(), p1: to.position ? to.position.clone() : null,
      q0: obj.quaternion.clone(), q1: to.quaternion ? to.quaternion.clone() : null,
      s0: obj.scale.clone(),
      s1: to.scale == null ? null : (typeof to.scale === 'number' ? new THREE.Vector3().setScalar(to.scale) : to.scale.clone()),
      duration: Math.max(1e-4, opts.duration ?? 0.6),
      delay: opts.delay ?? 0,
      arc: opts.arc ?? 0,
      ease: ease[opts.ease || 'inOut'],
      onUpdate: opts.onUpdate,
      elapsed: 0,
    };
    const promise = new Promise(resolve => { t.resolve = resolve; });
    this.active.add(t);
    return promise;
  }

  /** Wait for `seconds` of tween time (respects speed and finishAll). */
  wait(seconds) {
    return this.to(new THREE.Object3D(), {}, { duration: seconds });
  }

  update(dt) {
    for (const t of this.active) {
      t.elapsed += dt * this.speed;
      const raw = (t.elapsed - t.delay) / t.duration;
      if (raw < 0) continue;
      this._apply(t, Math.min(1, raw));
      if (raw >= 1) { this.active.delete(t); t.resolve(); }
    }
  }

  /** Jump all running tweens to their end state and resolve them. */
  finishAll() {
    // Resolving can start new tweens (await chains); loop until nothing is left.
    for (let guard = 0; this.active.size && guard < 1000; guard++) {
      const t = this.active.values().next().value;
      this._apply(t, 1);
      this.active.delete(t);
      t.resolve();
    }
  }

  get busy() { return this.active.size > 0; }

  _apply(t, k) {
    const e = t.ease(k);
    const o = t.obj;
    if (t.p1) {
      o.position.lerpVectors(t.p0, t.p1, e);
      if (t.arc) o.position.y += Math.sin(Math.PI * e) * t.arc;
    }
    if (t.q1) o.quaternion.slerpQuaternions(t.q0, t.q1, e);
    if (t.s1) o.scale.lerpVectors(t.s0, t.s1, e);
    t.onUpdate?.(k);
  }
}

export const tweens = new Tweens();

const _v = new THREE.Vector3(), _q = new THREE.Quaternion(), _s = new THREE.Vector3();

function rootOf(obj) {
  let r = obj;
  while (r.parent) r = r.parent;
  return r;
}

/**
 * Fly an object to a new parent (e.g. from the deck to a mat slot, or from the feeder to a supply),
 * animating in world space and reparenting at the end.
 * @param {THREE.Object3D} obj
 * @param {THREE.Object3D} parent      destination parent
 * @param {THREE.Vector3} position     destination position in parent's local space
 * @param {THREE.Quaternion} [quaternion] destination rotation in parent's local space (default identity)
 * @param {object} [opts]  duration, arc (default 1.2), delay, ease; animate:false to snap
 */
export async function fly(obj, parent, position, quaternion = new THREE.Quaternion(), opts = {}) {
  const root = rootOf(parent);
  if (obj.parent && rootOf(obj) === root) root.attach(obj);
  else root.add(obj);

  parent.updateWorldMatrix(true, false);
  const worldPos = parent.localToWorld(position.clone());
  parent.getWorldQuaternion(_q);
  const worldQuat = _q.clone().multiply(quaternion);
  parent.getWorldScale(_s);
  const worldScale = _s.clone();

  if (opts.animate !== false) {
    await tweens.to(obj, { position: worldPos, quaternion: worldQuat, scale: worldScale },
      { duration: opts.duration ?? 0.7, arc: opts.arc ?? 1.2, delay: opts.delay, ease: opts.ease });
  }
  parent.add(obj);
  obj.position.copy(position);
  obj.quaternion.copy(quaternion);
  obj.scale.set(1, 1, 1);
  return obj;
}

/** World position of a point given in an object's local space (handy as a fly() start point). */
export function worldPoint(obj, local = new THREE.Vector3()) {
  obj.updateWorldMatrix(true, false);
  return obj.localToWorld(_v.copy(local)).clone();
}
