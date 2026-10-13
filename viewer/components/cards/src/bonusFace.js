// Draws a bonus card face onto the blank bonus card art.
//
// Regions are in bonus_face.jpg pixels (966 x 1419); re-measure if that art is regenerated.

import { loadImage } from '../../tabletop/src/assets.js';
import { waitForFonts } from './cardFace.js';
import { loadSymbols, layoutRich, drawRich } from './symbols.js';

export const BONUS_FACE_URL = new URL('../assets/bonus_face.jpg', import.meta.url).href;
export const BONUS_FACE_SIZE = [966, 1419];

export const BONUS_REGIONS = {
  name:      [110, 150, 856, 300],
  subtitle:  [110, 318, 856, 372],
  condition: [120, 430, 846, 900],
  points:    [120, 960, 846, 1270],
};

const INK = '#2b2620';
const FONT_DISPLAY = '"Alegreya SC", "Palatino Linotype", Palatino, Georgia, serif';
const FONT_BODY = '"Alegreya Sans", "Gill Sans", "Trebuchet MS", sans-serif';

/**
 * @typedef {object} Bonus
 * @property {string} name
 * @property {string} [condition]   what is counted, e.g. "Birds with [platform] nests"
 * @property {string} [points]      how it scores, e.g. "4+ birds: 4[point]; 6+ birds: 7[point]"
 * @property {string|number} [id]   stable identity; cards with the same id share one face texture
 */

/** Render a bonus card face. Resolves with a canvas sized BONUS_FACE_SIZE x scale. */
export async function drawBonusFace(bonus, { scale = 1 } = {}) {
  const [face, symbols] = await Promise.all([loadImage(BONUS_FACE_URL), loadSymbols(), waitForFonts()]);
  const [W, H] = BONUS_FACE_SIZE;
  const c = document.createElement('canvas');
  c.width = Math.round(W * scale); c.height = Math.round(H * scale);
  const g = c.getContext('2d');
  g.scale(c.width / W, c.height / H);
  if (face) g.drawImage(face, 0, 0, W, H);
  else { g.fillStyle = '#f3ead8'; g.fillRect(0, 0, W, H); }

  // name
  {
    const [x0, y0, x1, y1] = BONUS_REGIONS.name;
    let size = 92;
    g.font = `700 ${size}px ${FONT_DISPLAY}`;
    while (g.measureText(bonus.name || '').width > x1 - x0 && size > 40) { size -= 2; g.font = `700 ${size}px ${FONT_DISPLAY}`; }
    g.fillStyle = INK; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText(bonus.name || '', (x0 + x1) / 2, (y0 + y1) / 2);
    g.strokeStyle = 'rgba(43,38,32,0.55)'; g.lineWidth = 2;
    g.beginPath(); g.moveTo(x0 + 60, y1 + 6); g.lineTo(x1 - 60, y1 + 6); g.stroke();
  }
  {
    const [x0, y0, x1, y1] = BONUS_REGIONS.subtitle;
    g.font = `500 40px ${FONT_DISPLAY}`;
    g.fillStyle = 'rgba(43,38,32,0.7)'; g.textAlign = 'center'; g.textBaseline = 'middle';
    g.fillText('Bonus Card', (x0 + x1) / 2, (y0 + y1) / 2);
  }
  fitRich(g, bonus.condition || '', BONUS_REGIONS.condition, 64, 500, symbols);
  if (bonus.points) {
    const [x0, y0, x1] = BONUS_REGIONS.points;
    g.strokeStyle = 'rgba(43,38,32,0.55)'; g.lineWidth = 2;
    g.beginPath(); g.moveTo(x0 + 40, y0 - 24); g.lineTo(x1 - 40, y0 - 24); g.stroke();
    // one scoring tier per line
    fitRich(g, bonus.points.split(/;\s*/).join('\n'), BONUS_REGIONS.points, 58, 700, symbols);
  }
  return c;
}

// Draw text centred in a region at the largest size that fits. Newlines force breaks.
function fitRich(g, text, [x0, y0, x1, y1], startSize, weight, symbols) {
  const maxW = x1 - x0;
  let size = startSize, lines;
  for (;;) {
    g.font = `${weight} ${size}px ${FONT_BODY}`;
    lines = text.split('\n').flatMap(t => layoutRich(g, t, maxW, size));
    if (lines.length * size * 1.2 <= y1 - y0 || size <= 24) break;
    size -= 2;
  }
  const lh = size * 1.2;
  drawRich(g, lines, (x0 + x1) / 2, (y0 + y1) / 2 - ((lines.length - 1) * lh) / 2, lh, size, symbols, INK);
}
