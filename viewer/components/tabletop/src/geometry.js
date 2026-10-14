// Shared geometry helpers.
import * as THREE from 'three';

// Geometries are shared: every card, tile and tab of one size uses the same buffers,
// so never dispose a geometry that came from this file.
const cache = new Map();
function shared(key, make) {
  if (!cache.has(key)) cache.set(key, make());
  return cache.get(key);
}

/** A rounded-rectangle Shape centred on the origin. */
export function roundedRectShape(w, h, r) {
  const s = new THREE.Shape();
  const x = -w / 2, y = -h / 2;
  s.moveTo(x + r, y);
  s.lineTo(x + w - r, y); s.quadraticCurveTo(x + w, y, x + w, y + r);
  s.lineTo(x + w, y + h - r); s.quadraticCurveTo(x + w, y + h, x + w - r, y + h);
  s.lineTo(x + r, y + h); s.quadraticCurveTo(x, y + h, x, y + h - r);
  s.lineTo(x, y + r); s.quadraticCurveTo(x, y, x + r, y);
  return s;
}

/**
 * A flat rounded-rectangle face lying in the XZ plane, facing +Y (or -Y with down=true),
 * with UVs covering the bounding box so an image maps onto it edge to edge.
 * Image "up" points toward -Z (away from a camera looking from +Z).
 */
export function roundedFaceGeometry(w, h, r, { down = false } = {}) {
  return shared(`face:${w}:${h}:${r}:${down}`, () => buildFace(w, h, r, down));
}

function buildFace(w, h, r, down) {
  const g = new THREE.ShapeGeometry(roundedRectShape(w, h, r), 6);
  const pos = g.attributes.position, uv = g.attributes.uv;
  for (let i = 0; i < pos.count; i++) {
    uv.setXY(i, (pos.getX(i) + w / 2) / w, (pos.getY(i) + h / 2) / h);
  }
  // shape is in XY facing +Z; lay it face up (image top toward -Z)
  g.rotateX(-Math.PI / 2);
  // face down: turn it over about the long (Z) axis, so the image reads correctly
  // once the piece itself is flipped over the same way
  if (down) g.rotateZ(Math.PI);
  g.computeVertexNormals();
  return g;
}

/**
 * A rounded slab (tile, card body) of thickness t sitting on y=0, with separate
 * top and bottom image faces and a plain edge.
 * Returns a Group: children[0] = edge body, [1] = top face, [2] = bottom face.
 */
export function roundedSlab(w, h, r, t, topMat, bottomMat, edgeMat) {
  const group = new THREE.Group();
  const body = new THREE.Mesh(
    shared(`body:${w}:${h}:${r}:${t}`, () => new THREE.ExtrudeGeometry(roundedRectShape(w, h, r), { depth: t, bevelEnabled: false, curveSegments: 6 })),
    edgeMat,
  );
  body.rotation.x = -Math.PI / 2;
  const top = new THREE.Mesh(roundedFaceGeometry(w, h, r), topMat);
  top.position.y = t + 0.0015;
  const bottom = new THREE.Mesh(roundedFaceGeometry(w, h, r, { down: true }), bottomMat || edgeMat);
  bottom.position.y = -0.0015;
  for (const m of [body, top, bottom]) { m.castShadow = true; m.receiveShadow = true; group.add(m); }
  return group;
}
