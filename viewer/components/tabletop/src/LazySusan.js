// LazySusan — a turntable in the middle of the table. Put shared components on its
// `top` and turn it to face whoever is being watched:
//
//   const susan = table.add(new LazySusan({ radius: 10 }));
//   table.add(board, { parent: susan.top, position: [0, 0, 4] });
//   await susan.turnTo(Math.PI / 2);
//
// Angle 0 leaves the things on it as you placed them; a positive angle turns it
// anticlockwise seen from above (the same sense as Object3D.rotation.y).

import * as THREE from 'three';
import { tweens } from './tween.js';

export class LazySusan {
  /** @param {{radius?:number, height?:number}} [o] */
  constructor({ radius = 10, height = 0.22 } = {}) {
    this.radius = radius;
    this.height = height;
    this.object3d = new THREE.Group();
    this.object3d.name = 'lazy-susan';

    const wood = woodTexture();
    const topMat = new THREE.MeshStandardMaterial({ map: wood, roughness: 0.7 });
    const edgeMat = new THREE.MeshStandardMaterial({ color: 0x8a6843, roughness: 0.8 });
    const disc = new THREE.Mesh(new THREE.CylinderGeometry(radius, radius, height, 96), [edgeMat, topMat, edgeMat]);
    disc.position.y = height / 2;
    disc.castShadow = disc.receiveShadow = true;
    disc.name = 'lazy-susan-disc';
    this.object3d.add(disc);

    /** Parent for whatever rides on the turntable; its y = 0 is the disc's surface. */
    this.top = new THREE.Group();
    this.top.name = 'lazy-susan-top';
    this.top.position.y = height;
    this.object3d.add(this.top);
    this._angle = 0;
  }

  get angle() { return this._angle; }

  /** Turn to an angle in radians, the shortest way round. */
  async turnTo(angle, { animate = true, duration = 0.9 } = {}) {
    this._angle = angle;
    const q = new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0, 1, 0), angle);
    if (animate) await tweens.to(this.object3d, { quaternion: q }, { duration });
    if (this._angle === angle) this.object3d.quaternion.copy(q);
  }

  setState({ angle = 0 } = {}) { this.turnTo(angle, { animate: false }); }
  getState() { return { angle: this._angle }; }
}

// Turned wood: faint concentric rings with a little grain, drawn once.
function woodTexture() {
  const S = 1024;
  const c = document.createElement('canvas');
  c.width = c.height = S;
  const g = c.getContext('2d');
  g.fillStyle = '#b08a5c';
  g.fillRect(0, 0, S, S);
  let seed = 11;
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  for (let r = 6; r < S * 0.72; r += 3 + rnd() * 7) {
    g.strokeStyle = `rgba(${rnd() < 0.5 ? '70,48,24' : '236,208,160'},${0.05 + rnd() * 0.1})`;
    g.lineWidth = 1 + rnd() * 3;
    g.beginPath(); g.ellipse(S / 2 + (rnd() - 0.5) * 6, S / 2 + (rnd() - 0.5) * 6, r, r * (0.985 + rnd() * 0.03), 0, 0, Math.PI * 2); g.stroke();
  }
  for (let i = 0; i < 1400; i++) {
    g.fillStyle = `rgba(60,40,20,${0.03 + rnd() * 0.05})`;
    g.fillRect(rnd() * S, rnd() * S, 1 + rnd() * 2, 6 + rnd() * 30);
  }
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 8;
  return t;
}
