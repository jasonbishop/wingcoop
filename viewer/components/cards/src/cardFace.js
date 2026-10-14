// Draws a bird card face onto a canvas, using the blank card art as the template.
//
// The template's regions (in card_face.jpg pixels, 910 x 1320) are listed in REGIONS.
// If you regenerate card_face.jpg from different art, re-measure these.

import { loadImage } from '../../tabletop/src/assets.js';
import { FOOD_ICONS } from '../../pieces/src/pieces.js';
import { loadSymbols, layoutRich, drawRich, drawSymbol, drawFeather } from './symbols.js';

export const FACE_URL = new URL('../assets/card_face.jpg', import.meta.url).href;
export const FACE_SIZE = [910, 1320];

export const REGIONS = {
  iconBox: [62, 41, 250, 273],    // top-left grey box: habitats + food cost
  title:   [264, 41, 866, 192],   // name bar
  stats:   [52, 290, 230, 1040],  // left column: points, nest + egg limit, wingspan
  art:     [236, 236, 868, 1040], // illustration
  power:   [66, 1074, 848, 1196], // power text bar
  footer:  [180, 1205, 730, 1275],// scientific name
};

export const HABITAT_COLORS = { wetland: '#6f9fcc', forest: '#3d6b45', grassland: '#d4ad3c' };
const POWER_TINTS = { brown: 'rgba(150, 105, 60, 0.30)', pink: 'rgba(205, 120, 140, 0.30)', white: 'rgba(255, 255, 255, 0.35)', none: null };
const INK = '#2b2620';

const FONT_DISPLAY = '"Alegreya SC", "Palatino Linotype", Palatino, Georgia, serif';
const FONT_BODY = '"Alegreya Sans", "Gill Sans", "Trebuchet MS", sans-serif';

let fontsReady = null;
export function waitForFonts() {
  if (!fontsReady) {
    fontsReady = document.fonts
      ? Promise.race([
        Promise.all([
          document.fonts.load(`700 64px ${FONT_DISPLAY}`),
          document.fonts.load(`500 34px ${FONT_BODY}`),
          document.fonts.load(`italic 28px ${FONT_BODY}`),
        ]),
        new Promise(r => setTimeout(r, 2500)),
      ]).catch(() => {})
      : Promise.resolve();
  }
  return fontsReady;
}

/**
 * @typedef {object} Bird
 * @property {string} name
 * @property {string} [scientific]
 * @property {number} [points]
 * @property {string[]} [habitats]       'wetland' | 'forest' | 'grassland'
 * @property {string[]} [food]           e.g. ['fish', 'fish']; food keys from pieces FOODS, or 'wild'
 * @property {boolean} [foodOr]          true = "any one of" instead of "all of"
 * @property {string} [nest]             'bowl' | 'cavity' | 'ground' | 'platform' | 'wild'
 * @property {number} [eggLimit]
 * @property {number} [wingspan]         cm
 * @property {string} [power]            power text
 * @property {'brown'|'pink'|'white'|'none'} [powerColor]
 * @property {string} [image]            URL of the illustration (parchment background is fine; it's multiplied in).
 *                                       Without one a quiet silhouette is drawn in its place.
 * @property {string|number} [id]        stable identity; cards with the same id share one face texture
 * @property {string[]} [tags]           small notes under the wingspan, e.g. ['predator', 'flocking']
 */

/**
 * Render a bird card face. Resolves with a canvas sized FACE_SIZE x scale.
 * @param {Bird} bird
 * @param {{scale?: number}} [opts]  scale < 1 draws a smaller texture (same layout)
 */
export async function drawCardFace(bird, { scale = 1 } = {}) {
  const [face, art, symbols, ...foods] = await Promise.all([
    loadImage(FACE_URL),
    bird.image ? loadImage(bird.image) : null,
    loadSymbols(),
    ...(bird.food || []).map(f => (FOOD_ICONS[f] ? loadImage(FOOD_ICONS[f]) : null)),
    waitForFonts(),
  ]);
  const [W, H] = FACE_SIZE;
  const c = document.createElement('canvas');
  c.width = Math.round(W * scale); c.height = Math.round(H * scale);
  const g = c.getContext('2d');
  g.scale(c.width / W, c.height / H);
  if (face) g.drawImage(face, 0, 0, W, H);
  else { g.fillStyle = '#efe4cf'; g.fillRect(0, 0, W, H); }

  drawTitle(g, bird.name || '');
  drawIconBox(g, bird, foods.slice(0, (bird.food || []).length), symbols);
  drawStats(g, bird);
  if (art) drawArt(g, art);
  else drawSilhouette(g, bird);
  drawPower(g, bird, symbols);
  if (bird.scientific) {
    const [x0, y0, x1, y1] = REGIONS.footer;
    g.fillStyle = 'rgba(43,38,32,0.75)';
    g.font = `italic 28px ${FONT_BODY}`;
    g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(bird.scientific, (x0 + x1) / 2, (y0 + y1) / 2, x1 - x0);
  }
  return c;
}

function drawTitle(g, name) {
  const [x0, y0, x1, y1] = REGIONS.title;
  const maxW = x1 - x0 - 40;
  let size = 68;
  g.font = `700 ${size}px ${FONT_DISPLAY}`;
  while (g.measureText(name).width > maxW && size > 30) { size -= 2; g.font = `700 ${size}px ${FONT_DISPLAY}`; }
  g.fillStyle = INK;
  g.textAlign = 'center'; g.textBaseline = 'middle';
  g.fillText(name, (x0 + x1) / 2, (y0 + y1) / 2 + 4);
}

function drawIconBox(g, bird, foodImgs, symbols) {
  const [x0, y0, x1] = REGIONS.iconBox;
  const habitats = bird.habitats || [];
  // habitats: watercolour dots across the top
  habitats.forEach((h, i) => {
    const cx = x0 + 40 + i * 54, cy = y0 + 46;
    const grad = g.createRadialGradient(cx - 6, cy - 6, 4, cx, cy, 24);
    grad.addColorStop(0, HABITAT_COLORS[h] || '#888');
    grad.addColorStop(1, 'rgba(0,0,0,0)');
    g.fillStyle = grad;
    g.beginPath(); g.arc(cx, cy, 24, 0, Math.PI * 2); g.fill();
    g.fillStyle = HABITAT_COLORS[h] || '#888';
    g.globalAlpha = 0.7;
    g.beginPath(); g.arc(cx, cy, 15, 0, Math.PI * 2); g.fill();
    g.globalAlpha = 1;
  });
  // food cost: token icons, two per row
  const n = foodImgs.length, size = 64, gap = bird.foodOr ? 26 : 8;
  foodImgs.forEach((img, i) => {
    const row = Math.floor(i / 2), col = i % 2;
    const perRow = Math.min(2, n - row * 2);
    const rowW = perRow * size + (perRow - 1) * gap;
    const x = (x0 + x1) / 2 - rowW / 2 + col * (size + gap), y = y0 + 92 + row * (size + 10);
    g.save();
    if (bird.food[i] === 'wild') drawSymbol(g, 'wild', x + size / 2, y + size / 2, size, symbols, INK);
    else {
      g.beginPath(); g.arc(x + size / 2, y + size / 2, size / 2 - 1, 0, Math.PI * 2); g.clip();
      if (img) g.drawImage(img, x, y, size, size);
      else { g.fillStyle = '#bbb'; g.fill(); }
    }
    g.restore();
    if (bird.foodOr && col === 0 && perRow === 2) {
      g.fillStyle = INK; g.font = `700 30px ${FONT_BODY}`; g.textAlign = 'center'; g.textBaseline = 'middle';
      g.fillText('/', x + size + gap / 2, y + size / 2);
    }
  });
}

function drawStats(g, bird) {
  const [x0, y0, x1] = REGIONS.stats;
  const cx = (x0 + x1) / 2;
  g.fillStyle = INK; g.strokeStyle = INK; g.textAlign = 'center'; g.textBaseline = 'middle';
  // points with a feather
  if (bird.points != null) {
    g.font = `700 92px ${FONT_DISPLAY}`;
    g.fillText(String(bird.points), cx - 18, y0 + 70);
    drawFeather(g, cx + 38, y0 + 72, 34, INK);
  }
  // nest + egg limit
  if (bird.nest) drawNest(g, bird.nest, cx, y0 + 220);
  if (bird.eggLimit != null) {
    const per = 3, s = 22;
    for (let i = 0; i < bird.eggLimit; i++) {
      const row = Math.floor(i / per), col = i % per, inRow = Math.min(per, bird.eggLimit - row * per);
      const x = cx - ((inRow - 1) * (s + 10)) / 2 + col * (s + 10), y = y0 + 300 + row * 40;
      g.lineWidth = 3;
      g.beginPath(); g.ellipse(x, y, s / 2, s * 0.68, 0, 0, Math.PI * 2); g.stroke();
    }
  }
  // wingspan
  if (bird.wingspan != null) {
    g.font = `500 34px ${FONT_BODY}`;
    g.fillText(`${bird.wingspan} cm`, cx, y0 + 470);
    g.lineWidth = 3;
    g.beginPath(); g.moveTo(cx - 52, y0 + 430); g.quadraticCurveTo(cx, y0 + 410, cx + 52, y0 + 430); g.stroke();
  }
  // small notes: predator, flocking
  (bird.tags || []).forEach((tag, i) => {
    g.font = `italic 27px ${FONT_BODY}`;
    g.fillStyle = 'rgba(43,38,32,0.8)';
    g.fillText(tag, cx, y0 + 530 + i * 34, x1 - x0 - 8);
  });
}

// No illustration yet: a perched-bird silhouette in a soft wash, so the card still reads as a bird.
function drawSilhouette(g, bird) {
  const [x0, y0, x1, y1] = REGIONS.art;
  const cx = (x0 + x1) / 2 + 10, cy = (y0 + y1) / 2 + 10;
  // size follows wingspan a little, so an eagle looks bigger than a wren
  const k = 2.1 + Math.min(1.5, Math.log10(Math.max(10, bird.wingspan || 30)) - 1) * 0.9;
  const tint = HABITAT_COLORS[(bird.habitats || [])[0]] || '#8a8172';
  g.save();
  g.translate(cx, cy); g.scale(k, k);
  g.globalAlpha = 0.16; g.fillStyle = tint;
  g.beginPath(); g.ellipse(0, 6, 118, 96, -0.2, 0, Math.PI * 2); g.fill();
  g.globalAlpha = 0.5; g.fillStyle = '#5b5348'; g.strokeStyle = '#5b5348'; g.lineCap = 'round';
  // branch
  g.lineWidth = 5; g.beginPath(); g.moveTo(-105, 62); g.quadraticCurveTo(-10, 50, 105, 66); g.stroke();
  // tail, body, head, beak
  g.beginPath(); g.moveTo(-28, 12); g.lineTo(-98, 46); g.lineTo(-88, 58); g.lineTo(-18, 34); g.closePath(); g.fill();
  g.beginPath(); g.ellipse(2, 8, 50, 34, -0.42, 0, Math.PI * 2); g.fill();
  g.beginPath(); g.arc(40, -30, 22, 0, Math.PI * 2); g.fill();
  g.beginPath(); g.moveTo(58, -36); g.lineTo(84, -27); g.lineTo(58, -21); g.closePath(); g.fill();
  // legs
  g.lineWidth = 3;
  g.beginPath(); g.moveTo(6, 38); g.lineTo(4, 56); g.moveTo(20, 34); g.lineTo(22, 56); g.stroke();
  g.restore();
}

export function drawNest(g, nest, x, y) {
  g.save();
  g.lineWidth = 5; g.lineCap = 'round';
  g.beginPath();
  if (nest === 'bowl') { g.ellipse(x, y - 8, 46, 34, 0, 0, Math.PI); g.moveTo(x - 46, y - 8); g.lineTo(x + 46, y - 8); }
  else if (nest === 'cavity') { g.arc(x, y, 38, 0, Math.PI * 2); g.moveTo(x + 14, y); g.arc(x, y, 14, 0, Math.PI * 2); }
  else if (nest === 'ground') { g.moveTo(x - 50, y + 12); g.quadraticCurveTo(x, y - 30, x + 50, y + 12); g.moveTo(x - 58, y + 14); g.lineTo(x + 58, y + 14); }
  else if (nest === 'platform') { for (let i = 0; i < 3; i++) { g.moveTo(x - 50 + i * 6, y - 14 + i * 12); g.lineTo(x + 50 - i * 6, y - 18 + i * 12); } }
  else { for (let i = 0; i < 5; i++) { const a = -Math.PI / 2 + (i * 4 * Math.PI) / 5; g[i ? 'lineTo' : 'moveTo'](x + Math.cos(a) * 36, y + Math.sin(a) * 36); } g.closePath(); }
  g.stroke();
  g.restore();
}

function drawArt(g, img) {
  const [x0, y0, x1, y1] = REGIONS.art;
  const bw = x1 - x0, bh = y1 - y0;
  const s = Math.min(bw / img.width, bh / img.height);
  const w = img.width * s, h = img.height * s;
  // fade the illustration's edges so crop borders and stray marks disappear into the card
  const off = document.createElement('canvas');
  off.width = Math.ceil(w); off.height = Math.ceil(h);
  const o = off.getContext('2d');
  o.drawImage(img, 0, 0, w, h);
  o.globalCompositeOperation = 'destination-in';
  const fade = 0.12;
  const gx = o.createLinearGradient(0, 0, w, 0);
  gx.addColorStop(0, 'rgba(0,0,0,0)'); gx.addColorStop(fade, '#000'); gx.addColorStop(1 - fade, '#000'); gx.addColorStop(1, 'rgba(0,0,0,0)');
  o.fillStyle = gx; o.fillRect(0, 0, w, h);
  const gy = o.createLinearGradient(0, 0, 0, h);
  gy.addColorStop(0, 'rgba(0,0,0,0)'); gy.addColorStop(fade, '#000'); gy.addColorStop(1 - fade, '#000'); gy.addColorStop(1, 'rgba(0,0,0,0)');
  o.fillStyle = gy; o.fillRect(0, 0, w, h);
  g.save();
  g.globalCompositeOperation = 'multiply';
  g.drawImage(off, x0 + (bw - w) / 2, y0 + (bh - h) / 2);
  g.restore();
}

function drawPower(g, bird, symbols) {
  const [x0, y0, x1, y1] = REGIONS.power;
  const tint = POWER_TINTS[bird.powerColor || 'brown'];
  if (tint && bird.power) {
    g.save();
    g.globalCompositeOperation = 'multiply';
    g.fillStyle = tint;
    g.fillRect(x0, y0, x1 - x0, y1 - y0);
    g.restore();
  }
  if (!bird.power) return;
  const maxW = x1 - x0 - 40;
  let size = 36, lines;
  for (;;) {
    g.font = `500 ${size}px ${FONT_BODY}`;
    lines = layoutRich(g, bird.power, maxW, size);
    if (lines.length * size * 1.15 <= y1 - y0 - 14 || size <= 18) break;
    size -= 2;
  }
  const lh = size * 1.15, top = (y0 + y1) / 2 - ((lines.length - 1) * lh) / 2;
  drawRich(g, lines, (x0 + x1) / 2, top, lh, size, symbols, INK);
}
