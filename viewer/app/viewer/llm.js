// Reading a language-model seat's decisions: the anatomy of a reply, plans and their
// changes, flags (fallback, retry, cut off, plan changed) and a search index. No DOM here.
//
// Log format section 6: decision.info for an `llm` seat has `replies` (one, or two when
// the first had no valid answer), optional `thinking` (parallel to replies), `chosen`
// (1-based), `fallback`, `usage` and `prompt`; plan seats add `plan` and `plan_updated`.

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
 * - `body`: the reasoning and the ANSWER line, without the plan block.
 * - `answer`: { text, value, start, end } for the last ANSWER line in `body` (start/end
 *   index into `body`), or null.
 * - `plan`: the text of a PLAN: … END PLAN block, or null.
 */
export function parseReply(raw) {
  let s = String(raw ?? '');
  const hidden = [];
  s = s.replace(/<think>([\s\S]*?)<\/think>/g, (m, t) => { if (t.trim()) hidden.push(t.trim()); return ''; });
  s = s.replace(/<\/?think>/g, '');

  let plan = null;
  const pm = /^[ \t]*[*_#]*\s*PLAN[*_]*\s*:/m.exec(s);
  if (pm) {
    const rest = s.slice(pm.index + pm[0].length);
    const end = /^[ \t]*[*_]*END PLAN\b.*$/im.exec(rest);
    plan = (end ? rest.slice(0, end.index) : rest).trim() || null;
    s = s.slice(0, pm.index) + (end ? rest.slice(end.index + end[0].length) : '');
  }
  const body = s.trim();

  let answer = null;
  const re = /ANSWER\s*[:=]?\s*\**\s*([^\n]*)/gi;
  for (let m; (m = re.exec(body));) {
    answer = { text: m[0].trim(), value: m[1].replace(/\*+/g, '').trim(), start: m.index, end: m.index + m[0].length };
  }
  return { hidden, body, answer, plan };
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
 * @returns {{ index, d, seat, replies, thinking, flags, plan, search }}
 */
export function modelEntry(header, position) {
  const d = position.decision, seatNo = d.player, seat = header.seats[seatNo], info = d.info || {};
  const replies = (info.replies || []).map(parseReply);
  // hidden thinking: the separate list when the endpoint returned it, else <think> pairs
  const thinking = replies.map((r, i) => [info.thinking?.[i], ...r.hidden].filter(Boolean).join('\n\n') || null);
  const cut = cutOffReply(seat, d);
  const hasPlan = !!seat.settings?.plan && ('plan' in info || 'plan_updated' in info);
  const plan = hasPlan ? { before: info.plan ?? null, after: info.plan_updated ?? null, ...planDiff(info.plan, info.plan_updated) } : null;
  const flags = {
    fallback: !!info.fallback,
    retry: replies.length > 1,
    cutoff: cut >= 0,
    planChanged: !!plan && plan.changed.length > 0,
  };
  // what search looks through: the reasoning and hidden thinking, not the plan blocks (every
  // plan says "Round goal:", which would drown a search for the words)
  const text = [...replies.map(r => r.body), ...thinking].filter(Boolean).join('\n\n');
  return { index: position.index, d, seatNo, seat, replies, thinking, cut, flags, plan, text, search: text.toLowerCase(), round: position.round, turn_no: position.turn_no };
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
