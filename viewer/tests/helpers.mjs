import { readFileSync, readdirSync, statSync } from 'node:fs';
import { gunzipSync } from 'node:zlib';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { cardsFromLists, parseJsonl } from '../app/viewer/replay/log.js';

export const ROOT = fileURLToPath(new URL('../..', import.meta.url));
export const SAMPLES = join(ROOT, 'docs', 'samples');

export function cardReference() {
  return cardsFromLists(JSON.parse(readFileSync(join(ROOT, 'wingsim', 'data', 'cards.json'), 'utf8')));
}

/** Read either log form. Returns { lines, cards }. */
export function readLog(path) {
  if (path.endsWith('.gz')) return { lines: parseJsonl(gunzipSync(readFileSync(path)).toString('utf8')), cards: cardReference() };
  if (path.endsWith('.jsonl')) return { lines: parseJsonl(readFileSync(path, 'utf8')), cards: cardReference() };
  return JSON.parse(readFileSync(path, 'utf8'));
}

function walk(dir, out = []) {
  for (const name of readdirSync(dir)) {
    const p = join(dir, name);
    if (statSync(p).isDirectory()) walk(p, out);
    else if (/\.jsonl(\.gz)?$/.test(name)) out.push(p);
  }
  return out;
}

/** The sample logs, plus every log under $WINGSIM_LOGS if it is set (for a wider check). */
export function logFiles() {
  const files = walk(SAMPLES);
  if (process.env.WINGSIM_LOGS) files.push(...walk(process.env.WINGSIM_LOGS));
  return files;
}
