// Tabletop — the shared 3D scene every game component sits in.
//
//   const table = new Tabletop({ container: document.getElementById('table') });
//   table.add(mat, { position: [0, 0, 4] });
//   table.add(feeder, { position: [13, 0, -3], scale: 0.55 });
//
// A "component" is anything with an `object3d` (THREE.Object3D) and optionally
// `update(dt)`. Tabletop owns the renderer, camera, lights, table surface and the
// render loop, and advances the shared `tweens`.
//
// Coordinates: the table top is y = 0, +y up, +z toward the default camera.
// Card-sized units: a bird card is 1.5 x 2.17.

import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { tweens } from './tween.js';

export class Tabletop extends EventTarget {
  /**
   * @param {object} o
   * @param {HTMLElement} o.container       element to render into (fills it)
   * @param {number} [o.size=[46, 32]]       table surface width/depth
   * @param {'rect'|'round'} [o.shape='rect'] round: a circular table, size[0] across
   * @param {boolean} [o.shadows=true]
   * @param {number} [o.shadowMapSize=4096]  smaller is cheaper and softer
   * @param {object} [o.views]               named camera views, see setView()
   */
  constructor(o) {
    super();
    this.options = { size: [46, 32], shadows: true, shadowMapSize: 4096, ...o };
    /** Speed of animated camera moves (2 = twice as fast). */
    this.cameraSpeed = 1;
    const container = (this.container = o.container);
    this.components = [];
    this._updaters = [];

    const renderer = (this.renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true }));
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = this.options.shadows;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:none';
    container.appendChild(renderer.domElement);

    const scene = (this.scene = new THREE.Scene());
    this.camera = new THREE.PerspectiveCamera(32, 1, 0.5, 300);

    scene.add(new THREE.HemisphereLight(0xfffbf0, 0x6c6a58, 1.6));
    const sun = new THREE.DirectionalLight(0xfff3e0, 1.8);
    sun.position.set(14, 30, 16);
    sun.castShadow = this.options.shadows;
    sun.shadow.mapSize.set(this.options.shadowMapSize, this.options.shadowMapSize);
    // the shadow camera covers the whole table surface, whatever its size
    const [tw, td] = this.options.size;
    const sx = Math.max(28, tw / 2 + 4), sz = Math.max(22, td / 2 + 4);
    Object.assign(sun.shadow.camera, { left: -sx, right: sx, top: sz, bottom: -sz, near: 1, far: 60 + Math.max(tw, td) });
    sun.shadow.bias = -0.0004;
    sun.shadow.normalBias = 0.02;
    scene.add(sun);
    this.sun = sun;

    this._buildSurface();

    const controls = (this.controls = new OrbitControls(this.camera, renderer.domElement));
    controls.enableDamping = true;
    controls.minDistance = 4;
    controls.maxDistance = 90;
    controls.maxPolarAngle = Math.PI * 0.47;
    controls.screenSpacePanning = false;

    this.views = {
      overview: { position: [0, 34, 30], target: [0, 0, 0.5] },
      ...(this.options.views || {}),
    };
    this.setView('overview', { animate: false });

    this._initPicking();

    const resize = () => {
      const w = container.clientWidth || 1, h = container.clientHeight || 1;
      renderer.setSize(w, h, false);
      this.camera.aspect = w / h;
      // keep the whole table in frame on narrow screens
      this.camera.fov = w / h < 1 ? 32 / Math.max(0.55, w / h) : 32;
      this.camera.updateProjectionMatrix();
    };
    this._ro = new ResizeObserver(resize);
    this._ro.observe(container);
    resize();

    const clock = new THREE.Clock();
    const loop = () => {
      const dt = Math.min(clock.getDelta(), 1 / 20);
      this.update(dt);
      controls.update();
      this._fitNearPlane();
      renderer.render(scene, this.camera);
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  /**
   * Put a component on the table.
   * @param {{object3d:THREE.Object3D, update?:(dt:number)=>void}} component
   * @param {{position?:number[], rotationY?:number, scale?:number, parent?:THREE.Object3D}} [place]
   *   parent: put it inside another object (e.g. a LazySusan's `top`) instead of the scene
   */
  add(component, place = {}) {
    const o = component.object3d;
    if (place.position) o.position.set(...place.position);
    if (place.rotationY) o.rotation.y = place.rotationY;
    if (place.scale) o.scale.setScalar(place.scale);
    (place.parent || this.scene).add(o);
    this.components.push(component);
    if (component.update) this._updaters.push(dt => component.update(dt));
    return component;
  }

  // Keep the near plane as far out as the view allows. Card faces sit a hair above their
  // bodies, and from across a big table a close near plane leaves too little depth
  // precision to keep them apart.
  _fitNearPlane() {
    const d = this.camera.position.distanceTo(this.controls.target);
    const near = Math.min(10, Math.max(0.5, d * 0.06));
    if (Math.abs(near - this.camera.near) > 0.05 * this.camera.near) {
      this.camera.near = near;
      this.camera.updateProjectionMatrix();
    }
  }

  /** Run a function every frame with dt in seconds. */
  onUpdate(fn) { this._updaters.push(fn); }

  update(dt) {
    tweens.update(dt);
    for (const fn of this._updaters) fn(dt);
    if (this._camAnim) this._stepCamera(dt);
  }

  /**
   * Move the camera to a named view, e.g. 'overview' or one you registered:
   *   table.views.mat = { position: [0, 14, 16], target: [0, 0, 4] };
   * or straight to a view object { position, target }.
   * @param {string|{position:number[], target:number[]}} view
   * @param {{animate?:boolean, duration?:number, orbit?:boolean}} [opts]
   *   orbit: swing around the table's centre (the y axis) instead of moving in a straight
   *   line, so going to the far side of the table doesn't fly through it
   * @returns {Promise<void>} resolves when the camera has arrived
   */
  setView(view, { animate = true, duration = 0.9, orbit = false } = {}) {
    const v = typeof view === 'string' ? this.views[view] : view;
    if (!v) throw new Error(`[Tabletop] unknown view "${view}"`);
    const to = { p: new THREE.Vector3(...v.position), t: new THREE.Vector3(...v.target) };
    this._camAnim?.resolve();
    this._camAnim = null;
    if (!animate) {
      this.camera.position.copy(to.p);
      this.controls.target.copy(to.t);
      this.controls.update();
      return Promise.resolve();
    }
    return new Promise(resolve => {
      this._camAnim = { from: { p: this.camera.position.clone(), t: this.controls.target.clone() }, to, k: 0, duration, orbit, resolve };
    });
  }

  /** Jump a camera move in progress to its end. */
  finishCamera() {
    const a = this._camAnim;
    if (!a) return;
    this.camera.position.copy(a.to.p);
    this.controls.target.copy(a.to.t);
    this._camAnim = null;
    a.resolve();
  }

  _stepCamera(dt) {
    const a = this._camAnim;
    a.k = Math.min(1, a.k + (dt * this.cameraSpeed) / a.duration);
    const e = a.k < 0.5 ? 2 * a.k * a.k : 1 - Math.pow(-2 * a.k + 2, 2) / 2;
    if (a.orbit) {
      orbitLerp(this.camera.position, a.from.p, a.to.p, e);
      orbitLerp(this.controls.target, a.from.t, a.to.t, e);
    } else {
      this.camera.position.lerpVectors(a.from.p, a.to.p, e);
      this.controls.target.lerpVectors(a.from.t, a.to.t, e);
    }
    if (a.k >= 1) { this._camAnim = null; a.resolve(); }
  }

  _buildSurface() {
    // A soft linen cloth, generated so it tiles without visible seams.
    const c = document.createElement('canvas');
    c.width = c.height = 512;
    const g = c.getContext('2d');
    g.fillStyle = '#d9d6c6';
    g.fillRect(0, 0, 512, 512);
    let seed = 7;
    const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
    for (let i = 0; i < 9000; i++) {
      const horizontal = i % 2 === 0;
      const p = Math.floor(rnd() * 512), q = Math.floor(rnd() * 512), len = 8 + rnd() * 40;
      g.fillStyle = `rgba(${rnd() < 0.5 ? '255,255,250' : '120,112,96'},${0.05 + rnd() * 0.07})`;
      if (horizontal) { g.fillRect(q, p, len, 1); g.fillRect(q - 512, p, len, 1); }
      else { g.fillRect(p, q, 1, len); g.fillRect(p, q - 512, 1, len); }
    }
    const tex = new THREE.CanvasTexture(c);
    tex.colorSpace = THREE.SRGBColorSpace;
    tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
    const [w, d] = this.options.size;
    tex.repeat.set(w / 6, d / 6);
    tex.anisotropy = 8;
    // subdivided: one huge triangle pair loses depth precision up close and can draw over the boards
    const geo = this.options.shape === 'round'
      ? new THREE.RingGeometry(0.0001, w / 2, 128, Math.ceil(w / 2))
      : new THREE.PlaneGeometry(w, d, Math.ceil(w), Math.ceil(d));
    const cloth = new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ map: tex, roughness: 1, color: 0xffffff }));
    cloth.rotation.x = -Math.PI / 2;
    cloth.receiveShadow = true;
    cloth.name = 'table-surface';
    this.scene.add(cloth);
    this.surface = cloth;
  }

  // Clicking anything with `userData.pick` set (on itself or an ancestor) emits a 'pick' event
  // whose detail is that pick data plus the object, e.g. { type: 'card', habitat, slot, object }.
  _initPicking() {
    const ray = new THREE.Raycaster(), ptr = new THREE.Vector2(), dom = this.renderer.domElement;
    let downAt = null;
    const down = e => { downAt = [e.clientX, e.clientY]; };
    const up = e => {
      if (!downAt) return;
      const moved = Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]);
      downAt = null;
      if (moved > 6) return;
      const r = dom.getBoundingClientRect();
      ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ptr, this.camera);
      for (const hit of ray.intersectObjects(this.scene.children, true)) {
        let o = hit.object;
        while (o && !o.userData.pick) o = o.parent;
        if (o && o.visible) {
          this.dispatchEvent(new CustomEvent('pick', { detail: { ...o.userData.pick, object: o, point: hit.point } }));
          return;
        }
      }
    };
    dom.addEventListener('pointerdown', down);
    dom.addEventListener('pointerup', up);
    this._unpick = () => { dom.removeEventListener('pointerdown', down); dom.removeEventListener('pointerup', up); };
  }

  dispose() {
    cancelAnimationFrame(this._raf);
    this._ro.disconnect();
    this._unpick();
    this.controls.dispose();
    for (const c of this.components) c.dispose?.();
    this.renderer.dispose();
    this.renderer.domElement.remove();
  }
}

// Interpolate around the y axis: angle, distance from the axis and height each move evenly.
function orbitLerp(out, from, to, k) {
  const r0 = Math.hypot(from.x, from.z), r1 = Math.hypot(to.x, to.z);
  // a point on the axis has no angle of its own: borrow the other end's
  const a1 = r1 > 1e-6 ? Math.atan2(to.x, to.z) : Math.atan2(from.x, from.z);
  const a0 = r0 > 1e-6 ? Math.atan2(from.x, from.z) : a1;
  let da = a1 - a0;
  da = ((da + Math.PI) % (Math.PI * 2) + Math.PI * 2) % (Math.PI * 2) - Math.PI;   // shortest way round
  const a = a0 + da * k, r = r0 + (r1 - r0) * k;
  out.set(Math.sin(a) * r, from.y + (to.y - from.y) * k, Math.cos(a) * r);
}
