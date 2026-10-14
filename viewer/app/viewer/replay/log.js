// Reads a replay log (docs/replay-log-format.md) into a list of positions.
//
// A *position* is the table at one moment plus the decision pending there:
//
//   positions[i] = {
//     index,                 // 0 .. N
//     state,                 // state-shaped object (section 5): the board before the decision
//     exact,                 // true if `state` came straight from a snapshot, false if derived from events
//     decision,              // the decision line made here, or null at the final position
//     events,                // the event lines that choice caused (what happened next)
//     round, turn_no, turn,  // when
//     turnStart,             // true if this is the first decision of a turn
//     quiet,                 // per event: true if it changed nothing (an unchanged tray refill)
//   }
//
// positions[0] is the state before decision 1 and positions[N] is the final state, so
// playing step i means: show positions[i], reveal the choice, animate its events and
// arrive at positions[i + 1]. This is the "one step" of section 9; a live game would
// fill in the same object with `decision.choice` still unset.

import { applyEvent, cloneState } from './reduce.js';

export const SUPPORTED_VERSION = 2;

/** Parse JSON Lines text into line objects. */
export function parseJsonl(text) {
  const lines = [];
  for (const raw of text.split('\n')) {
    const t = raw.trim();
    if (t) lines.push(JSON.parse(t));
  }
  return lines;
}

/**
 * Turn the card reference of wingsim/data/cards.json (lists with an `id` field) into the
 * keyed form an exported file carries.
 */
export function cardsFromLists(data) {
  const keyed = list => Object.fromEntries((list || []).map(c => [String(c.id), c]));
  return { birds: keyed(data.birds), bonus: keyed(data.bonus), goals: keyed(data.goals) };
}

/** Accepts an exported file ({cards, lines}) or bare lines plus a card reference. */
export function buildReplay(input, cards = null) {
  const lines = Array.isArray(input) ? input : input.lines;
  cards = (Array.isArray(input) ? null : input.cards) || cards;
  if (!Array.isArray(lines) || !lines.length) throw new Error('The log has no lines.');
  const header = lines[0];
  if (header.t !== 'header') throw new Error('The first line of a log must be the header.');
  if (!cards) throw new Error('No card reference: open an exported .json, or supply wingsim/data/cards.json.');
  if (cards.birds && Array.isArray(cards.birds)) cards = cardsFromLists(cards);

  const warnings = [];
  if (header.version !== SUPPORTED_VERSION) {
    warnings.push(`Log format version ${header.version}; this viewer was written for version ${SUPPORTED_VERSION}.`);
  }

  const snapshots = new Map();   // before_seq (or 'final') -> snapshot line
  const decisions = [];
  const eventsBySeq = new Map();
  for (const l of lines) {
    if (l.t === 'snapshot') snapshots.set(l.before_seq ?? 'final', l);
    else if (l.t === 'decision') decisions.push(l);
    else if (l.t === 'event') {
      if (!eventsBySeq.has(l.seq)) eventsBySeq.set(l.seq, []);
      eventsBySeq.get(l.seq).push(l);
    }
  }
  decisions.sort((a, b) => a.seq - b.seq);
  if (!snapshots.has(1) && decisions.length) throw new Error('The log has no snapshot before the first decision.');

  const unknown = new Set();
  const positions = [];
  let live = null;        // derived state carried forward between snapshots
  let turnOwner = null;

  const dealEvents = eventsBySeq.get(0) || [];

  for (let i = 0; i <= decisions.length; i++) {
    const decision = decisions[i] || null;
    const snap = decision ? snapshots.get(decision.seq) : snapshots.get('final');
    let state, exact;
    if (snap) { state = cloneState(snap.state); exact = true; }
    else if (live) { state = live; exact = false; }
    else throw new Error(`No snapshot to start from at decision ${decision?.seq}.`);

    const events = decision ? (eventsBySeq.get(decision.seq) || []) : [];
    // The turn a position belongs to. A turn_start event is logged under the decision
    // that ended the previous turn, so it applies from the next position on.
    if (snap && snap.player != null && snap.state.phase === 'turns') turnOwner = snap.player;
    if (state.phase !== 'turns') turnOwner = null;

    positions.push({
      index: i,
      state,
      exact,
      decision,
      events,
      round: decision ? decision.round : state.round,
      turn_no: decision ? decision.turn_no : state.turn_no,
      turn: turnOwner,
      turnStart: snap ? !!snap.turn_start : false,
      pending: snap?.state.pending ?? null,
      quiet: [],             // per event: true if it changed nothing worth reporting
    });

    if (decision) {
      live = cloneState(state);
      const quiet = positions[positions.length - 1].quiet;
      for (const e of events) {
        // a tray refill that changed nothing, or the end of a turn, is bookkeeping, not news
        quiet.push(e.e === 'turn_end' || (e.e === 'tray_refill' && sameList(e.tray, live.tray)));
        if (!applyEvent(live, e, { decision })) unknown.add(e.e);
        if (e.e === 'turn_start') turnOwner = e.p;
        if (e.e === 'round_end') turnOwner = null;
      }
    }
  }

  // mark turn starts for positions that had no snapshot of their own
  for (let i = 1; i < positions.length; i++) {
    const prev = positions[i - 1];
    if (prev.events.some(e => e.e === 'turn_start')) positions[i].turnStart = true;
  }

  if (unknown.size) warnings.push(`Events this viewer does not know: ${[...unknown].join(', ')}.`);

  return {
    header,
    cards,
    positions,
    dealEvents,
    players: header.config.players,
    coop: !!header.config.plugins?.coop_goals,
    finalScores: lastEvent(lines, 'final_scoring')?.scores ?? null,
    warnings,
  };
}

const sameList = (a, b) => a.length === b.length && a.every((x, i) => x === b[i]);

function lastEvent(lines, name) {
  for (let i = lines.length - 1; i >= 0; i--) if (lines[i].t === 'event' && lines[i].e === name) return lines[i];
  return null;
}

/** Index of the first position of each turn, in order: [{ index, round, turn_no, player }]. */
export function turnIndex(replay) {
  const out = [];
  for (const p of replay.positions) {
    if (p.turnStart && p.turn != null) out.push({ index: p.index, round: p.round, turn_no: p.turn_no, player: p.turn });
  }
  return out;
}

/** Index of the first position of each round: [{ index, round }]. Setup is round 0. */
export function roundIndex(replay) {
  const out = [{ index: 0, round: 0 }];
  for (const p of replay.positions) {
    const r = p.state.phase === 'setup' ? 0 : p.round;
    if (r !== out[out.length - 1].round && r >= 1 && r <= 4) out.push({ index: p.index, round: r });
  }
  return out;
}
