// Draws a goal tile at runtime, for goals that have no tile art of their own.
// The label may contain symbols in brackets ("[egg] in bowl nests"); see cards/src/symbols.js.

import { waitForFonts } from '../../cards/src/cardFace.js';
import { loadSymbols, layoutRich, drawRich } from '../../cards/src/symbols.js';

const FONT = '"Alegreya SC", "Palatino Linotype", Palatino, Georgia, serif';
const SIZE = 384;

/**
 * @param {{label: string, tint?: string}} goal  tint: border wash colour (e.g. a habitat colour)
 * @returns {Promise<HTMLCanvasElement>}
 */
export async function drawGoalTile(goal) {
  const [symbols] = await Promise.all([loadSymbols(), waitForFonts()]);
  const c = document.createElement('canvas');
  c.width = c.height = SIZE;
  const g = c.getContext('2d');
  const tint = goal.tint || '#6f8fb0';

  g.fillStyle = '#f4ecdb';
  g.fillRect(0, 0, SIZE, SIZE);
  // watercolour border: a few uneven strokes of the tint
  let seed = [...goal.label].reduce((a, ch) => (a * 31 + ch.charCodeAt(0)) % 2147483647, 7);
  const rnd = () => ((seed = (seed * 16807) % 2147483647) / 2147483647);
  g.strokeStyle = tint;
  for (let i = 0; i < 5; i++) {
    g.globalAlpha = 0.22 + rnd() * 0.12;
    g.lineWidth = 20 + rnd() * 22;
    const inset = 14 + rnd() * 10;
    g.beginPath(); g.roundRect(inset, inset, SIZE - inset * 2, SIZE - inset * 2, 26); g.stroke();
  }
  g.globalAlpha = 0.9; g.lineWidth = 3;
  g.beginPath(); g.roundRect(34, 34, SIZE - 68, SIZE - 68, 14); g.stroke();
  g.globalAlpha = 1;

  const maxW = SIZE - 96, maxH = SIZE - 100;
  let size = 76, lines;
  for (;;) {
    g.font = `700 ${size}px ${FONT}`;
    lines = layoutRich(g, goal.label, maxW, size);
    const widest = Math.max(...lines.map(l => l.width));
    if ((lines.length * size * 1.12 <= maxH && widest <= maxW) || size <= 30) break;
    size -= 2;
  }
  const lh = size * 1.12;
  drawRich(g, lines, SIZE / 2, SIZE / 2 - ((lines.length - 1) * lh) / 2 + 4, lh, size, symbols, '#2b2620');
  return c;
}
