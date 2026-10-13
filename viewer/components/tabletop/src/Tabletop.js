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
   * @param {boolean} [o.shadows=true]
   * @param {object} [o.views]               named camera views, see setView()
   */
  constructor(o) {
    super();
    this.options = { size: [46, 32], shadows: true, ...o };
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
    sun.shadow.mapSize.set(4096, 4096);
    Object.assign(sun.shadow.camera, { left: -28, right: 28, top: 22, bottom: -22, near: 1, far: 90 });
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
      renderer.render(scene, this.camera);
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  /**
   * Put a component on the table.
   * @param {{object3d:THREE.Object3D, update?:(dt:number)=>void}} component
   * @param {{position?:number[], rotationY?:number, scale?:number}} [place]
   */
  add(component, place = {}) {
    const o = component.object3d;
    if (place.position) o.position.set(...place.position);
    if (place.rotationY) o.rotation.y = place.rotationY;
    if (place.scale) o.scale.setScalar(place.scale);
    this.scene.add(o);
    this.components.push(component);
    if (component.update) this._updaters.push(dt => component.update(dt));
    return component;
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
   */
  setView(name, { animate = true, duration = 0.9 } = {}) {
    const v = this.views[name];
    if (!v) throw new Error(`[Tabletop] unknown view "${name}"`);
    const to = { p: new THREE.Vector3(...v.position), t: new THREE.Vector3(...v.target) };
    if (!animate) {
      this.camera.position.copy(to.p);
      this.controls.target.copy(to.t);
      this.controls.update();
      this._camAnim = null;
      return;
    }
    this._camAnim = { from: { p: this.camera.position.clone(), t: this.controls.target.clone() }, to, k: 0, duration };
  }

  _stepCamera(dt) {
    const a = this._camAnim;
    a.k = Math.min(1, a.k + dt / a.duration);
    const e = a.k < 0.5 ? 2 * a.k * a.k : 1 - Math.pow(-2 * a.k + 2, 2) / 2;
    this.camera.position.lerpVectors(a.from.p, a.to.p, e);
    this.controls.target.lerpVectors(a.from.t, a.to.t, e);
    if (a.k >= 1) this._camAnim = null;
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
    const cloth = new THREE.Mesh(
      // subdivided: one huge triangle pair loses depth precision up close and can draw over the boards
      new THREE.PlaneGeometry(w, d, Math.ceil(w), Math.ceil(d)),
      new THREE.MeshStandardMaterial({ map: tex, roughness: 1, color: 0xffffff }),
    );
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
