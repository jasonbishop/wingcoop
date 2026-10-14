// The opening screen: drop a file, or pick one of the logs the dev server can see.

import { el, esc } from './rich.js';
import { listRuns } from '../replay/load.js';

const $ = id => document.getElementById(id);
const kb = n => (n > 1e6 ? `${(n / 1e6).toFixed(1)} MB` : `${Math.max(1, Math.round(n / 1024))} KB`);

// "7-3p-w0.5-ladder_2_p1_0-share.jsonl.gz" -> seed 7, 3 players, the rest of the cell name
function parseName(file) {
  const base = file.replace(/\.(jsonl\.gz|jsonl|json)$/, '');
  const m = /^(\d+)-(\d)p(?:-(.*))?$/.exec(base);
  return m ? { seed: m[1], players: m[2], cell: m[3] || '' } : { label: base };
}

export class Home {
  /** @param {{onFile: (f: File) => void, onPath: (p: string) => void}} handlers */
  constructor({ onFile, onPath }) {
    this.onPath = onPath;
    const drop = $('drop');
    $('file').addEventListener('change', e => { if (e.target.files[0]) onFile(e.target.files[0]); e.target.value = ''; });
    // a log dropped anywhere on the page opens, whether or not this screen is showing
    window.addEventListener('dragover', e => { e.preventDefault(); drop.classList.add('over'); });
    window.addEventListener('dragleave', () => drop.classList.remove('over'));
    window.addEventListener('drop', e => {
      e.preventDefault();
      drop.classList.remove('over');
      const f = e.dataTransfer?.files?.[0];
      if (f) onFile(f);
    });
    $('home-close').addEventListener('click', () => this.hide());
  }

  async show({ canClose = false } = {}) {
    $('home').hidden = false;
    $('home-close').hidden = !canClose;
    this.error(null);
    this.renderRuns(await listRuns());
  }

  hide() { $('home').hidden = true; }

  error(message) {
    $('home-error').hidden = !message;
    $('home-error').textContent = message || '';
  }

  busy(text) {
    $('drop').classList.toggle('busy', !!text);
    if (text) this.error(null);
  }

  renderRuns(files) {
    const box = $('runs');
    box.replaceChildren();
    if (files == null) {
      box.append(el('p.hint', {}, 'Run the viewer with “npm run dev” to browse the simulator’s logs/ folder from here.'));
      return;
    }
    if (!files.length) {
      box.append(el('p.hint', { html: 'No logs found under <code>logs/</code> or <code>docs/samples/</code>. Run an experiment with full logging and reload.' }));
      return;
    }
    const groups = new Map();
    for (const f of files) {
      const dir = f.path.slice(0, f.path.lastIndexOf('/'));
      if (!groups.has(dir)) groups.set(dir, []);
      groups.get(dir).push(f);
    }
    const filter = el('input.filter', { type: 'search', placeholder: `Filter ${files.length} games…`, 'aria-label': 'Filter games' });
    box.append(el('h2', {}, 'Games on this machine'), filter);
    const sections = [];
    for (const [dir, list] of [...groups].sort((a, b) => a[0].localeCompare(b[0]))) {
      list.sort((a, b) => a.path.localeCompare(b.path, undefined, { numeric: true }));
      const items = list.map(f => {
        const name = f.path.slice(f.path.lastIndexOf('/') + 1);
        const p = parseName(name);
        const label = p.label
          ? esc(p.label)
          : `<b>seed ${esc(p.seed)}</b> · ${esc(p.players)} players${p.cell ? ` · <span class="cell">${esc(p.cell)}</span>` : ''}`;
        return el('button.run', { title: f.path, dataset: { text: f.path.toLowerCase() }, onclick: () => this.onPath(f.path), html: `${label}<span class="size">${kb(f.size)}</span>` });
      });
      const section = el('section.rungroup', {}, el('h3', {}, dir), el('div.runlist', {}, items));
      sections.push({ section, items });
      box.append(section);
    }
    filter.addEventListener('input', () => {
      const q = filter.value.trim().toLowerCase();
      for (const { section, items } of sections) {
        let any = false;
        for (const b of items) { const hit = !q || b.dataset.text.includes(q); b.hidden = !hit; any ||= hit; }
        section.hidden = !any;
      }
    });
  }
}
