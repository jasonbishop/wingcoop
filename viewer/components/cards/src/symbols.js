// Card text with symbols. Rules text arrives with symbols written in brackets, e.g.
// "Gain 1 [fish] from the birdfeeder" or "2[point] per bird". Foods and eggs are drawn
// as their token art, a few others as small glyphs, and the rest as plain words.

import { loadImage } from '../../tabletop/src/assets.js';
import { FOOD_ICONS, EGG_ICONS } from '../../pieces/src/pieces.js';

const IMAGE_URLS = { ...FOOD_ICONS, egg: EGG_ICONS.cream };

/** Symbols written as a word. Anything unknown is written as its own name. */
export const SYMBOL_WORDS = {
  bird: 'bird', predator: 'predator', flocking: 'flocking',
  bowl: 'bowl', cavity: 'cavity', ground: 'ground', platform: 'platform', star: 'star',
  forest: 'forest', grassland: 'grassland', wetland: 'wetland',
};

const GLYPHS = new Set(['card', 'die', 'wild', 'point']);

let images = null;
/** Load the symbol images once. Resolves with { name: HTMLImageElement|null }. */
export function loadSymbols() {
  images ||= Promise.all(Object.entries(IMAGE_URLS).map(async ([k, url]) => [k, await loadImage(url)]))
    .then(Object.fromEntries);
  return images;
}

/** Split text into runs: { text } or { symbol }. Spaces separate words; symbols are their own run. */
export function tokenize(text) {
  const out = [];
  // "3[point]" reads better as words than as a number glued to a glyph
  const src = String(text || '').replace(/(\d+)\s*\[point\]/g, (m, n) => `${n} ${n === '1' ? 'point' : 'points'}`);
  for (const part of src.split(/(\[[a-z_/]+\])/)) {
    if (!part) continue;
    const m = /^\[([a-z_/]+)\]$/.exec(part);
    if (!m) { out.push({ text: part }); continue; }
    const name = m[1];
    if (IMAGE_URLS[name] || GLYPHS.has(name)) out.push({ symbol: name });
    else out.push({ text: SYMBOL_WORDS[name] ?? name });
  }
  return out;
}

/** The text with every symbol written as a word (for titles, tooltips and alt text). */
export function plainText(text) {
  return tokenize(text).map(t => t.text ?? (t.symbol === 'wild' ? 'food' : t.symbol)).join('');
}

/**
 * Break text into lines no wider than maxW at the context's current font.
 * @returns {Array<Array<{text?:string, symbol?:string, w:number}>>}
 */
export function layoutRich(g, text, maxW, size) {
  const items = [];
  for (const run of tokenize(text)) {
    if (run.symbol) { items.push({ symbol: run.symbol, w: size * 1.02 }); continue; }
    for (const piece of run.text.split(/(\s+)/)) {
      if (!piece) continue;
      if (/^\s+$/.test(piece)) items.push({ space: true, w: g.measureText(' ').width });
      else items.push({ text: piece, w: g.measureText(piece).width });
    }
  }
  const lines = [];
  let line = [], width = 0;
  const flush = () => {
    while (line.length && line[line.length - 1].space) width -= line.pop().w;
    if (line.length) lines.push(Object.assign(line, { width }));
    line = []; width = 0;
  };
  for (let i = 0; i < items.length; i++) {
    const it = items[i];
    if (it.space) { if (line.length) { line.push(it); width += it.w; } continue; }
    // keep runs with no space between them together ("[fish]." or "[egg],")
    let chunk = [it], cw = it.w;
    while (i + 1 < items.length && !items[i + 1].space) { chunk.push(items[++i]); cw += items[i].w; }
    if (line.length && width + cw > maxW) flush();
    line.push(...chunk); width += cw;
  }
  flush();
  return lines;
}

/** Draw lines from layoutRich() centred on cx, first baseline-middle at `top`. */
export function drawRich(g, lines, cx, top, lineHeight, size, imgs, ink = '#2b2620') {
  g.textAlign = 'left'; g.textBaseline = 'middle';
  lines.forEach((line, n) => {
    let x = cx - line.width / 2;
    const y = top + n * lineHeight;
    for (const it of line) {
      if (it.text) { g.fillStyle = ink; g.fillText(it.text, x, y); }
      else if (it.symbol) drawSymbol(g, it.symbol, x + it.w / 2, y, size, imgs, ink);
      x += it.w;
    }
  });
}

/** Draw one symbol centred on (cx, cy), about `size` px tall. */
export function drawSymbol(g, name, cx, cy, size, imgs = {}, ink = '#2b2620') {
  const r = size * 0.48;
  g.save();
  if (name === 'egg' && imgs.egg) {
    const h = size * 1.05, w = h * (imgs.egg.width / imgs.egg.height);
    g.drawImage(imgs.egg, cx - w / 2, cy - h / 2, w, h);
  } else if (imgs[name]) {
    g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.clip();
    g.drawImage(imgs[name], cx - r, cy - r, r * 2, r * 2);
  } else if (name === 'wild') {
    // "any food": a disc in five wedges
    const colors = ['#c98a7c', '#d9b65a', '#7fa3bf', '#b05a6e', '#8c8478'];
    colors.forEach((c, i) => {
      g.fillStyle = c;
      g.beginPath(); g.moveTo(cx, cy);
      g.arc(cx, cy, r, -Math.PI / 2 + (i * 2 * Math.PI) / 5, -Math.PI / 2 + ((i + 1) * 2 * Math.PI) / 5);
      g.closePath(); g.fill();
    });
    g.strokeStyle = ink; g.lineWidth = Math.max(1.5, size * 0.05);
    g.beginPath(); g.arc(cx, cy, r, 0, Math.PI * 2); g.stroke();
  } else if (name === 'card') {
    const w = size * 0.62, h = size * 0.9, rad = size * 0.09;
    g.fillStyle = '#f3ead6'; g.strokeStyle = ink; g.lineWidth = Math.max(1.5, size * 0.06);
    g.beginPath(); g.roundRect(cx - w / 2, cy - h / 2, w, h, rad); g.fill(); g.stroke();
    g.beginPath(); g.moveTo(cx - w * 0.25, cy - h * 0.2); g.lineTo(cx + w * 0.25, cy - h * 0.2); g.stroke();
  } else if (name === 'die') {
    const s = size * 0.8, rad = size * 0.14;
    g.fillStyle = '#c9a877'; g.strokeStyle = ink; g.lineWidth = Math.max(1.5, size * 0.06);
    g.beginPath(); g.roundRect(cx - s / 2, cy - s / 2, s, s, rad); g.fill(); g.stroke();
    g.fillStyle = ink;
    for (const [dx, dy] of [[-0.22, -0.22], [0, 0], [0.22, 0.22]]) { g.beginPath(); g.arc(cx + dx * s, cy + dy * s, s * 0.07, 0, Math.PI * 2); g.fill(); }
  } else if (name === 'point') {
    drawFeather(g, cx, cy, size * 0.5, ink);
  }
  g.restore();
}

/** A small quill feather, the points mark. `h` is half its length. */
export function drawFeather(g, x, y, h, ink = '#2b2620') {
  g.save();
  g.translate(x, y); g.rotate(-0.5);
  g.strokeStyle = ink; g.lineWidth = Math.max(1.5, h * 0.09); g.lineCap = 'round';
  g.beginPath(); g.moveTo(0, h); g.lineTo(0, -h); g.stroke();
  g.beginPath(); g.moveTo(0, -h); g.quadraticCurveTo(h * 0.6, -h * 0.24, 0, h * 0.65); g.quadraticCurveTo(-h * 0.6, -h * 0.24, 0, -h); g.stroke();
  g.restore();
}
