// Getting a log into the browser: from a dropped/picked file, or from the dev server's
// log folders (server/api.js). Either way the result goes to buildReplay().

import { buildReplay, parseJsonl } from './log.js';

let cardsPromise = null;
/** The card reference for native logs (they don't carry one). Needs the dev server. */
function fetchCards() {
  cardsPromise ||= fetch('/api/cards').then(r => {
    if (!r.ok) throw new Error('This log has no card reference in it. Open an exported .json instead, or run the viewer with `npm run dev` so it can read wingsim/data/cards.json.');
    return r.json();
  }).catch(err => { cardsPromise = null; throw err; });
  return cardsPromise;
}

async function gunzip(blob) {
  if (typeof DecompressionStream === 'undefined') throw new Error('This browser cannot unpack .gz files. Export the log to .json first.');
  return new Response(blob.stream().pipeThrough(new DecompressionStream('gzip'))).text();
}

async function fromText(text, isJsonl) {
  if (!isJsonl) {
    const data = JSON.parse(text);
    if (data.lines) return buildReplay(data, data.cards ? null : await fetchCards());
    throw new Error('This .json file is not an exported replay (no "lines").');
  }
  return buildReplay(parseJsonl(text), await fetchCards());
}

/** Open a File the user dropped or picked: .json (exported), .jsonl or .jsonl.gz (native). */
export async function loadFile(file) {
  const name = file.name.toLowerCase();
  const text = name.endsWith('.gz') ? await gunzip(file) : await file.text();
  const replay = await fromText(text, /\.jsonl(\.gz)?$/.test(name));
  replay.name = file.name;
  return replay;
}

/** Open a log from the dev server by its listed path, e.g. "logs/exp/coop/7-3p-x.jsonl.gz". */
export async function loadPath(path) {
  const r = await fetch(`/api/log?path=${encodeURIComponent(path)}`);
  if (!r.ok) throw new Error(`Could not open ${path} (${r.status}).`);
  const replay = await fromText(await r.text(), !path.endsWith('.json'));
  replay.name = path;
  replay.path = path;
  return replay;
}

/** The logs the dev server can see: [{ root, path, size, mtime }], or null without a dev server. */
export async function listRuns() {
  try {
    const r = await fetch('/api/runs');
    if (!r.ok) return null;
    return (await r.json()).files;
  } catch { return null; }
}
