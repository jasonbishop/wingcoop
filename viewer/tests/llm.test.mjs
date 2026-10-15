// The language-model helpers: reply anatomy, plans, word diffs and flags.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseReply, parsePlan, diffWords, planDiff, cutOffReply, modelIndex, excerpt } from '../app/viewer/llm.js';
import { buildReplay } from '../app/viewer/replay/log.js';
import { logFiles, readLog } from './helpers.mjs';

test('a lone <think> is dropped and its text kept', () => {
  const r = parseReply('<think>I will take the fish.\n\nANSWER: 2');
  assert.deepEqual(r.hidden, []);
  assert.equal(r.body, 'I will take the fish.\n\nANSWER: 2');
  assert.equal(r.answer.value, '2');
  assert.equal(r.body.slice(r.answer.start, r.answer.end), 'ANSWER: 2');
});

test('a <think> pair is hidden thinking', () => {
  const r = parseReply('<think>secret plan</think>Visible.\nANSWER: 1');
  assert.deepEqual(r.hidden, ['secret plan']);
  assert.equal(r.body, 'Visible.\nANSWER: 1');
});

test('the plan block is split off, and a "plan:" in the reasoning is not it', () => {
  const raw = 'Looking at "Need next" in my plan: "fish".\nANSWER: 1\n\nPLAN:\nEngine: A\nBonus target: B\nRound goal: C\nNeed next: D\nPivot if: E\nEND PLAN';
  const r = parseReply(raw);
  assert.equal(r.answer.value, '1');
  assert.match(r.body, /in my plan: "fish"/);
  assert.equal(r.plan, 'Engine: A\nBonus target: B\nRound goal: C\nNeed next: D\nPivot if: E');
  assert.deepEqual(parsePlan(r.plan).fields, { Engine: 'A', 'Bonus target': 'B', 'Round goal': 'C', 'Need next': 'D', 'Pivot if': 'E' });
});

test('the last ANSWER line counts; none gives null', () => {
  assert.equal(parseReply('ANSWER: 1 ... no wait\nANSWER: 3').answer.value, '3');
  assert.equal(parseReply('I could not decide').answer, null);
  assert.equal(parseReply('ANSWER: 1, 4').answer.value, '1, 4');
});

test('word diff', () => {
  assert.deepEqual(diffWords('more bowl nest birds', 'more cavity nest birds now'), [
    { op: 'same', text: 'more' }, { op: 'del', text: 'bowl' }, { op: 'ins', text: 'cavity' },
    { op: 'same', text: 'nest birds' }, { op: 'ins', text: 'now' },
  ]);
  assert.deepEqual(diffWords('', 'new'), [{ op: 'ins', text: 'new' }]);
});

test('plan diff field by field', () => {
  const before = 'Engine: Wood Duck\nBonus target: Gardener\nRound goal: eggs\nNeed next: seed\nPivot if: never';
  const after = 'Engine: Wood Duck\nBonus target: Gardener\nRound goal: eggs\nNeed next: fruit\nPivot if: never';
  const d = planDiff(before, after);
  assert.deepEqual(d.changed, ['Need next']);
  assert.equal(d.first, false);
  assert.deepEqual(planDiff(null, after).changed.length, 5);
  assert.equal(planDiff(null, after).first, true);
  assert.deepEqual(planDiff(before, null).changed, []);
  // spacing and case alone are not a change
  assert.deepEqual(planDiff(before, before.replace('Wood Duck', 'wood  duck')).changed, []);
});

test('cut off is judged on the last reply against max_tokens (+600 at plan actions)', () => {
  const seat = { settings: { max_tokens: 1500, plan: true } };
  const d = (kind, used, n = 1) => ({ kind, info: { replies: Array(n).fill('x'), usage: { completion_tokens: used } } });
  assert.equal(cutOffReply(seat, d('action', 2100)), 0);
  assert.equal(cutOffReply(seat, d('action', 1500)), -1);
  assert.equal(cutOffReply(seat, d('take_die', 1499)), 0);
  assert.equal(cutOffReply(seat, d('take_die', 1499, 2)), 1);
  assert.equal(cutOffReply({ settings: {} }, d('take_die', 1499)), -1);
});

test('excerpt', () => {
  assert.equal(excerpt('aaa round goal bbb', 'round goal', 3), '…aa round goal bb…');
  assert.equal(excerpt('nothing', 'x'), null);
});

// Every log with language-model seats: entries are consistent with the decision lines.
for (const file of logFiles()) {
  const log = readLog(file);
  if (!log.lines[0].seats?.some(s => s.type === 'llm')) continue;
  test(`model entries: ${file.split('/').slice(-3).join('/')}`, () => {
    const replay = buildReplay(log, log.cards);
    const entries = modelIndex(replay);
    assert.ok(entries.length > 0);
    for (const e of entries) {
      const info = e.d.info;
      assert.equal(e.flags.retry, info.replies.length > 1);
      assert.equal(e.flags.fallback, info.fallback === 'random');
      if (!info.fallback) assert.equal(info.chosen, e.d.choice + 1, `chosen vs choice at ${e.d.seq}`);
      if (info.thinking) assert.equal(info.thinking.length, info.replies.length);
      if (e.flags.planChanged) assert.equal(e.d.kind, 'action');
      // the reply the viewer shows keeps all the text apart from the tags and the plan block
      e.replies.forEach((r, i) => {
        const raw = info.replies[i] || '';
        assert.ok(!r.body.includes('<think>'));
        if (!r.plan) assert.equal(r.body, raw.replace(/<\/?think>/g, '').trim());
      });
    }
  });
}
