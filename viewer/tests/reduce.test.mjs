// The reducer must rebuild every snapshot from the one before it plus the events between.
// Run with more logs:  WINGSIM_LOGS=../logs npm test
import test from 'node:test';
import assert from 'node:assert/strict';
import { applyEvent, cloneState, VIEW_FIELDS } from '../app/viewer/replay/reduce.js';
import { logFiles, readLog } from './helpers.mjs';

const sorted = v => [...v].sort((a, b) => a - b);

// What "the same" means for each field. Orders the log does not carry are ignored.
function normal(field, v) {
  switch (field) {
    case 'players': return v.map(p => ({ ...p, hand: sorted(p.hand), bonus: sorted(p.bonus), pink_used: sorted(p.pink_used || []) }));
    case 'tucked': return v.length;                 // identities of cards tucked from the deck are not logged
    case 'deck': case 'discard': case 'bonus_discard': case 'bonus_deck': return sorted(v);
    case 'variant': return Object.fromEntries(Object.entries(v || {}).filter(([, x]) => x != null));
    default: return v;
  }
}

// Places where the log is known not to say enough (see FORMAT-REQUESTS.md). The reducer is
// allowed to be behind here, and must have caught up by the next snapshot outside them.
function knownGap(field, decision, events, nextDecision) {
  // R1: bonus cards leave the bonus deck when the power is used, with no event.
  if ((field === 'bonus_deck' || field === 'bonus_discard') && nextDecision?.kind === 'keep_bonus') return true;
  // R2: cards taken for the American Oystercatcher draft produce no event until cards_revealed.
  if ((field === 'tray' || field === 'deck') && decision.kind === 'draw_card'
    && !events.some(e => e.e === 'cards_drawn' || e.e === 'cards_revealed')) return true;
  return false;
}

for (const file of logFiles()) {
  test(`reducer rebuilds snapshots: ${file.split('/').slice(-2).join('/')}`, () => {
    const { lines } = readLog(file);
    const snaps = new Map(), decisions = [], events = new Map();
    for (const l of lines) {
      if (l.t === 'snapshot') snaps.set(l.before_seq ?? 'final', l);
      else if (l.t === 'decision') decisions.push(l);
      else if (l.t === 'event') { if (!events.has(l.seq)) events.set(l.seq, []); events.get(l.seq).push(l); }
    }
    let state = null, compared = 0;
    decisions.forEach((d, i) => {
      if (snaps.has(d.seq)) state = cloneState(snaps.get(d.seq).state);
      const es = events.get(d.seq) || [];
      for (const e of es) assert.ok(applyEvent(state, e, { decision: d }), `unknown event ${e.e}`);
      const next = decisions[i + 1];
      const want = snaps.get(next ? next.seq : 'final');
      if (!want) return;
      compared++;
      const target = cloneState(want.state);
      for (const f of VIEW_FIELDS) {
        if (f === 'looked' || knownGap(f, d, es, next)) continue;
        assert.deepEqual(normal(f, state[f]), normal(f, target[f]), `${f} after decision ${d.seq} (${d.kind})`);
      }
    });
    assert.ok(compared > 0, 'no snapshot pairs to compare');
  });
}

// The same check the way a per-turn log is read: start from a turn-start snapshot, apply
// every event of the turn, and compare only at the next turn start. No known gaps are
// allowed here: by the end of a turn the reducer must be exactly right.
for (const file of logFiles()) {
  test(`reducer carries a whole turn: ${file.split('/').slice(-2).join('/')}`, () => {
    const { lines } = readLog(file);
    const snaps = new Map(), decisions = [], events = new Map();
    for (const l of lines) {
      if (l.t === 'snapshot') snaps.set(l.before_seq ?? 'final', l);
      else if (l.t === 'decision') decisions.push(l);
      else if (l.t === 'event') { if (!events.has(l.seq)) events.set(l.seq, []); events.get(l.seq).push(l); }
    }
    const anchor = s => s && (s.turn_start || s.before_seq === 1 || s.before_seq == null);
    let state = null, compared = 0;
    decisions.forEach((d, i) => {
      if (anchor(snaps.get(d.seq))) state = cloneState(snaps.get(d.seq).state);
      for (const e of events.get(d.seq) || []) applyEvent(state, e, { decision: d });
      const next = decisions[i + 1];
      const want = snaps.get(next ? next.seq : 'final');
      if (!anchor(want)) return;
      compared++;
      const target = cloneState(want.state);
      for (const f of VIEW_FIELDS) {
        if (f === 'looked') continue;
        assert.deepEqual(normal(f, state[f]), normal(f, target[f]), `${f} at the turn start after decision ${d.seq}`);
      }
    });
    assert.ok(compared > 0);
  });
}
