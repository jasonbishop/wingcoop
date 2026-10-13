// Shared texture / image loading with caching and a "everything loaded" promise.
import * as THREE from 'three';

const textureCache = new Map();
const imageCache = new Map();
let pending = 0;
let waiters = [];

function start() { pending++; }
function done() {
  pending--;
  if (pending === 0) { const w = waiters; waiters = []; w.forEach(r => r()); }
}

/** Resolves once every texture/image requested so far has loaded (or failed). */
export function assetsReady() {
  return pending === 0 ? Promise.resolve() : new Promise(r => waiters.push(r));
}

const loader = new THREE.TextureLoader();

/**
 * Load (once) and configure a colour texture.
 * @param {string} url
 * @param {{rotation?:number, repeat?:[number,number], anisotropy?:number}} [opts]
 *   Options make a separate clone so the same image can be used differently.
 */
export function loadTexture(url, opts = {}) {
  const key = url + JSON.stringify(opts);
  if (textureCache.has(key)) return textureCache.get(key);
  start();
  const t = loader.load(url, () => done(), undefined, () => { console.warn('[tabletop] could not load', url); done(); });
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = opts.anisotropy ?? 8;
  if (opts.rotation) { t.center.set(0.5, 0.5); t.rotation = opts.rotation; }
  if (opts.repeat) { t.wrapS = t.wrapT = THREE.RepeatWrapping; t.repeat.set(...opts.repeat); }
  textureCache.set(key, t);
  return t;
}

/** Load (once) an HTMLImageElement, e.g. for drawing on a canvas. */
export function loadImage(url) {
  if (imageCache.has(url)) return imageCache.get(url);
  start();
  const p = new Promise(resolve => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onload = () => { done(); resolve(img); };
    img.onerror = () => { console.warn('[tabletop] could not load', url); done(); resolve(null); };
    img.src = url;
  });
  imageCache.set(url, p);
  return p;
}
