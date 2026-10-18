// Reading a language-model seat's decisions: the anatomy of a reply, plans and their
// changes, flags (fallback, retry, cut off, plan changed) and a search index. No DOM here.
//
// Log format section 6: decision.info for an `llm` seat has `replies` (one, or two when
// the first had no valid answer), optional `thinking` (parallel to replies), `chosen`
// (1-based), `fallback`, `usage` (`usage_all` and `limits` per reply in newer logs) and
// `prompt`; plan seats add `plan` and `plan_updated`. At action decisions, talk seats add
// `said`, and coach or digest seats add `aux` (the extra calls before the main one, in
// order), `coach`, `digest` and `to_coach`. Every one of these is optional.

export const PLAN_FIELDS = ['Engine', 'Bonus target', 'Round goal', 'Need next', 'Pivot if'];

const FIELD_LINE = new RegExp(`^\\s*[*_]*(${PLAN_FIELDS.join('|')})[*_]*\\s*:\\s*(.*)$`, 'i');
const CANON = Object.fromEntries(PLAN_FIELDS.map(f => [f.toLowerCase(), f]));

/** A plan seat at an action decision gets this many tokens more than max_tokens. */
export const PLAN_EXTRA_TOKENS = 600;
/** "Within a few tokens" of the limit counts as cut off (finish_reason can't be trusted). */
const CUT_OFF_MARGIN = 8;

export const isLlmSeat = (header, p) => typeof p === 'number' && header.seats?.[p]?.type === 'llm';
export const llmSeats = header => (header.seats || []).map((s, p) => (s.type === 'llm' ? p : null)).filter(p => p != null);

/**
 * Split one raw reply into its parts.
 * - `hidden`: text inside real <think>…</think> pairs (hidden thinking).
 * - A lone <think> with no closing tag is a server quirk: the tag goes, the text stays.
 * - `body`: the reasoning and the ANSWER line, without the plan blocks.
 * - `answer`: { text, value, start, end } for the last ANSWER line in `body` (start/end
 *   index into `body`), or null.
 * - `plan`: the text of the last PLAN: … END PLAN block, or null.
 */
export function parseReply(raw) {
  let s = String(raw ?? '');
  const hidden = [];
  s = s.replace(/<think>([\s\S]*?)<\/think>/g, (m, t) => { if (t.trim()) hidden.push(t.trim()); return ''; });
  s = s.replace(/<\/?think>/g, '');

  // every plan block goes; the last one is the plan. Like the agent, a block without END PLAN
  // ends where an ANSWER, the next PLAN:, a SAY: or a TO COACH: line begins.
  let plan = null;
  const start = /^[ \t]*[*_#]*\s*PLAN[*_]*\s*:/m;
  for (let pm; (pm = start.exec(s));) {
    const rest = s.slice(pm.index + pm[0].length);
    const ends = [/^[ \t]*[*_]*END PLAN\b.*$/im, /ANSWER\s*[:=]/i, start, /^[*#\s]*(?:SAY|TO COACH):/m]
      .map(re => re.exec(rest)).filter(Boolean);
    const end = ends.sort((a, b) => a.index - b.index)[0];
    const closed = end && /END PLAN/i.test(end[0]);
    plan = (end ? rest.slice(0, end.index) : rest).trim() || null;
    s = s.slice(0, pm.index) + (end ? rest.slice(end.index + (closed ? end[0].length : 0)) : '');
  }
  const body = s.trim();

  // like the agent, read the answer with SAY: and TO COACH: lines left out
  const talk = [...allLines(body, 'SAY'), ...allLines(body, 'TO COACH')];
  const inTalk = i => talk.some(t => i >= t.start && i < t.end);
  let answer = null;
  const re = /ANSWER\s*[:=]?\s*\**\s*([^\n]*)/gi;
  for (let m; (m = re.exec(body));) {
    if (inTalk(m.index)) continue;
    answer = { text: m[0].trim(), value: m[1].replace(/\*+/g, '').trim(), start: m.index, end: m.index + m[0].length };
  }
  return { hidden, body, answer, plan, say: allLines(body, 'SAY').pop() ?? null, toCoach: allLines(body, 'TO COACH').pop() ?? null };
}

/** The lines of `body` starting with `<label>:` (as the agent finds SAY: and TO COACH:), as [{ text, start, end }]. */
function allLines(body, label) {
  const out = [], re = new RegExp(`^[*#\\s]*${label}:.*$`, 'gm');
  for (let m; (m = re.exec(body));) out.push({ text: m[0].trim(), start: m.index, end: m.index + m[0].length });
  return out;
}

/** A plan's five fields (missing ones are ''), plus any lines that belong to none. */
export function parsePlan(text) {
  const fields = Object.fromEntries(PLAN_FIELDS.map(f => [f, '']));
  const extra = [];
  let current = null;
  for (const line of String(text ?? '').split('\n')) {
    const m = FIELD_LINE.exec(line);
    if (m) { current = CANON[m[1].toLowerCase()]; fields[current] = m[2].trim(); }
    else if (!line.trim()) continue;
    else if (current) fields[current] += ` ${line.trim()}`;
    else extra.push(line.trim());
  }
  return { fields, extra: extra.join(' ') };
}

const words = s => String(s ?? '').split(/\s+/).filter(Boolean);
const squash = s => words(s).join(' ').toLowerCase();

/**
 * Word-level diff: [{ op: 'same' | 'del' | 'ins', text }], consecutive words of one kind
 * joined. Longest common subsequence over words, ignoring case for matching.
 */
export function diffWords(a, b) {
  const A = words(a), B = words(b), n = A.length, m = B.length;
  const key = w => w.toLowerCase();
  const L = Array.from({ length: n + 1 }, () => new Uint16Array(m + 1));
  for (let i = n - 1; i >= 0; i--) {
    for (let j = m - 1; j >= 0; j--) {
      L[i][j] = key(A[i]) === key(B[j]) ? L[i + 1][j + 1] + 1 : Math.max(L[i + 1][j], L[i][j + 1]);
    }
  }
  const out = [];
  const push = (op, w) => {
    const last = out[out.length - 1];
    if (last && last.op === op) last.text += ` ${w}`; else out.push({ op, text: w });
  };
  let i = 0, j = 0;
  while (i < n && j < m) {
    if (key(A[i]) === key(B[j])) { push('same', B[j]); i++; j++; }
    else if (L[i + 1][j] >= L[i][j + 1]) push('del', A[i++]);
    else push('ins', B[j++]);
  }
  while (i < n) push('del', A[i++]);
  while (j < m) push('ins', B[j++]);
  return out;
}

/**
 * Plan shown vs plan written, field by field:
 * { fields: [{ name, before, after, changed, ops }], changed: [names], first: bool }.
 * `after` null (no plan written) gives no changes.
 */
export function planDiff(before, after) {
  const A = parsePlan(before).fields;
  const B = after == null ? null : parsePlan(after).fields;
  const fields = PLAN_FIELDS.map(name => {
    const b = A[name], a = B ? B[name] : b;
    const changed = !!B && squash(a) !== squash(b);
    return { name, before: b, after: a, changed, ops: changed ? diffWords(b, a) : null };
  });
  return { fields, changed: fields.filter(f => f.changed).map(f => f.name), first: before == null && after != null };
}

/** The token limit of a decision's first call (log format section 6, and plan seats' extra room). */
export function tokenLimit(seat, decision) {
  const st = seat?.settings || {};
  if (st.max_tokens == null) return null;
  return st.max_tokens + (st.plan && decision.kind === 'action' ? PLAN_EXTRA_TOKENS : 0);
}

/**
 * Which replies were cut off, one boolean per reply. Newer logs give `usage_all` and `limits`
 * per reply, so each can be judged; older ones only allow cutOffReply() on the last.
 */
export function replyCuts(seat, decision) {
  const info = decision.info || {}, n = info.replies?.length || 0;
  if (Array.isArray(info.usage_all) && Array.isArray(info.limits)) {
    return Array.from({ length: n }, (_, i) => isCut(info.usage_all[i], info.limits[i]));
  }
  const last = cutOffReply(seat, decision);
  return Array.from({ length: n }, (_, i) => i === last);
}

/** A call whose completion_tokens reaches its limit was cut off (format section 6). */
const isCut = (usage, limit) => usage?.completion_tokens != null && limit != null && usage.completion_tokens >= limit;

/** The coach's way of saying all is well (wingsim/prompts/coach.md). */
const NO_PROBLEMS = /^[\s\-*•]*no problems\b/i;
export const coachFlagged = notes => !!notes && !NO_PROBLEMS.test(notes);

/**
 * Whether an extra call's notes were shortened: the notes are the tail of the reply, so reply
 * text left after them means the agent cut them (at 600 characters in llm.py) and the player
 * saw only this much.
 */
export function notesCut(call) {
  if (!call?.notes || !call.reply) return false;
  const reply = String(call.reply).replace(/<think>[\s\S]*?<\/think>/g, '');
  const i = reply.lastIndexOf(call.notes);
  return i >= 0 && reply.slice(i + call.notes.length).trim() !== '';
}

/**
 * Which reply looks cut off, judged from usage.completion_tokens against the limit, or -1.
 * `usage` covers the last call only (see FORMAT-REQUESTS.md, L2), so only the last reply
 * can be judged; and only against the first call's limit (L3).
 */
export function cutOffReply(seat, decision) {
  const info = decision.info, limit = tokenLimit(seat, decision);
  const used = info?.usage?.completion_tokens;
  if (limit == null || used == null || !info.replies?.length) return -1;
  return used >= limit - CUT_OFF_MARGIN ? info.replies.length - 1 : -1;
}

/**
 * Everything the model panel needs about one decision of a language-model seat.
 * @returns {{ index, d, seat, replies, thinking, cuts, flags, plan, aux, said, toCoach, coach, digest, search }}
 */
export function modelEntry(header, position) {
  const d = position.decision, seatNo = d.player, seat = header.seats[seatNo], info = d.info || {};
  const replies = (info.replies || []).map(parseReply);
  // hidden thinking: the separate list when the endpoint returned it, else <think> pairs
  const thinking = replies.map((r, i) => [info.thinking?.[i], ...r.hidden].filter(Boolean).join('\n\n') || null);
  const cuts = replyCuts(seat, d);
  // the extra calls before the main one (coach, digest), with their notes up front
  const aux = (info.aux || []).map(a => {
    const r = parseReply(a.reply);
    return {
      role: a.role, notes: a.notes ?? null, prompt: a.prompt ?? null, reply: a.reply ?? '', body: r.body,
      thinking: [a.thinking, ...r.hidden].filter(Boolean).join('\n\n') || null,
      usage: a.usage || {}, limit: a.limit ?? null, cut: isCut(a.usage, a.limit), notesCut: notesCut(a),
    };
  });
  const coachCall = aux.find(a => a.role === 'coach');
  const hasPlan = !!seat.settings?.plan && ('plan' in info || 'plan_updated' in info);
  const plan = hasPlan ? { before: info.plan ?? null, after: info.plan_updated ?? null, ...planDiff(info.plan, info.plan_updated) } : null;
  const said = info.said ?? null, toCoach = info.to_coach ?? null;
  const coach = info.coach ?? coachCall?.notes ?? null;
  const flags = {
    fallback: !!info.fallback,
    retry: replies.length > 1,
    cutoff: cuts.some(Boolean) || aux.some(a => a.cut),
    planChanged: !!plan && plan.changed.length > 0,
    said: !!said,
    coachFlagged: !!coachCall && coachFlagged(coach),
    readTalk: aux.some(a => a.role === 'digest'),
    answeredCoach: !!toCoach,
  };
  // what search looks through: the reasoning and hidden thinking, what it said, and every extra
  // call; not the plan blocks (every plan says "Round goal:", which would drown a search for the words)
  const text = [...replies.map(r => r.body), ...thinking, said, toCoach,
    ...aux.flatMap(a => [a.notes, a.body, a.thinking])].filter(Boolean).join('\n\n');
  return {
    index: position.index, d, seatNo, seat, replies, thinking, cuts, cut: cuts.lastIndexOf(true), flags, plan, aux,
    said, toCoach, coach, digest: info.digest ?? aux.find(a => a.role === 'digest')?.notes ?? null,
    text, search: text.toLowerCase(), round: position.round, turn_no: position.turn_no,
  };
}

/** Every language-model decision in a replay, in order. */
export function modelIndex(replay) {
  const out = [];
  for (const pos of replay.positions) {
    if (pos.decision && isLlmSeat(replay.header, pos.decision.player) && pos.decision.info?.replies) {
      out.push(modelEntry(replay.header, pos));
    }
  }
  return out;
}

/** A short excerpt of `text` around the first match of `query` (lowercase), or null. */
export function excerpt(text, query, width = 70) {
  const i = text.toLowerCase().indexOf(query);
  if (i < 0) return null;
  const a = Math.max(0, i - width), b = Math.min(text.length, i + query.length + width);
  return `${a > 0 ? '…' : ''}${text.slice(a, b).replace(/<\/?think>/g, '').replace(/\s+/g, ' ').trim()}${b < text.length ? '…' : ''}`;
}

/** Every message left for the table, oldest first: [{ index, round, turn_no, seatNo, text }]. */
export function talkLog(entries) {
  return entries.filter(e => e.said).map(e => ({ index: e.index, round: e.round, turn_no: e.turn_no, seatNo: e.seatNo, text: e.said }));
}

/**
 * The messages a digest at this entry read: what other seats said since this seat's previous
 * digest (wingsim makes a digest only when there is something new). Rebuilt from `said`.
 */
export function digestRead(entries, entry) {
  if (!entry.flags.readTalk) return [];
  const mine = entries.filter(e => e.seatNo === entry.seatNo && e.index < entry.index && e.flags.readTalk);
  const since = mine.length ? mine[mine.length - 1].index : -1;
  return talkLog(entries).filter(m => m.index > since && m.index < entry.index && m.seatNo !== entry.seatNo);
}

/**
 * Token use of one seat over the game: main replies (usage_all, or usage) and each extra-call
 * role: { main: {calls, prompt, completion, cost}, coach: {…}, digest: {…} }.
 */
export function tokenTotals(entries, seatNo) {
  const blank = () => ({ calls: 0, prompt: 0, completion: 0, cost: 0, cut: 0 });
  const out = { main: blank() };
  const add = (key, u, cut) => {
    const t = (out[key] ||= blank());
    t.calls++; t.prompt += u?.prompt_tokens || 0; t.completion += u?.completion_tokens || 0; t.cost += Number(u?.cost) || 0;
    if (cut) t.cut++;
  };
  for (const e of entries) {
    if (e.seatNo !== seatNo) continue;
    const info = e.d.info;
    const usages = Array.isArray(info.usage_all) ? info.usage_all : info.usage ? [info.usage] : [];
    usages.forEach((u, i) => add('main', u, Array.isArray(info.usage_all) ? e.cuts[i] : i === usages.length - 1 && e.cut >= 0));
    for (const a of e.aux) add(a.role, a.usage, a.cut);
  }
  return out;
}
