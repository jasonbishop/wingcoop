// Plaque — a small flat name plate with text drawn at runtime, e.g. a player's name by their mat.
//
//   const plate = new Plaque({ width: 3.4, height: 0.95 });
//   plate.setText({ title: 'Player 1', subtitle: 'greedy bot', color: '#4f7fae' });

import * as THREE from 'three';
import { roundedSlab } from './geometry.js';

const edgeMat = new THREE.MeshStandardMaterial({ color: 0xd8cbb0, roughness: 1 });
const FONT_DISPLAY = '"Alegreya SC", "Palatino Linotype", Palatino, Georgia, serif';
const FONT_BODY = '"Alegreya Sans", "Gill Sans", "Trebuchet MS", sans-serif';

export class Plaque {
  /** @param {{width?:number, height?:number, thickness?:number}} [o] */
  constructor({ width = 3.4, height = 0.95, thickness = 0.05 } = {}) {
    this.width = width; this.height = height;
    this.canvas = document.createElement('canvas');
    this.canvas.width = 768; this.canvas.height = Math.round(768 * height / width);
    this.texture = new THREE.CanvasTexture(this.canvas);
    this.texture.colorSpace = THREE.SRGBColorSpace;
    this.texture.anisotropy = 8;
    this._mat = new THREE.MeshStandardMaterial({ map: this.texture, roughness: 0.9 });
    this.object3d = roundedSlab(width, height, 0.1, thickness, this._mat, edgeMat, edgeMat);
    this.object3d.name = 'plaque';
    this._text = {};
    this.setText({});
  }

  /**
   * @param {{title?:string, subtitle?:string, color?:string, highlight?:boolean}} text
   *   color: a stripe down the left edge; highlight: a brighter plate (e.g. whose turn it is)
   */
  async setText(text) {
    this._text = { ...this._text, ...text };
    const t = this._text;
    const key = JSON.stringify(t);
    if (key === this._drawn) return;
    this._drawn = key;
    if (document.fonts) {
      await Promise.race([document.fonts.load(`700 80px ${FONT_DISPLAY}`), new Promise(r => setTimeout(r, 2000))]).catch(() => {});
      if (this._drawn !== key) return;
    }
    const g = this.canvas.getContext('2d');
    const { width: W, height: H } = this.canvas;
    g.fillStyle = t.highlight ? '#fbf3d6' : '#efe6d2';
    g.fillRect(0, 0, W, H);
    if (t.highlight) { g.strokeStyle = '#c9972e'; g.lineWidth = 14; g.strokeRect(7, 7, W - 14, H - 14); }
    const pad = t.color ? 70 : 34;
    if (t.color) { g.fillStyle = t.color; g.fillRect(0, 0, 44, H); }
    g.fillStyle = '#2b2620'; g.textAlign = 'left'; g.textBaseline = 'middle';
    let size = Math.round(H * 0.44);
    g.font = `700 ${size}px ${FONT_DISPLAY}`;
    while (g.measureText(t.title || '').width > W - pad - 24 && size > 24) { size -= 2; g.font = `700 ${size}px ${FONT_DISPLAY}`; }
    g.fillText(t.title || '', pad, t.subtitle ? H * 0.34 : H * 0.52);
    if (t.subtitle) {
      let s2 = Math.round(H * 0.27);
      g.font = `500 ${s2}px ${FONT_BODY}`;
      while (g.measureText(t.subtitle).width > W - pad - 24 && s2 > 16) { s2 -= 2; g.font = `500 ${s2}px ${FONT_BODY}`; }
      g.fillStyle = 'rgba(43,38,32,0.78)';
      g.fillText(t.subtitle, pad, H * 0.74);
    }
    this.texture.needsUpdate = true;
  }

  dispose() {
    this.texture.dispose();
    this._mat.dispose();
    this.object3d.parent?.remove(this.object3d);
  }
}
