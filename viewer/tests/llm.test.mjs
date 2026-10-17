// The language-model helpers: reply anatomy, plans, word diffs and flags.

import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseReply, parsePlan, diffWords, planDiff, cutOffReply, replyCuts, coachFlagged, modelIndex, talkLog, digestRead, tokenTotals, excerpt } from '../app/viewer/llm.js';
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

test('SAY and TO COACH lines: the last of each, and never read as the answer', () => {
  const r = parseReply('I take fish.\nANSWER: 2\nSAY: my answer is wetland birds\nSAY: second thought\n**TO COACH:** agreed');
  assert.equal(r.answer.value, '2');
  assert.equal(r.say.text, 'SAY: second thought');
  assert.equal(r.toCoach.text, '**TO COACH:** agreed');
  assert.equal(parseReply('ANSWER: 1').say, null);
});

test('cut off per reply from usage_all and limits', () => {
  const d = { kind: 'action', info: { replies: ['a', 'b'], usage_all: [{ completion_tokens: 2100 }, { completion_tokens: 12 }], limits: [2100, 300], usage: { completion_tokens: 12 } } };
  assert.deepEqual(replyCuts({ settings: { max_tokens: 1500, plan: true } }, d), [true, false]);
  delete d.info.usage_all;   // an older log: only the last reply can be judged
  assert.deepEqual(replyCuts({ settings: { max_tokens: 1500, plan: true } }, d), [false, false]);
});

test('coach flagged: anything but "No problems"', () => {
  assert.equal(coachFlagged('- No problems: the plan fits the position.'), false);
  assert.equal(coachFlagged('No problems.'), false);
  assert.equal(coachFlagged('- Too many cards, no food.'), true);
  assert.equal(coachFlagged(null), false);
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
      // table talk and the harness: only at action decisions, and the flags follow the logged fields
      assert.equal(e.flags.said, !!info.said);
      assert.equal(e.flags.answeredCoach, !!info.to_coach);
      assert.equal(e.flags.readTalk, !!info.aux?.some(a => a.role === 'digest'));
      if (info.said || info.aux || info.to_coach) assert.equal(e.d.kind, 'action', `talk or harness fields off an action at ${e.d.seq}`);
      if (info.aux) {
        assert.equal(e.coach, info.coach ?? null);
        assert.equal(e.digest, info.digest ?? null);
        // a digest comes first, and only when someone else said something since this seat's last one
        const roles = info.aux.map(a => a.role);
        assert.ok(roles.indexOf('digest') <= 0, `digest not first at ${e.d.seq}`);
        if (e.flags.readTalk) assert.ok(digestRead(entries, e).length > 0, `digest with nothing new at ${e.d.seq}`);
      }
      if (Array.isArray(info.usage_all)) assert.equal(e.cuts.length, info.replies.length);
      if (e.flags.planChanged) assert.equal(e.d.kind, 'action');
      // the reply the viewer shows keeps all the text apart from the tags and the plan block
      e.replies.forEach((r, i) => {
        const raw = info.replies[i] || '';
        assert.ok(!r.body.includes('<think>'));
        if (!r.plan) assert.equal(r.body, raw.replace(/<\/?think>/g, '').trim());
      });
    }
    // the talk log is every said, in order; token totals count every call
    assert.deepEqual(talkLog(entries).map(m => m.text), entries.filter(e => e.d.info.said).map(e => e.d.info.said));
    for (const p of new Set(entries.map(e => e.seatNo))) {
      const t = tokenTotals(entries, p);
      const aux = entries.filter(e => e.seatNo === p).flatMap(e => e.d.info.aux || []);
      assert.equal((t.coach?.calls || 0) + (t.digest?.calls || 0), aux.length);
    }
  });
}
