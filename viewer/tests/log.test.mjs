import test from 'node:test';
import assert from 'node:assert/strict';
import { join } from 'node:path';
import { buildReplay, turnIndex, roundIndex } from '../app/viewer/replay/log.js';
import { SAMPLES, readLog } from './helpers.mjs';

const load = name => buildReplay(readLog(join(SAMPLES, name)));

test('positions: one per decision plus the final state', () => {
  const r = load('coop-3p-greedy-every-decision.json');
  assert.equal(r.players, 3);
  assert.equal(r.coop, true);
  assert.equal(r.positions.length, 433);
  assert.equal(r.positions[0].decision.seq, 1);
  assert.equal(r.positions.at(-1).decision, null);
  assert.equal(r.positions.at(-1).state.phase, 'over');
  assert.ok(r.positions.every(p => p.exact));
  assert.equal(r.finalScores.team_total, 231);
  assert.deepEqual(r.warnings, []);
});

test('native .jsonl.gz and exported .json give the same replay', () => {
  const a = load('coop-2p-haiku-vs-greedy.json');
  const b = load('coop-2p-haiku-vs-greedy.jsonl.gz');
  assert.equal(a.positions.length, b.positions.length);
  assert.deepEqual(a.positions[100].state, b.positions[100].state);
  assert.equal(a.cards.birds['2'].name, b.cards.birds['2'].name);
});

test('per-turn logs: positions inside a turn are derived, turn starts are exact', () => {
  const r = load('baseline-2p-greedy-per-turn.json');
  assert.equal(r.coop, false);
  const derived = r.positions.filter(p => !p.exact);
  assert.ok(derived.length > 100);
  assert.ok(r.positions.filter(p => p.turnStart && p.turn != null).every(p => p.exact));
  // a derived position still has a complete board
  assert.equal(derived[0].state.players.length, 2);
});

test('turn and round indexes', () => {
  const r = load('coop-3p-greedy-every-decision.json');
  const turns = turnIndex(r);
  assert.equal(turns.length, 3 * (8 + 7 + 6 + 5));
  assert.deepEqual(turns.slice(0, 4).map(t => t.player), [2, 0, 1, 2]);
  assert.deepEqual(roundIndex(r).map(x => x.round), [0, 1, 2, 3, 4]);
});
