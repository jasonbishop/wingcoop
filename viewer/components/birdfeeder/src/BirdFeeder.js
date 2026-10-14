// BirdFeeder — a 3D birdhouse dice tower with physics food dice.
//
// Two ways to use it:
//
//   Standalone: it creates its own renderer, camera, lights and render loop inside a DOM element.
//     const feeder = new BirdFeeder({ container: document.getElementById('feeder') });
//
//   Embedded: you own the renderer and scene; the feeder is just a Group you add and update.
//     const feeder = new BirdFeeder({ scene, camera, domElement: renderer.domElement });
//     // in your loop:  feeder.update(dt);  renderer.render(scene, camera);
//
// Rolls are simulated ahead of time and then played back, which makes them
// riggable (`roll(['fish','seed',…])` always lands on exactly those faces),
// skippable (`skip()`), speed-adjustable, and repeatable with a seeded `random`.
// See README.md for the full API.

import * as THREE from 'three';
import * as CANNON from 'cannon-es';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { FACE_KEYS, FACES, isFaceKey } from './faces.js';
import { DEFAULT_TEXTURES } from './textures.js';

// ---------------------------------------------------------------------------
// Geometry. Units: one die is 1 unit wide. Origin: centre of the tower's base.
// +z points out of the dice opening toward the tray, +y is up.
// ---------------------------------------------------------------------------
export const DIMENSIONS = Object.freeze({
  towerWidth: 5.4, towerDepth: 5.4, wall: 0.3,
  eave: 10, ridge: 12.4,              // wall height at the eaves and at the roof peak
  openingWidth: 4.2, openingHeight: 3.8,
  trayDepth: 6.4, trayWidth: 5.8, trayRim: 1.0, trayFloor: 0.25,
  die: 1.0,
});
const W = DIMENSIONS.towerWidth, D = DIMENSIONS.towerDepth, T = DIMENSIONS.wall;
const EAVE = DIMENSIONS.eave, RIDGE = DIMENSIONS.ridge;
const OPEN_W = DIMENSIONS.openingWidth, OPEN_H = DIMENSIONS.openingHeight;
const TRAY_D = DIMENSIONS.trayDepth, TRAY_W = DIMENSIONS.trayWidth, RIM_H = DIMENSIONS.trayRim, FLOOR_H = DIMENSIONS.trayFloor;
const DIE = DIMENSIONS.die;
const TRAY_Z0 = D / 2 - 0.05, TRAY_ZC = TRAY_Z0 + TRAY_D / 2;

// The painted perch hole on front.jpg sits at 41.3% down the texture (see assets/manifest.json).
const PERCH_Y = RIDGE * (1 - 0.413);

// Internal baffles as [zStart, yStart, zEnd, yEnd]. Gaps and vertical clearances are tuned so
// two dice can't wedge between baffles; re-test rolls if you change these.
const RAMPS = [
  [D / 2 - T, 9.6, 0.0, 8.5],             // top: slopes to the back
  [-D / 2 + T, 6.0, 0.4, 4.8],            // middle: slopes to the front
  [-D / 2 + T, 2.4, D / 2 + 0.25, 0.3],   // bottom: out through the opening into the tray
];

// Resting spots in the tray for setDice() (x, z), in order.
const TRAY_SPOTS = [
  [-1.2, 4.2], [0.6, 3.9], [1.9, 5.0], [-0.3, 5.6], [-1.9, 5.9], [1.0, 6.7], [-1.0, 7.3], [2.0, 7.6],
];

// Roll timeline (seconds of playback)
const ROOF_OPEN = 0.35, SPAWN_START = 0.38, SPAWN_GAP = 0.14, ROOF_CLOSE_AFTER = 0.65, ROOF_CLOSE = 0.4;
const SIM_HZ = 120, FRAME_HZ = 60, MAX_ROLL_SECONDS = 16;

// Face slots in BoxGeometry order: +x, -x, +y, -y, +z, -z
const SLOT_NORMALS = [
  new THREE.Vector3(1, 0, 0), new THREE.Vector3(-1, 0, 0), new THREE.Vector3(0, 1, 0),
  new THREE.Vector3(0, -1, 0), new THREE.Vector3(0, 0, 1), new THREE.Vector3(0, 0, -1),
];
const SLOT_UP = 2;

const smooth = x => { const t = Math.min(1, Math.max(0, x)); return t * t * (3 - 2 * t); };

export class BirdFeeder extends EventTarget {
  /**
   * @param {object} options
   * @param {HTMLElement} [options.container]  Standalone mode: render into this element.
   * @param {THREE.Scene} [options.scene]       Embedded mode: add the feeder to this scene.
   * @param {THREE.Camera} [options.camera]     Embedded mode: needed for clicking dice.
   * @param {HTMLElement} [options.domElement]  Embedded mode: element that receives clicks.
   * @param {number}  [options.diceCount=5]     Dice dropped by roll() when no faces are given.
   * @param {boolean} [options.clickToTake=true] Clicking a resting die takes it. Set false for replays.
   * @param {number}  [options.speed=1]         Default playback speed for rolls.
   * @param {boolean} [options.shadows=true]
   * @param {boolean} [options.controls=true]   Standalone mode: orbit controls.
   * @param {object}  [options.textures]        Override any key of DEFAULT_TEXTURES with your own URL.
   */
  constructor(options = {}) {
    super();
    this.options = { diceCount: 5, clickToTake: true, speed: 1, shadows: true, controls: true, ...options };
    const o = this.options;

    /** The whole feeder. Move, rotate or scale this to place it in your scene. */
    this.object3d = new THREE.Group();
    this.object3d.name = 'BirdFeeder';

    this._dice = [];
    this._playback = null;
    this._xray = false;
    this._roofLift = 0;
    this._disposables = [];
    this._listeners = [];

    if (o.container) this._initStandalone(o.container);
    else if (o.scene) o.scene.add(this.object3d);
    this._camera = this._camera || o.camera || null;
    this._dom = this._dom || o.domElement || null;

    const manager = new THREE.LoadingManager();
    /** Resolves when all textures have loaded (or failed — missing art renders untextured). */
    this.ready = new Promise(resolve => {
      manager.onLoad = resolve;
      manager.onError = url => console.warn('[BirdFeeder] could not load', url);
    });
    this._buildMaterials(manager);
    this._buildPhysics();
    this._buildHouse();
    this._dieGeo = new RoundedBoxGeometry(DIE, DIE, DIE, 4, 0.11);
    this._disposables.push(this._dieGeo);
    this._initPicking();
  }

  // ===================================================================== public API

  /**
   * Drop dice through the tower.
   *   roll()                                   5 random dice
   *   roll(['fish','seed','seed'])             rigged: 3 dice that land on exactly these faces
   *   roll({ faces, count, speed, random })    random: () => number in [0,1), e.g. seededRandom(42)
   * A roll already in progress is finished instantly first.
   * @returns {Promise<Array<{index:number, face:string, taken:boolean}>>} the dice once they settle
   */
  roll(arg = {}) {
    const opts = Array.isArray(arg) ? { faces: arg } : arg;
    const faces = opts.faces || null;
    if (faces) {
      const bad = faces.filter(f => !isFaceKey(f));
      if (bad.length) throw new Error(`[BirdFeeder] unknown face(s): ${bad.join(', ')}. Use one of: ${FACE_KEYS.join(', ')}`);
    }
    const count = faces ? faces.length : (opts.count ?? this.options.diceCount);
    if (this._playback) this.skip();
    this._clearDice();
    if (count === 0) return Promise.resolve([]);

    const rec = this._simulate(count, opts.random || Math.random);
    this._dice = rec.final.map((pose, i) => {
      const top = topSlot(pose.quaternion);
      const layout = FACE_KEYS.slice();
      if (faces) swapInto(layout, faces[i], top);
      const die = this._makeDie(i, layout);
      die.face = layout[top];
      die.mesh.visible = false;
      return die;
    });

    let resolve;
    const promise = new Promise(r => { resolve = r; });
    this._playback = { rec, t: 0, speed: opts.speed ?? this.options.speed, resolve };
    this._emit('rollstart', { count, rigged: !!faces });
    return promise;
  }

  /** Jump the current roll to its end (dice appear settled in the tray). No-op if not rolling. */
  skip() {
    if (this._playback) this._finishPlayback();
  }

  /** True while a roll is playing. */
  get rolling() { return !!this._playback; }

  /**
   * Place dice straight into the tray, no animation — for scrubbing a replay to any point.
   * @param {string[]} faces  e.g. ['fish','rodent']; [] empties the feeder
   */
  setDice(faces) {
    const bad = faces.filter(f => !isFaceKey(f));
    if (bad.length) throw new Error(`[BirdFeeder] unknown face(s): ${bad.join(', ')}`);
    if (this._playback) this._cancelPlayback();
    this._clearDice();
    this._dice = faces.map((face, i) => {
      const layout = FACE_KEYS.slice();
      swapInto(layout, face, SLOT_UP);
      const die = this._makeDie(i, layout);
      die.face = face;
      const [x, z] = trayspot(i);
      die.mesh.position.set(x, FLOOR_H + DIE / 2, z);
      die.mesh.quaternion.setFromAxisAngle(new THREE.Vector3(0, 1, 0), ((i * 1.7 + 0.3) % 1.2) - 0.6);
      return die;
    });
    this._roofLift = 0;
    this._applyRoof();
    return this.getDice();
  }

  /**
   * Remove a die from the tray with a short lift-and-vanish animation.
   * @returns {string|null} the face it showed, or null if there is no such die
   */
  take(index) {
    const d = this._dice[index];
    if (!d || d.taken || this._playback) return null;
    d.taken = true;
    d.takeT = 0;
    this._emit('take', { index, face: d.face });
    return d.face;
  }

  /** World-space position of a die, e.g. as the start point for a food token flying to a player. */
  dieWorldPosition(index) {
    const d = this._dice[index];
    if (!d) return null;
    d.mesh.updateWorldMatrix(true, false);
    return d.mesh.getWorldPosition(new THREE.Vector3());
  }

  /** Remove all dice. */
  clear() {
    if (this._playback) this._cancelPlayback();
    this._clearDice();
  }

  /** Current dice, including taken ones (taken: true). */
  getDice() {
    return this._dice.map(d => ({ index: d.index, face: d.face, taken: d.taken }));
  }

  /** Hide the right-hand wall so the baffles and falling dice are visible. */
  setXray(on) {
    this._xray = !!on;
    this._sideR.visible = !this._xray;
  }
  get xray() { return this._xray; }

  /** Standalone mode: move the camera back to its starting view. */
  resetCamera() {
    if (!this._controls) return;
    const narrow = this._container.clientWidth / Math.max(1, this._container.clientHeight) < 0.8;
    this._camera.position.set(18, 13.5, 24.5).multiplyScalar(narrow ? 1.4 : 1);
    this._controls.target.set(0, 5.2, 2.8);
    this._controls.update();
  }

  /**
   * Advance animations by dt seconds. Called automatically in standalone mode;
   * call it from your own loop in embedded mode.
   */
  update(dt) {
    dt = Math.min(dt, 1 / 20);
    if (this._playback) this._stepPlayback(dt);
    for (const d of this._dice) {
      if (!d.taken || !d.mesh.visible) continue;
      d.takeT += dt * 3;
      d.mesh.position.y += dt * 9;
      d.mesh.scale.setScalar(Math.max(0.001, 1 - d.takeT));
      if (d.takeT >= 1) d.mesh.visible = false;
    }
  }

  /** Free GPU resources, stop the render loop and remove listeners. */
  dispose() {
    cancelAnimationFrame(this._raf);
    this._resizeObserver?.disconnect();
    for (const [el, type, fn] of this._listeners) el.removeEventListener(type, fn);
    this._clearDice();
    this.object3d.parent?.remove(this.object3d);
    for (const x of this._disposables) x.dispose?.();
    this._controls?.dispose();
    if (this._renderer) {
      this._renderer.dispose();
      this._renderer.domElement.remove();
    }
  }

  // Standalone-mode handles, for anyone who needs to reach in.
  get renderer() { return this._renderer || null; }
  get scene() { return this._scene || this.options.scene || null; }
  get camera() { return this._camera; }
  get controls() { return this._controls || null; }

  // ===================================================================== setup

  _initStandalone(container) {
    this._container = container;
    const renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    renderer.outputColorSpace = THREE.SRGBColorSpace;
    renderer.shadowMap.enabled = this.options.shadows;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    renderer.setClearColor(0x000000, 0);
    renderer.domElement.style.cssText = 'display:block;width:100%;height:100%;touch-action:none';
    container.appendChild(renderer.domElement);
    this._renderer = renderer;
    this._dom = renderer.domElement;

    const scene = new THREE.Scene();
    scene.add(this.object3d);
    this._scene = scene;
    this._camera = new THREE.PerspectiveCamera(34, 1, 0.1, 200);

    scene.add(new THREE.HemisphereLight(0xfffbf0, 0x6c6a58, 1.55));
    const sun = new THREE.DirectionalLight(0xfff3e0, 1.9);
    sun.position.set(9, 18, 12);
    sun.castShadow = this.options.shadows;
    sun.shadow.mapSize.set(2048, 2048);
    Object.assign(sun.shadow.camera, { left: -13, right: 13, top: 13, bottom: -13, near: 1, far: 60 });
    sun.shadow.bias = -0.0006;
    sun.shadow.normalBias = 0.03;
    scene.add(sun);

    const groundGeo = new THREE.PlaneGeometry(200, 200);
    const groundMat = new THREE.ShadowMaterial({ opacity: 0.22 });
    const ground = new THREE.Mesh(groundGeo, groundMat);
    ground.rotation.x = -Math.PI / 2;
    ground.receiveShadow = true;
    scene.add(ground);
    this._disposables.push(groundGeo, groundMat);

    if (this.options.controls) {
      const c = new OrbitControls(this._camera, renderer.domElement);
      c.enableDamping = true;
      c.minDistance = 9;
      c.maxDistance = 55;
      c.maxPolarAngle = Math.PI * 0.48;
      c.enablePan = false;
      this._controls = c;
    }

    const resize = () => {
      const w = container.clientWidth || 1, h = container.clientHeight || 1;
      renderer.setSize(w, h, false);
      this._camera.aspect = w / h;
      this._camera.updateProjectionMatrix();
    };
    this._resizeObserver = new ResizeObserver(resize);
    this._resizeObserver.observe(container);
    resize();
    if (this._controls) this.resetCamera();
    else { this._camera.position.set(18, 13.5, 24.5); this._camera.lookAt(0, 5.2, 2.8); }

    const clock = new THREE.Clock();
    const loop = () => {
      this.update(clock.getDelta());
      this._controls?.update();
      renderer.render(scene, this._camera);
      this._raf = requestAnimationFrame(loop);
    };
    this._raf = requestAnimationFrame(loop);
  }

  _buildMaterials(manager) {
    const urls = { ...DEFAULT_TEXTURES, ...(this.options.textures || {}) };
    const loader = new THREE.TextureLoader(manager);
    const aniso = this._renderer ? this._renderer.capabilities.getMaxAnisotropy() : 8;
    const tex = (key, rot = 0) => {
      const t = loader.load(urls[key]);
      t.colorSpace = THREE.SRGBColorSpace;
      t.anisotropy = aniso;
      if (rot) { t.center.set(0.5, 0.5); t.rotation = rot; }
      this._disposables.push(t);
      return t;
    };
    const mat = (map, extra = {}) => {
      const m = new THREE.MeshStandardMaterial({ map, roughness: 0.92, metalness: 0, ...extra });
      this._disposables.push(m);
      return m;
    };
    this._edgeMat = new THREE.MeshStandardMaterial({ color: 0x5c5446, roughness: 1 });
    this._disposables.push(this._edgeMat);
    this._mats = {
      front: mat(tex('front')),
      back: mat(tex('back')),
      sideA: mat(tex('sideA')),
      sideB: mat(tex('sideB')),
      roofA: mat(tex('roofA', Math.PI / 2)),
      roofB: mat(tex('roofB', -Math.PI / 2)),
      cap: mat(tex('cap', Math.PI / 2)),
      trayFloor: mat(tex('trayFloor')),
      rim: mat(tex('trayRim')),
      ramp: mat(tex('back', Math.PI / 2)),
    };
    this._dieMats = {};
    for (const k of FACE_KEYS) this._dieMats[k] = mat(tex(`die_${k}`), { roughness: 0.75 });
  }

  _buildPhysics() {
    const world = new CANNON.World({ gravity: new CANNON.Vec3(0, -42, 0) });
    world.broadphase = new CANNON.SAPBroadphase(world);
    world.solver.iterations = 14;
    const wood = new CANNON.Material('wood');
    const ramp = new CANNON.Material('ramp');
    const tray = new CANNON.Material('tray');
    const die = new CANNON.Material('die');
    // Ramps are frictionless on purpose: cannon-es scales friction with the number of contact
    // points, so a die lying flat on a sloped box can lock in place even at low friction.
    world.addContactMaterial(new CANNON.ContactMaterial(wood, die, { friction: 0.22, restitution: 0.28 }));
    world.addContactMaterial(new CANNON.ContactMaterial(die, die, { friction: 0.18, restitution: 0.3 }));
    world.addContactMaterial(new CANNON.ContactMaterial(ramp, die, { friction: 0, restitution: 0.25 }));
    world.addContactMaterial(new CANNON.ContactMaterial(tray, die, { friction: 0.13, restitution: 0.3 }));
    this._world = world;
    this._phys = { wood, ramp, tray, die };

    const ground = new CANNON.Body({ mass: 0, material: wood, shape: new CANNON.Plane() });
    ground.quaternion.setFromEuler(-Math.PI / 2, 0, 0);
    world.addBody(ground);
  }

  _staticBox(sx, sy, sz, pos, rotX = 0, material = this._phys.wood) {
    const b = new CANNON.Body({ mass: 0, material });
    b.addShape(new CANNON.Box(new CANNON.Vec3(sx / 2, sy / 2, sz / 2)));
    b.position.set(pos.x, pos.y, pos.z);
    if (rotX) b.quaternion.setFromEuler(rotX, 0, 0);
    this._world.addBody(b);
    return b;
  }

  _buildHouse() {
    const M = this._mats, edge = this._edgeMat, root = this.object3d;
    const geos = [];
    const add = (geo, material, parent = root) => {
      if (!geos.includes(geo)) geos.push(geo);
      const m = new THREE.Mesh(geo, material);
      m.castShadow = true;
      m.receiveShadow = true;
      parent.add(m);
      return m;
    };

    // Gable walls: extruded pentagons; the painted panel maps onto the wall's bounding box.
    const panelUV = {
      generateTopUV: (g, v, a, b, c) => [a, b, c].map(i => new THREE.Vector2((v[i * 3] + W / 2) / W, v[i * 3 + 1] / RIDGE)),
      generateSideWallUV: (g, v, a, b, c, d) => [a, b, c, d].map(i => new THREE.Vector2((v[i * 3] + W / 2) / W, v[i * 3 + 1] / RIDGE)),
    };
    const gable = withOpening => {
      const s = new THREE.Shape();
      s.moveTo(-W / 2, 0);
      if (withOpening) {
        s.lineTo(-OPEN_W / 2, 0); s.lineTo(-OPEN_W / 2, OPEN_H);
        s.lineTo(OPEN_W / 2, OPEN_H); s.lineTo(OPEN_W / 2, 0);
      }
      s.lineTo(W / 2, 0); s.lineTo(W / 2, EAVE); s.lineTo(0, RIDGE); s.lineTo(-W / 2, EAVE); s.closePath();
      return new THREE.ExtrudeGeometry(s, { depth: T, bevelEnabled: false, UVGenerator: panelUV });
    };
    add(gable(true), [M.front, edge]).position.z = D / 2 - T;
    add(gable(false), [M.back, edge]).position.z = -D / 2;

    const sideGeo = new THREE.BoxGeometry(T, EAVE, D - 2 * T);
    add(sideGeo, [M.sideA, M.sideA, edge, edge, edge, edge]).position.set(-W / 2 + T / 2, EAVE / 2, 0);
    this._sideR = add(sideGeo, [M.sideB, M.sideB, edge, edge, edge, edge]);
    this._sideR.position.set(W / 2 - T / 2, EAVE / 2, 0);

    const perch = add(new THREE.CylinderGeometry(0.09, 0.09, 0.8, 12), edge);
    perch.rotation.x = Math.PI / 2;
    perch.position.set(0, PERCH_Y, D / 2 + 0.38);

    // Roof: two boards per slope (roofA/roofB swapped per side so the moss doesn't repeat)
    // plus a folded ridge cap. Lifted as one group during a roll.
    const roof = new THREE.Group();
    root.add(roof);
    this._roof = roof;
    const slopeAngle = Math.atan2(RIDGE - EAVE, W / 2);
    const slopeLen = Math.hypot(RIDGE - EAVE, W / 2) + 0.75;
    const ROOF_D = D + 1.1, BOARD_T = 0.22;
    const boardGeo = new THREE.BoxGeometry(slopeLen, BOARD_T, ROOF_D / 2);
    [[1, M.roofA, M.roofB], [-1, M.roofB, M.roofA]].forEach(([side, m1, m2]) => {
      const pivot = new THREE.Group();
      pivot.position.set(0, RIDGE + BOARD_T * 0.55, 0.15);
      pivot.rotation.z = -side * slopeAngle;
      roof.add(pivot);
      [[m1, ROOF_D / 4], [m2, -ROOF_D / 4]].forEach(([m, z]) => {
        add(boardGeo, [edge, edge, m, m, edge, edge], pivot).position.set(side * slopeLen / 2, 0, z);
      });
    });
    const capGeo = new THREE.BoxGeometry(0.62, 0.13, ROOF_D + 0.12);
    [1, -1].forEach(side => {
      const pivot = new THREE.Group();
      pivot.position.set(0, RIDGE + BOARD_T * 0.55 + BOARD_T / 2 + 0.06, 0.15);
      pivot.rotation.z = -side * slopeAngle;
      roof.add(pivot);
      add(capGeo, [edge, edge, M.cap, edge, edge, edge], pivot).position.x = side * 0.27;
    });

    // Tray
    const trayFloor = add(new THREE.BoxGeometry(TRAY_W, FLOOR_H, TRAY_D), [edge, edge, M.trayFloor, edge, edge, edge]);
    trayFloor.position.set(0, FLOOR_H / 2, TRAY_ZC);
    const rimSideGeo = new THREE.BoxGeometry(T, RIM_H, TRAY_D);
    [-1, 1].forEach(s => add(rimSideGeo, M.rim).position.set(s * (TRAY_W / 2 + T / 2), RIM_H / 2, TRAY_ZC));
    add(new THREE.BoxGeometry(TRAY_W + 2 * T, RIM_H, T), M.rim).position.set(0, RIM_H / 2, TRAY_Z0 + TRAY_D + T / 2);

    // Baffles (visible in x-ray mode and through the opening) + their colliders
    const innerW = W - 2 * T;
    for (const [z1, y1, z2, y2] of RAMPS) {
      const len = Math.hypot(z2 - z1, y2 - y1);
      const ang = Math.atan2(y2 - y1, z2 - z1);
      const m = add(new THREE.BoxGeometry(innerW, 0.2, len), [edge, edge, M.ramp, M.ramp, edge, edge]);
      m.position.set(0, (y1 + y2) / 2, (z1 + z2) / 2);
      m.rotation.x = -ang;
      this._staticBox(innerW, 0.2, len, m.position, -ang, this._phys.ramp);
    }

    // Shell colliders. Walls run 4 units above the roof so dice can't hop out while it is lifted;
    // tray walls are taller than the visible rim for the same reason.
    const WALL_H = RIDGE + 4;
    this._staticBox(W, WALL_H, T, { x: 0, y: WALL_H / 2, z: -D / 2 + T / 2 });
    this._staticBox(T, WALL_H, D, { x: -W / 2 + T / 2, y: WALL_H / 2, z: 0 });
    this._staticBox(T, WALL_H, D, { x: W / 2 - T / 2, y: WALL_H / 2, z: 0 });
    this._staticBox(W, WALL_H - OPEN_H, T, { x: 0, y: (WALL_H + OPEN_H) / 2, z: D / 2 - T / 2 });
    const jambW = (W - OPEN_W) / 2;
    [-1, 1].forEach(s => this._staticBox(jambW, OPEN_H, T, { x: s * (W / 2 - jambW / 2), y: OPEN_H / 2, z: D / 2 - T / 2 }));
    this._staticBox(TRAY_W, FLOOR_H, TRAY_D, trayFloor.position, 0, this._phys.tray);
    [-1, 1].forEach(s => this._staticBox(T, 3, TRAY_D, { x: s * (TRAY_W / 2 + T / 2), y: 1.5, z: TRAY_ZC }));
    this._staticBox(TRAY_W + 2 * T, 3, T, { x: 0, y: 1.5, z: TRAY_Z0 + TRAY_D + T / 2 });

    this._disposables.push(...geos);
  }

  _initPicking() {
    if (!this._dom || !this._camera) return;
    const ray = new THREE.Raycaster(), ptr = new THREE.Vector2();
    let downAt = null;
    const down = e => { downAt = [e.clientX, e.clientY]; };
    const up = e => {
      if (!downAt) return;
      const moved = Math.hypot(e.clientX - downAt[0], e.clientY - downAt[1]);
      downAt = null;
      if (moved > 6 || this._playback) return;   // a drag is a camera move, not a click
      const r = this._dom.getBoundingClientRect();
      ptr.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      ray.setFromCamera(ptr, this._camera);
      const live = this._dice.filter(d => !d.taken);
      const hit = ray.intersectObjects(live.map(d => d.mesh))[0];
      if (!hit) return;
      const d = live.find(x => x.mesh === hit.object);
      this._emit('pick', { index: d.index, face: d.face });
      if (this.options.clickToTake) this.take(d.index);
    };
    this._dom.addEventListener('pointerdown', down);
    this._dom.addEventListener('pointerup', up);
    this._listeners.push([this._dom, 'pointerdown', down], [this._dom, 'pointerup', up]);
  }

  // ===================================================================== dice

  _makeDie(index, layout) {
    const mesh = new THREE.Mesh(this._dieGeo, layout.map(k => this._dieMats[k]));
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    mesh.name = `die-${index}`;
    this.object3d.add(mesh);
    return { index, mesh, layout, face: null, taken: false, takeT: 0 };
  }

  _clearDice() {
    for (const d of this._dice) this.object3d.remove(d.mesh);
    this._dice = [];
  }

  // Run the whole roll in the physics world up front and record every frame.
  _simulate(count, rnd) {
    const world = this._world;
    const bodies = new Array(count).fill(null);
    const state = Array.from({ length: count }, () => ({ still: 0, exited: false }));
    const spawnAt = i => SPAWN_START + i * SPAWN_GAP;
    const frames = [];
    const fdt = 1 / FRAME_HZ, steps = SIM_HZ / FRAME_HZ;
    const inTray = p => p.z >= D / 2 - 0.6 && p.y < 2.4;
    let t = 0, settle = 0;

    for (;;) {
      for (let i = 0; i < count; i++) {
        if (bodies[i] || t < spawnAt(i)) continue;
        const b = new CANNON.Body({ mass: 1, material: this._phys.die, shape: new CANNON.Box(new CANNON.Vec3(DIE / 2, DIE / 2, DIE / 2)) });
        b.linearDamping = 0.05;
        b.angularDamping = 0.08;
        b.position.set((rnd() - 0.5) * 2.8, 11.1 + rnd(), 0.5 + rnd() * 1.4);
        b.quaternion.setFromEuler(rnd() * 6.28, rnd() * 6.28, rnd() * 6.28);
        b.angularVelocity.set((rnd() - 0.5) * 12, (rnd() - 0.5) * 12, (rnd() - 0.5) * 12);
        b.velocity.set((rnd() - 0.5) * 2, -2, (rnd() - 0.5) * 2);
        world.addBody(b);
        bodies[i] = b;
      }
      for (let s = 0; s < steps; s++) world.step(1 / SIM_HZ);
      t += fdt;

      const spawned = bodies.every(Boolean);
      bodies.forEach((b, i) => {
        if (!b) return;
        const p = b.position, st = state[i];
        st.still = b.velocity.length() < 0.35 ? st.still + fdt : 0;
        // carry speed out of the opening so dice spread across the tray instead of piling at the mouth
        if (!st.exited && p.z > D / 2 - 0.2) {
          st.exited = true;
          const v = b.velocity;
          v.set(v.x + (rnd() - 0.5) * 6, Math.max(v.y, 1.5), Math.max(v.z, 6 + rnd() * 3));
        }
        // a die that stalls inside the tower gets nudged downhill (top baffle slopes back, others forward)
        if (p.z < D / 2 - 0.6 && st.still > 0.5) {
          b.velocity.set((rnd() - 0.5) * 2, 2.5, (p.y > 7.4 ? -1 : 1) * 5);
          st.still = 0;
        }
      });

      const frame = new Float32Array(count * 7).fill(NaN);
      bodies.forEach((b, i) => {
        if (!b) return;
        frame.set([b.position.x, b.position.y, b.position.z, b.quaternion.x, b.quaternion.y, b.quaternion.z, b.quaternion.w], i * 7);
      });
      frames.push(frame);

      const calm = spawned && bodies.every(b => inTray(b.position) && b.velocity.length() < 0.2 && b.angularVelocity.length() < 0.4);
      settle = calm ? settle + fdt : 0;
      if ((spawned && settle > 0.5) || t > MAX_ROLL_SECONDS) break;
    }

    // Safety net: if a die never made it out (very rare), set it down in a free tray spot.
    const last = frames[frames.length - 1];
    let spot = count;
    bodies.forEach((b, i) => {
      if (inTray(b.position)) return;
      const [x, z] = trayspot(spot++);
      b.position.set(x, FLOOR_H + DIE / 2, z);
      b.quaternion.set(0, 0, 0, 1);
      last.set([x, FLOOR_H + DIE / 2, z, 0, 0, 0, 1], i * 7);
    });

    const final = bodies.map(b => ({
      position: new THREE.Vector3(b.position.x, b.position.y, b.position.z),
      quaternion: new THREE.Quaternion(b.quaternion.x, b.quaternion.y, b.quaternion.z, b.quaternion.w),
    }));
    bodies.forEach(b => world.removeBody(b));
    return { frames, count, final, duration: frames.length / FRAME_HZ, closeAt: spawnAt(count - 1) + ROOF_CLOSE_AFTER };
  }

  _stepPlayback(dt) {
    const pb = this._playback;
    pb.t += dt * pb.speed;
    const { frames, count } = pb.rec;
    if (pb.t >= pb.rec.duration) { this._finishPlayback(); return; }

    const f = pb.t * FRAME_HZ;
    const i0 = Math.min(Math.floor(f), frames.length - 1), i1 = Math.min(i0 + 1, frames.length - 1);
    const a = f - i0, A = frames[i0], B = frames[i1];
    const qa = new THREE.Quaternion(), qb = new THREE.Quaternion();
    for (let k = 0; k < count; k++) {
      const o = k * 7, mesh = this._dice[k].mesh;
      if (Number.isNaN(A[o])) { mesh.visible = false; continue; }
      mesh.visible = true;
      mesh.position.set(A[o] + (B[o] - A[o]) * a, A[o + 1] + (B[o + 1] - A[o + 1]) * a, A[o + 2] + (B[o + 2] - A[o + 2]) * a);
      qa.set(A[o + 3], A[o + 4], A[o + 5], A[o + 6]);
      qb.set(B[o + 3], B[o + 4], B[o + 5], B[o + 6]);
      mesh.quaternion.slerpQuaternions(qa, qb, a);
    }
    this._roofLift = smooth(pb.t / ROOF_OPEN) * (1 - smooth((pb.t - pb.rec.closeAt) / ROOF_CLOSE));
    this._applyRoof();
  }

  _finishPlayback() {
    const pb = this._playback;
    this._playback = null;
    pb.rec.final.forEach((pose, k) => {
      const mesh = this._dice[k].mesh;
      mesh.visible = true;
      mesh.position.copy(pose.position);
      mesh.quaternion.copy(pose.quaternion);
    });
    this._roofLift = 0;
    this._applyRoof();
    const dice = this.getDice();
    pb.resolve(dice);
    this._emit('settled', { dice });
  }

  _cancelPlayback() {
    const pb = this._playback;
    this._playback = null;
    pb.resolve(this.getDice());
  }

  _applyRoof() {
    const l = this._roofLift;
    this._roof.position.set(-l * 1.2, l * 3.4, -l * 0.6);
    this._roof.rotation.z = l * 0.32;
  }

  _emit(type, detail) {
    this.dispatchEvent(new CustomEvent(type, { detail }));
  }
}

// --------------------------------------------------------------------------- helpers

function topSlot(q) {
  let best = 0, bestY = -2;
  SLOT_NORMALS.forEach((n, i) => {
    const y = n.clone().applyQuaternion(q).y;
    if (y > bestY) { bestY = y; best = i; }
  });
  return best;
}

// Rearrange a die's faces so `face` is in `slot` (swaps with wherever it was; each face stays once per die).
function swapInto(layout, face, slot) {
  const j = layout.indexOf(face);
  [layout[slot], layout[j]] = [layout[j], layout[slot]];
}

function trayspot(i) {
  if (i < TRAY_SPOTS.length) return TRAY_SPOTS[i];
  const k = i - TRAY_SPOTS.length;   // overflow: a loose grid
  return [-2 + (k % 4) * 1.35, 3.6 + Math.floor(k / 4) * 1.3];
}

export { FACE_KEYS, FACES };
