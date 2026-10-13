// Text with symbols in brackets ("Gain 1 [fish]") as HTML for the panels.

import { FOOD_ICONS, EGG_ICONS } from '../../../components/pieces/src/index.js';

const ICONS = { ...FOOD_ICONS, egg: EGG_ICONS.cream };
const WORDS = { wild: 'any food', card: 'card', die: 'die', point: 'point' };

export const esc = s => String(s ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));

/** Escape text and turn [symbols] into icons or words. */
export function rich(text) {
  return esc(String(text ?? '').replace(/(\d+)\s*\[point\]/g, (m, n) => `${n} ${n === '1' ? 'point' : 'points'}`))
    .replace(/\[([a-z_]+)\]/g, (m, name) => {
      if (ICONS[name]) return `<img class="sym sym-${name}" src="${ICONS[name]}" alt="${name}" title="${name}">`;
      return WORDS[name] ?? name;
    });
}

/** Create an element: el('div.cls', { attrs }, ...children). Strings become text. */
export function el(spec, attrs = {}, ...children) {
  const [tag, ...classes] = spec.split('.');
  const node = document.createElement(tag || 'div');
  if (classes.length) node.className = classes.join(' ');
  for (const [k, v] of Object.entries(attrs)) {
    if (v == null || v === false) continue;
    if (k === 'html') node.innerHTML = v;
    else if (k === 'class') { for (const c of String(v).split(/\s+/).filter(Boolean)) node.classList.add(c); }
    else if (k === 'style' && typeof v === 'object') {
      for (const [prop, val] of Object.entries(v)) {
        if (prop.startsWith('--')) node.style.setProperty(prop, val); else node.style[prop] = val;
      }
    }
    else if (k.startsWith('on')) node.addEventListener(k.slice(2), v);
    else if (k === 'dataset') Object.assign(node.dataset, v);
    else node.setAttribute(k, v === true ? '' : v);
  }
  for (const c of children.flat()) if (c != null && c !== false) node.append(c);
  return node;
}
