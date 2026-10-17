// The language model's side of a game: what it was shown, what it replied, what it chose
// and how its plan changed. Three views share one search and one set of filters:
//
//   ModelPanel    the Model tab: plan timeline, search and filters, and the model decision
//                 at (or just before) the replay cursor
//   Transcript    every decision in order, readable top to bottom without the table
//   SideDrawer    beside the panel: the table talk as a chat, each seat's thread with its
//                 coach, and the system prompts (rules summary), to compare with its reasoning
//
// decisionCard() draws one decision and is also used by the Step tab. At an action decision of
// a seat with a coach or digest it shows the calls in the order they were made.

import { el, esc, rich } from './rich.js';
import { modelIndex, llmSeats, excerpt, parsePlan, tokenLimit, talkLog, digestRead, tokenTotals, PLAN_FIELDS } from '../llm.js';
import { DECISION_TITLES } from '../describe.js';
import { keptBirds } from '../replay/log.js';
import { seatCss, seatLabel, playerName } from '../data.js';

const $ = id => document.getElementById(id);

export const FILTERS = [
  { key: 'fallback', label: 'Fallbacks', one: 'fallback', icon: '⚠', title: "The model's answer couldn't be read, so a random option was played" },
  { key: 'retry', label: 'Retries', one: 'retry', icon: '↻', title: 'The first reply had no valid answer and the model was asked again' },
  { key: 'cutoff', label: 'Cut off', one: 'cut off', icon: '✂', title: 'The reply used all the tokens it was allowed, so it probably stopped mid-thought' },
  { key: 'planChanged', label: 'Plan changed', one: 'plan changed', icon: '✎', title: 'The model rewrote at least one line of its plan' },
  // only offered when a seat has the feature (`need`); shown in the decision itself, so no badge
  { key: 'said', label: 'Said something', one: 'said', icon: '❝', need: 'talk', badge: false, title: 'It left a message for the table' },
  { key: 'coachFlagged', label: 'Coach flagged', one: 'coach flagged', icon: '⚑', need: 'coach', title: 'The coach pointed out a problem (anything but "No problems")' },
  { key: 'readTalk', label: 'Read new talk', one: 'read talk', icon: '⇄', need: 'digest', badge: false, title: 'A digest call read what the others had said since last time' },
  { key: 'answeredCoach', label: 'Answered coach', one: 'answered coach', icon: '↩', need: 'coach', badge: false, title: 'It replied to its coach (TO COACH:)' },
];

/** Which harness features any language-model seat of this game has: { talk, coach, digest }. */
export function seatFeatures(header) {
  const on = key => llmSeats(header).some(p => !!header.seats[p].settings?.[key]);
  return { talk: on('talk'), coach: on('coach'), digest: on('digest') };
}
const filtersFor = features => FILTERS.filter(f => !f.need || features[f.need]);

/** Escape text and wrap every match of `q` (lowercase) in <mark>. */
export function marked(text, q) {
  const s = String(text ?? '');
  if (!q) return esc(s);
  const low = s.toLowerCase();
  let out = '', i = 0, j;
  while ((j = low.indexOf(q, i)) >= 0) {
    out += `${esc(s.slice(i, j))}<mark>${esc(s.slice(j, j + q.length))}</mark>`;
    i = j + q.length;
  }
  return out + esc(s.slice(i));
}

/** marked(), plus the bit of Markdown the models use: **bold** and *italics*. */
function prose(text, q) {
  return marked(text, q)
    .replace(/\*\*([^*\n]+?)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[\s(])\*([^*\s][^*\n]*?)\*(?=[\s.,;:!?)]|$)/gm, '$1<em>$2</em>');
}

const plural = (n, w) => `${n} ${w}${n === 1 ? '' : 's'}`;
const wordCount = s => String(s).split(/\s+/).filter(Boolean).length;

/** "Setup" or "Round 2 · turn 9", for a model entry or a position. */
export function whereText(x) {
  return !x.round ? 'Setup' : `Round ${x.round} · turn ${x.turn_no + 1}`;
}

function badges(entry) {
  return FILTERS.filter(f => f.badge !== false && entry.flags[f.key]).map(f =>
    el('span.badge', { class: `b-${f.key}`, title: f.title }, `${f.icon} ${f.one}`));
}

/**
 * The keep-birds decision as the 5 dealt birds, the kept ones ticked ('?' if kept at random),
 * instead of its 32 subsets. `numbered`: number them 1-5, as a `compact` language-model seat's
 * prompt does (it answers with bird numbers). Null for any other decision.
 */
export function dealtBirdList(d, book, { random = !!d.info?.fallback, numbered = false } = {}) {
  const k = keptBirds(d);
  if (!k) return null;
  return el('ol.options.dealt', {}, k.dealt.map((id, i) => {
    const kept = k.kept.has(id);
    return el('li', { class: kept ? (random ? 'chosen random' : 'chosen') : '', title: kept ? (random ? 'Kept at random' : 'Kept') : 'Not kept' },
      el('span.mark', {}, kept ? (random ? '?' : '✓') : ''),
      el('span.label', {}, numbered ? el('span.num', {}, `${i + 1}. `) : null, book ? book.birdName(id) : `bird ${id}`),
      kept ? el('span.val', {}, random ? 'kept at random' : 'kept') : null);
  }));
}

/** Does this seat's prompt show the dealt birds by number rather than the 32 options? */
export const birdsByNumber = seat => !!seat?.settings?.compact;

function optionList(entry, book) {
  const d = entry.d, random = entry.flags.fallback;
  const numbered = birdsByNumber(entry.seat);
  const dealt = dealtBirdList(d, book, { random, numbered });
  // the chosen row keeps its number too: it is what the model's ANSWER refers to
  const row = i => el('li', { class: i === d.choice ? (random ? 'chosen random' : 'chosen') : '' },
    el('span.mark', {}, i === d.choice ? (random ? '?' : '✓') : `${i + 1}`),
    el('span.label', {}, i === d.choice ? el('span.num', {}, `${i + 1}. `) : null, el('span', { html: rich(d.labels?.[i] ?? JSON.stringify(d.options[i])) })),
    i === d.choice && random ? el('span.val', { title: 'Played at random, not chosen by the model' }, 'random') : null);
  if (d.options.length <= 8) return [el('ol.options', {}, d.options.map((_, i) => row(i)))];
  const all = el('details', {}, el('summary', {}, `All ${d.options.length} options`), el('ol.options', {}, d.options.map((_, i) => row(i))));
  if (!dealt) return [el('ol.options', {}, row(d.choice)), all];
  if (numbered) return [el('p.hint', {}, 'The model was shown these 5 birds and answered with their numbers.'), dealt, all];
  return [dealt, el('p.hint', {}, `The model was shown all ${d.options.length} combinations and answered with an option number:`), el('ol.options', {}, row(d.choice)), all];
}

function replyNodes(entry, q, { titled = true } = {}) {
  const out = [], n = entry.replies.length;
  entry.replies.forEach((r, i) => {
    const tags = [];
    if (i > 0) tags.push(el('span.badge.b-retry', { title: 'Asked again because the reply before had no valid answer' }, 'retry'));
    if (i < n - 1) tags.push(el('span.badge.b-quiet', { title: 'The agent could not read an answer from this reply, so it asked again' }, 'not accepted'));
    if (entry.cuts[i]) tags.push(el('span.badge.b-cutoff', { title: `It used ${replyUsage(entry, i)?.completion_tokens} of ${replyLimit(entry, i)} tokens` }, '✂ cut off'));
    if (!r.answer) tags.push(el('span.badge.b-quiet', {}, 'no ANSWER line'));
    if (titled || n > 1 || tags.length) out.push(el('div.rhead', {}, el('b', {}, n > 1 ? (i === 0 ? 'First reply' : 'Second reply') : 'Reply'), ...tags));
    if (entry.thinking[i]) {
      out.push(el('details.thinking', {}, el('summary', {}, `Hidden thinking · ${plural(wordCount(entry.thinking[i]), 'word')}`),
        el('div.reply.hidden-thought', { html: prose(entry.thinking[i], q) })));
    }
    out.push(el('div.reply', { html: r.body ? highlighted(r, q) : '<i>(empty reply)</i>' }));
    if (r.plan) out.push(el('details.rawplan', {}, el('summary', {}, 'Plan block as written'), el('div.reply', { html: marked(r.plan, q) })));
  });
  return out;
}

/** A reply body with its ANSWER, SAY and TO COACH lines picked out. */
function highlighted(r, q) {
  const marks = [[r.answer, 'answer'], [r.say, 'sayline'], [r.toCoach, 'coachline']].filter(([m]) => m)
    .sort((a, b) => a[0].start - b[0].start);
  let html = '', at = 0;
  for (const [m, cls] of marks) {
    if (m.start < at) continue;
    html += prose(r.body.slice(at, m.start), q) + `<span class="${cls}">${marked(m.text, q)}</span>`;
    at = m.end;
  }
  return html + prose(r.body.slice(at), q);
}

const replyUsage = (entry, i) => entry.d.info.usage_all?.[i] ?? (i === entry.replies.length - 1 ? entry.d.info.usage : null);
const replyLimit = (entry, i) => entry.d.info.limits?.[i] ?? tokenLimit(entry.seat, entry.d);

/** "56 of 16000 out · 2223 in", for one call. */
function callTokens(usage, limit) {
  const bits = [];
  if (usage?.completion_tokens != null) bits.push(`${usage.completion_tokens}${limit != null ? ` of ${limit}` : ''} out`);
  if (usage?.prompt_tokens != null) bits.push(`${usage.prompt_tokens} in`);
  if (usage?.reasoning_tokens) bits.push(`${usage.reasoning_tokens} hidden reasoning`);
  if (usage?.cost) bits.push(`$${Number(usage.cost).toFixed(5)}`);
  return bits.join(' · ');
}

/** What it left for the table and for its coach (the logged values), under the reply. */
function talkNodes(entry, q) {
  const out = [];
  if (entry.said) out.push(el('div.bubble.said', { style: { '--seat': seatCss(entry.seatNo) } }, el('span.blabel', {}, 'Said to the table'), el('span', { html: marked(entry.said, q) })));
  else if (entry.seat.settings?.talk && entry.d.kind === 'action') out.push(el('p.hint', {}, 'Said nothing to the table.'));
  if (entry.toCoach) out.push(el('div.bubble.tocoach', {}, el('span.blabel', {}, 'To its coach'), el('span', { html: marked(entry.toCoach, q) })));
  return out;
}

/** A notes box: the short result of an extra call, as the main prompt got it. */
function notesBox(notes, q, cls = '') {
  return el('div.notes', { class: cls, html: notes ? prose(notes, q) : '<i>No notes.</i>' });
}

/** One extra call (digest or coach): notes first, full reply and hidden thinking behind toggles. */
function auxStep(entry, a, n, q, entries) {
  const head = el('div.shead', {}, el('span.snum', {}, String(n)),
    el('b', {}, a.role === 'digest' ? 'Read the table talk' : a.role === 'coach' ? 'Coach review' : a.role),
    a.cut ? el('span.badge.b-cutoff', { title: `It used ${a.usage.completion_tokens} of ${a.limit} tokens` }, '✂ cut off') : null,
    el('span.stokens', {}, callTokens(a.usage, a.limit)));
  const out = [head];
  if (a.role === 'digest' && entries) {
    const read = digestRead(entries, entry);
    if (read.length) {
      out.push(el('div.readmsgs', {}, el('span.blabel', {}, `New since its last read (${read.length})`),
        ...read.map(m => el('div.bubble.small', { style: { '--seat': seatCss(m.seatNo) } },
          el('span.blabel', {}, `${playerName(m.seatNo)} · R${m.round} T${m.turn_no + 1}`), el('span', { html: marked(m.text, q) })))));
    }
  }
  const flagged = a.role === 'coach' && entry.flags.coachFlagged;
  out.push(notesBox(a.notes, q, a.role === 'coach' ? (flagged ? 'flagged' : 'calm') : 'talknotes'));
  const more = el('details.auxmore', {}, el('summary', {}, `Full ${a.role} reply${a.thinking ? ' and hidden thinking' : ''}`));
  if (a.thinking) more.append(el('details.thinking', {}, el('summary', {}, `Hidden thinking · ${plural(wordCount(a.thinking), 'word')}`), el('div.reply.hidden-thought', { html: prose(a.thinking, q) })));
  more.append(el('div.reply', { html: a.body ? prose(a.body, q) : '<i>(empty reply)</i>' }));
  if (a.prompt) more.append(lazyText(`What the ${a.role} call was shown`, () => marked(a.prompt, q)));
  out.push(more);
  return el('li.step', { class: `s-${a.role}` }, out);
}

function lazyText(summary, html) {
  const box = el('div.reply.prompt-text');
  const det = el('details.prompt', {}, el('summary', {}, summary), box);
  det.addEventListener('toggle', () => { if (det.open && !box.childNodes.length) box.innerHTML = html(); });
  return det;
}

function diffHtml(ops) {
  return ops.map(o => (o.op === 'same' ? esc(o.text) : o.op === 'del' ? `<del>${esc(o.text)}</del>` : `<ins>${esc(o.text)}</ins>`)).join(' ');
}

/** The plan shown to the model at this decision, against the plan it wrote back. */
function planNodes(entry) {
  const p = entry.plan, d = entry.d;
  if (!p) return [];
  const out = [el('h4', {}, 'Plan')];
  if (d.kind !== 'action') {
    // plans are only written at action decisions; show what it had in mind
    if (p.before) out.push(el('details', {}, el('summary', {}, 'The plan it was shown'), el('div.plantext', {}, p.before)));
    else out.push(el('p.hint', {}, 'No plan yet.'));
    return out;
  }
  if (p.after == null) {
    out.push(el('p.hint', {}, p.before ? 'No plan written back, so the old one stands.' : 'No plan written.'));
    if (p.before) out.push(el('details', {}, el('summary', {}, 'The plan it was shown'), el('div.plantext', {}, p.before)));
    return out;
  }
  const parsed = parsePlan(p.after);
  if (planUnreadable(parsed)) {
    out.push(el('p.warn', {}, 'The plan written back has none of the five lines; it was probably taken from the wrong part of the reply. This is what the model will be shown as its plan:'),
      el('div.plantext', {}, p.after));
  }
  out.push(el('p.hint', {}, p.first ? 'First plan written.' : p.changed.length ? `Changed: ${p.changed.join(', ')}.` : 'Kept as it was.'));
  const table = el('div.plandiff');
  for (const f of p.fields) {
    table.append(el('div.pf', { class: f.changed ? 'changed' : 'same' },
      el('span.pname', {}, f.name),
      el('span.pval', { html: f.changed ? (p.first ? `<ins>${esc(f.after)}</ins>` : diffHtml(f.ops)) : esc(f.after) || '<i>–</i>' })));
  }
  out.push(table);
  if (parsed.extra && !planUnreadable(parsed)) out.push(el('p.hint', {}, `Also written: ${parsed.extra}`));
  return out;
}
const planUnreadable = parsed => Object.values(parsed.fields).every(v => !v) && !!parsed.extra;

function usageNodes(entry) {
  const info = entry.d.info;
  if (Array.isArray(info.usage_all) && info.usage_all.length) {
    const many = info.usage_all.length > 1;
    return info.usage_all.map((u, i) => el('p.hint.usage', {}, `${many ? (i ? 'Second reply: ' : 'First reply: ') : ''}${callTokens(u, info.limits?.[i])}`));
  }
  const u = info.usage || {}, bits = [];
  const limit = tokenLimit(entry.seat, entry.d);
  if (u.prompt_tokens != null) bits.push(`${u.prompt_tokens} tokens in`);
  if (u.completion_tokens != null) bits.push(`${u.completion_tokens}${limit ? ` of ${limit}` : ''} out${entry.replies.length > 1 ? ' (second reply)' : ''}`);
  if (u.reasoning_tokens) bits.push(`${u.reasoning_tokens} hidden reasoning`);
  if (u.cost != null) bits.push(`$${Number(u.cost).toFixed(5)}`);
  return bits.length ? [el('p.hint.usage', {}, bits.join(' · '))] : [];
}

function promptNode(entry, q) {
  const box = el('div.reply.prompt-text');
  const det = el('details.prompt', {}, el('summary', {}, 'The position as the model was shown it'), box);
  // filled on first opening: prompts are long
  det.addEventListener('toggle', () => { if (det.open && !box.childNodes.length) box.innerHTML = marked(entry.d.info.prompt || '', q); });
  return det;
}

/**
 * One model decision.
 * @param {object} entry   from modelIndex()
 * @param {{query?: string, options?: boolean, wide?: boolean, planContext?: boolean, book?: object, entries?: Array}} [opts]
 *   planContext: show the plan the model was shown at decisions where it can't write one
 *   entries: every model entry of the game, to show which messages a digest read
 */
export function decisionCard(entry, { query = '', options = true, wide = false, planContext = true, book = null, entries = null } = {}) {
  const main = [], side = [];
  if (entry.flags.fallback) {
    main.push(el('p.fallback', {}, el('b', {}, 'Random move. '),
      `The model's answer couldn't be read, so option ${entry.d.choice + 1} was played at random. It is not the model's choice.`));
  }
  const b = badges(entry).filter(x => !x.classList.contains('b-fallback'));
  if (b.length) main.push(el('div.badges', {}, b));
  if (options) main.push(...optionList(entry, book));
  if (entry.aux.length) {
    // the calls in the order they were made: digest, coach, then the main reply
    const steps = entry.aux.map((a, i) => auxStep(entry, a, i + 1, query, entries));
    steps.push(el('li.step.s-main', {},
      el('div.shead', {}, el('span.snum', {}, String(entry.aux.length + 1)), el('b', {}, 'Its reply'),
        el('span.stokens', {}, entry.d.info.usage_all?.length ? callTokens(entry.d.info.usage_all.at(-1), entry.d.info.limits?.at(-1)) : '')),
      ...replyNodes(entry, query, { titled: false }), ...talkNodes(entry, query)));
    main.push(el('ol.steps', {}, steps));
  } else {
    main.push(...replyNodes(entry, query), ...talkNodes(entry, query));
  }
  if (planContext || entry.d.kind === 'action') (wide ? side : main).push(...planNodes(entry));
  main.push(...usageNodes(entry));
  if (entry.d.info.prompt) main.push(promptNode(entry, query));
  if (wide && side.length) return el('div.mcard.wide', {}, el('div.mmain', {}, main), el('div.mside', {}, side));
  return el('div.mcard', {}, main);
}

// ---------------------------------------------------------------- plan timeline

/** One lane per plan line, a marker wherever that line changed; click to go there. */
class PlanTimeline {
  constructor(entries, seatNo, last, rounds, onGo) {
    this.last = Math.max(1, last);
    this.node = el('div.timeline', { style: { '--seat': seatCss(seatNo) } });
    const changes = entries.filter(e => e.seatNo === seatNo && e.plan && (e.flags.planChanged));
    const track = el('div.ttrack');
    for (const r of rounds) if (r.round > 0) track.append(el('span.tround', { style: { left: this._x(r.index) }, title: `Round ${r.round}` }, `R${r.round}`));
    this.cursor = el('span.tcursor');
    track.append(this.cursor);
    this.markers = [];
    const lanes = el('div.tlanes');
    for (const name of PLAN_FIELDS) {
      const lane = el('div.tlane', {}, el('span.tname', {}, name));
      const bar = el('div.tbar');
      for (const e of changes) {
        if (!e.plan.changed.includes(name)) continue;
        const m = el('button.tm', {
          style: { left: this._x(e.index) },
          title: `${whereText(e)} (decision ${e.index + 1}): ${e.plan.first ? 'first plan' : `changed ${e.plan.changed.join(', ')}`}`,
          onclick: () => onGo(e.index),
        });
        m.dataset.index = String(e.index);
        bar.append(m);
        this.markers.push(m);
      }
      lane.append(bar);
      lanes.append(lane);
    }
    this.node.append(el('div.thead2', {}, el('span.dot'), el('b', {}, `${playerName(seatNo)}'s plan`), el('span.hint', {}, ` · ${plural(changes.length, 'change')}; click a mark to go there`)), track, lanes);
  }

  _x(index) { return `${(index / this.last) * 100}%`; }

  update(index) {
    this.cursor.style.left = this._x(index);
    for (const m of this.markers) m.classList.toggle('here', Number(m.dataset.index) === index);
  }
}

// ---------------------------------------------------------------- shared search and filters

class Finder extends EventTarget {
  constructor(entries) {
    super();
    this.entries = entries;
    this.query = '';
    this.filters = new Set();
    this.seat = null;   // null = every model seat
  }
  get active() { return !!this.query || this.filters.size > 0; }
  setQuery(q) { this.query = q.trim().toLowerCase(); this._changed(); }
  toggle(key) { this.filters.has(key) ? this.filters.delete(key) : this.filters.add(key); this._changed(); }
  setSeat(s) { this.seat = s; this._changed(); }
  _changed() { this.dispatchEvent(new Event('change')); }
  /** Does this entry pass the filters (any of those switched on) and the search? */
  passes(e) {
    if (this.seat != null && e.seatNo !== this.seat) return false;
    if (this.filters.size && ![...this.filters].some(k => e.flags[k])) return false;
    return !this.query || e.search.includes(this.query);
  }
  matches() { return this.entries.filter(e => this.passes(e)); }
  count(key) { return this.entries.filter(e => (this.seat == null || e.seatNo === this.seat) && e.flags[key]).length; }
}

function searchBox(finder, placeholder) {
  const input = el('input', { type: 'search', placeholder, value: finder.query, 'aria-label': 'Search the replies' });
  let timer = null;
  input.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => finder.setQuery(input.value), 150); });
  input.addEventListener('keydown', e => { if (e.key === 'Escape' && input.value) { e.stopPropagation(); input.value = ''; finder.setQuery(''); } });
  finder.addEventListener('change', () => { if (document.activeElement !== input && input.value.trim().toLowerCase() !== finder.query) input.value = finder.query; });
  return input;
}

function filterChips(finder, filters) {
  const box = el('div.filters', { role: 'group', 'aria-label': 'Filters' });
  const draw = () => box.replaceChildren(...filters.map(f => el('button.fchip', {
    class: `f-${f.key}`, 'aria-pressed': String(finder.filters.has(f.key)), title: f.title, onclick: () => finder.toggle(f.key),
  }, `${f.icon} ${f.label} `, el('span.n', {}, String(finder.count(f.key))))));
  finder.addEventListener('change', draw);
  draw();
  return box;
}

// ---------------------------------------------------------------- the Model tab

export class ModelPanel {
  /**
   * @param {{replay, player, book, box: HTMLElement, rounds: Array}} opts
   */
  constructor({ replay, player, book, box, rounds }) {
    this.replay = replay;
    this.book = book;
    this.player = player;
    this.box = box;
    this.header = replay.header;
    this.entries = modelIndex(replay);
    this.byIndex = new Map(this.entries.map(e => [e.index, e]));
    this.seats = llmSeats(this.header);
    this.finder = new Finder(this.entries);
    this.features = seatFeatures(this.header);
    this.filters = filtersFor(this.features);
    this.talk = talkLog(this.entries);
    this.drawer = new SideDrawer(this);
    this.transcript = new Transcript(this);
    this._build(rounds);
    this.finder.addEventListener('change', () => { this._renderResults(); this._renderCurrent(); });
    this._onKey = e => {
      if (e.key !== 'Escape') return;
      if (!$('rules').hidden) this.drawer.close();
      else if (!$('transcript').hidden) this.transcript.close();
    };
    window.addEventListener('keydown', this._onKey);
  }

  get query() { return this.finder.query; }

  dispose() {
    window.removeEventListener('keydown', this._onKey);
    this.drawer.close();
    this.transcript.close();
  }

  get placeholder() {
    const f = this.features;
    return f.talk || f.coach || f.digest ? 'Search replies, talk and coach notes' : 'Search the reasoning, e.g. round goal, group';
  }

  /** Buttons that open the side drawer at one of its pages. */
  drawerButtons() {
    return [
      this.features.talk ? el('button', { title: 'Every message left for the table, as a chat', onclick: () => this.drawer.toggle('talk') }, 'Table talk') : null,
      this.features.coach ? el('button', { title: "Each seat's conversation with its coach", onclick: () => this.drawer.toggle('coach') }, 'Coach') : null,
      el('button', { title: 'The rules summary the model was given', onclick: () => this.drawer.toggle('rules') }, 'Rules'),
    ];
  }

  _build(rounds) {
    const head = el('div.mhead');
    if (this.seats.length > 1) {
      const sel = el('select', { 'aria-label': 'Which model seat', onchange: () => this.finder.setSeat(sel.value === 'all' ? null : Number(sel.value)) },
        el('option', { value: 'all' }, 'Every model seat'),
        ...this.seats.map(p => el('option', { value: String(p) }, `${playerName(p)} · ${seatLabel(this.header, p)}`)));
      head.append(sel);
    } else {
      const p = this.seats[0];
      head.append(el('div.who', { style: { '--seat': seatCss(p) } }, el('span.dot'), el('b', {}, playerName(p)), el('span.agent', {}, seatLabel(this.header, p))));
    }
    head.append(el('div.mbuttons', {},
      el('button', { title: 'Every decision in order, without the table', onclick: () => this.transcript.open() }, 'Transcript'),
      ...this.drawerButtons()));

    this.timelines = this.seats.filter(p => this.header.seats[p].settings?.plan)
      .map(p => new PlanTimeline(this.entries, p, this.player.last, rounds, i => this.player.goto(i)));

    this.results = el('div.mresults');
    this.current = el('div.mcurrent');
    this.box.replaceChildren(head, ...this.timelines.map(t => t.node),
      el('div.msearch', {}, searchBox(this.finder, this.placeholder), filterChips(this.finder, this.filters)),
      this.results, this.current);
    this._renderResults();
  }

  _go(index) { this.player.goto(index); }

  _renderResults() {
    if (!this.finder.active) { this.results.replaceChildren(); this.results.hidden = true; return; }
    const list = this.finder.matches(), q = this.finder.query;
    this.results.hidden = false;
    const nav = el('div.rnav', {},
      el('span', {}, list.length ? plural(list.length, 'decision') : 'No decisions match'),
      el('button.quiet', { title: 'Previous match', disabled: !list.length, onclick: () => this._step(-1) }, '◀'),
      el('button.quiet', { title: 'Next match', disabled: !list.length, onclick: () => this._step(+1) }, '▶'));
    this._rows = list.map(e => {
      const snip = q ? excerpt(e.text, q) : null;
      const row = el('button.mres', { onclick: () => this._go(e.index) },
        el('span.rwhere', {}, `${e.index + 1} · ${whereText(e)} · ${DECISION_TITLES[e.d.kind] || e.d.kind}`),
        el('span.ricons', {}, FILTERS.filter(f => e.flags[f.key]).map(f => f.icon).join(' ')),
        snip ? el('span.rsnip', { html: marked(snip, q) }) : null);
      row.dataset.index = String(e.index);
      return row;
    });
    this.results.replaceChildren(nav, el('div.rlist', {}, this._rows));
    this._markRow();
  }

  _step(dir) {
    const list = this.finder.matches(), here = this.player.index;
    const target = dir > 0 ? list.find(e => e.index > here) ?? list[0] : [...list].reverse().find(e => e.index < here) ?? list[list.length - 1];
    if (target) this._go(target.index);
  }

  _markRow() {
    for (const r of this._rows || []) {
      const on = Number(r.dataset.index) === this.player.index;
      r.classList.toggle('current', on);
      if (on && !this.box.hidden) r.scrollIntoView({ block: 'nearest' });
    }
  }

  /** The model decision at the cursor, or the latest one before it, or the first. */
  _entryAt(index) {
    const ok = e => this.finder.seat == null || e.seatNo === this.finder.seat;
    let best = null;
    for (const e of this.entries) { if (!ok(e)) continue; if (e.index <= index) best = e; else { if (!best) best = e; break; } }
    return best;
  }

  _renderCurrent() {
    const index = this.player.index, e = this._entryAt(index);
    if (!e) { this.current.replaceChildren(el('p.hint', {}, 'No model decisions in this game.')); return; }
    const out = [];
    if (e.index !== index) {
      out.push(el('p.note', {}, e.index < index
        ? `Latest model decision, ${plural(index - e.index, 'decision')} back`
        : `The model's first decision comes at decision ${e.index + 1}`));
    }
    out.push(el('div.mtitle', { style: { '--seat': seatCss(e.seatNo) } },
      el('span.dot'), el('b', {}, DECISION_TITLES[e.d.kind] || e.d.kind),
      el('span.hint', {}, ` ${whereText(e)} · decision ${e.index + 1}`),
      e.index !== index ? el('button.quiet.go', { onclick: () => this._go(e.index) }, 'Go there') : null));
    out.push(decisionCard(e, { query: this.finder.query, book: this.book, entries: this.entries }));
    this.current.replaceChildren(...out);
  }

  render() {
    for (const t of this.timelines) t.update(this.player.index);
    this._markRow();
    this._renderCurrent();
    if (!$('transcript').hidden) this.transcript.markCurrent();
    this.drawer.update();
  }

  /** Show a decision: scroll the transcript to it when it is open, else move the replay there. */
  show(index) {
    if (!$('transcript').hidden) this.transcript.scrollTo(index);
    else this._go(index);
  }
}

// ---------------------------------------------------------------- transcript

class Transcript {
  constructor(panel) {
    this.panel = panel;
    this.showOthers = true;
    panel.finder.addEventListener('change', () => { if (!$('transcript').hidden) this._renderBody(); });
  }

  open() {
    const p = this.panel, root = $('transcript');
    this.panel.player.pause();
    const h = p.header;
    const others = el('label.check', { title: "Other players' decisions, one line each" },
      el('input', { type: 'checkbox', checked: this.showOthers, onchange: e => { this.showOthers = e.target.checked; this._renderBody(); } }), ' Other players');
    this.body = el('div.txbody');
    root.replaceChildren(el('div.txinner', {},
      el('div.txtop', {}, el('header.txhead', {},
        el('div', {}, el('h1', {}, 'Transcript'), el('p.hint', {}, `${[h.experiment, h.condition].filter(Boolean).join(' / ')} · seed ${h.seed} · ${p.seats.map(s => `${playerName(s)}: ${seatLabel(h, s)}`).join(', ')}`)),
        el('div.txbuttons', {},
          ...p.drawerButtons(),
          el('button.primary', { onclick: () => this.close() }, 'Back to the table'))),
      el('div.txtools', {}, searchBox(p.finder, p.placeholder), filterChips(p.finder, p.filters), others)),
      ...p.timelines.map(t => {
        // a copy of the strip whose marks scroll the transcript instead
        const n = t.node.cloneNode(true);
        n.querySelectorAll('.tm').forEach(m => m.addEventListener('click', () => this.scrollTo(Number(m.dataset.index))));
        n.querySelector('.thead2 .hint').textContent = ' · click a mark to read that decision';
        return n;
      }),
      this.body));
    root.hidden = false;
    document.body.classList.add('transcript-open');
    this._renderBody();
    this.scrollTo(this._nearest(p.player.index), 'auto');
  }

  close() {
    const root = $('transcript');
    if (root.hidden) return;
    root.hidden = true;
    root.replaceChildren();
    document.body.classList.remove('transcript-open');
  }

  _nearest(index) {
    const e = this.panel._entryAt(index);
    return e ? e.index : index;
  }

  scrollTo(index, behavior = 'smooth') {
    const node = this.body.querySelector(`[data-index="${index}"]`);
    if (node) node.scrollIntoView({ block: 'start', behavior });
  }

  markCurrent() {
    for (const n of this.body?.querySelectorAll('.txentry') || []) n.classList.toggle('current', Number(n.dataset.index) === this.panel.player.index);
  }

  _renderBody() {
    const p = this.panel, f = p.finder, q = f.query, h = p.header, out = [];
    let round = -1, shown = 0;
    for (const pos of p.replay.positions) {
      const d = pos.decision;
      if (!d) continue;
      const entry = p.byIndex.get(pos.index);
      let node = null;
      if (entry && f.passes(entry)) {
        shown++;
        node = el('article.txentry', { style: { '--seat': seatCss(entry.seatNo) } },
          el('div.txtitle', {},
            el('span.dot'), el('b', {}, DECISION_TITLES[d.kind] || d.kind),
            el('span.hint', {}, ` ${playerName(entry.seatNo)} · ${whereText(pos)} · decision ${pos.index + 1}`),
            el('button.quiet.go', { onclick: () => { this.close(); p.player.goto(pos.index); } }, 'Show on the table')),
          decisionCard(entry, { query: q, wide: true, planContext: false, book: p.book, entries: p.entries }));
      } else if (!entry && !f.active && this.showOthers) {
        const who = d.player === 'group' ? 'The group' : playerName(d.player);
        const agent = d.player === 'group' ? (h.group_policy || 'group policy') : seatLabel(h, d.player);
        node = el('div.txother', { style: d.player === 'group' ? {} : { '--seat': seatCss(d.player) } },
          el('span.dot'), el('span.hint', {}, `${who} (${agent}) · ${DECISION_TITLES[d.kind] || d.kind}: `),
          el('span', { html: rich(d.labels?.[d.choice] ?? '') }));
      }
      if (!node) continue;
      if (pos.round !== round) {
        round = pos.round;
        const goal = round >= 1 && round <= 4 ? p.replay.positions[pos.index].state.goals?.[round - 1] : null;
        out.push(el('h2.txround', {}, round ? `Round ${round}` : 'Setup', goal != null ? el('span.hint', { html: ` · goal: ${rich(p.book.goal(goal)?.plain ?? goal)}` }) : null));
      }
      node.dataset.index = String(pos.index);
      out.push(node);
    }
    if (f.active && !shown) out.push(el('p.hint', {}, 'No decisions match.'));
    this.body.replaceChildren(...out);
    this.markCurrent();
  }
}

// ---------------------------------------------------------------- side drawer

const PAGES = { talk: 'Table talk', coach: 'Coach', rules: 'Rules' };

/** Beside the panel (or the transcript): the table talk, coach threads and system prompts. */
class SideDrawer {
  constructor(panel) {
    this.panel = panel;
    this.page = 'rules';
    this.seat = panel.seats[0];
    this.coachSeat = panel.seats.find(p => panel.header.seats[p].settings?.coach) ?? panel.seats[0];
    this.onlyAnswered = false;
    panel.finder.addEventListener('change', () => { if (this.isOpen) this._render(); });
  }

  get isOpen() { return !$('rules').hidden; }
  get pages() { return Object.keys(PAGES).filter(k => k === 'rules' || this.panel.features[k]); }

  /** Open at a page, or close if it is already showing that page. */
  toggle(page = this.page) {
    if (this.isOpen && page === this.page) this.close(); else this.open(page);
  }

  open(page = this.page) {
    // the coach page starts on the seat whose decision is showing
    if (page === 'coach' && page !== this.page) {
      const e = this.panel._entryAt(this.panel.player.index);
      if (e && this.panel.header.seats[e.seatNo].settings?.coach) this.coachSeat = e.seatNo;
    }
    this.page = page;
    $('rules').hidden = false;
    document.body.classList.add('rules-open');
    this._render();
  }

  close() {
    $('rules').hidden = true;
    document.body.classList.remove('rules-open');
  }

  /** The replay moved: mark what has been said by now, and the current decision. */
  update() {
    if (!this.isOpen || this.page === 'rules') return;
    const here = this.panel.player.index;
    let now = null;
    for (const n of $('rules').querySelectorAll('[data-index]')) {
      const i = Number(n.dataset.index);
      n.classList.toggle('later', i > here);
      n.classList.remove('now');
      if (i <= here) now = n;
    }
    if (now) { now.classList.add('now'); now.scrollIntoView({ block: 'nearest' }); }
  }

  _render() {
    const pages = this.pages;
    if (!pages.includes(this.page)) this.page = 'rules';
    const tabs = pages.length > 1 ? el('nav.dtabs', { role: 'tablist' }, pages.map(k =>
      el('button', { role: 'tab', 'aria-selected': String(k === this.page), onclick: () => this.open(k) }, PAGES[k]))) : null;
    const body = this.page === 'talk' ? this._talk() : this.page === 'coach' ? this._coach() : this._rules();
    $('rules').replaceChildren(...[
      el('div.rhead2', {},
        el('h2', {}, this.page === 'rules' ? 'What the model was told' : PAGES[this.page]),
        el('button.quiet.close', { 'aria-label': 'Close', onclick: () => this.close() }, '×')),
      tabs, ...body].filter(Boolean));
    this.update();
    const first = $('rules').querySelector('.rules-text mark');
    if (first) first.scrollIntoView({ block: 'center' });
  }

  _seatPicker(seats, value, set) {
    if (seats.length < 2) return null;
    return el('select', { onchange: e => { set(Number(e.target.value)); this._render(); } },
      ...seats.map(s => el('option', { value: String(s), selected: s === value }, `${playerName(s)} · ${seatLabel(this.panel.header, s)}`)));
  }

  /** Every message, as a chat; the ones still to come are faded. Click one to go to its decision. */
  _talk() {
    const p = this.panel, q = p.finder.query, two = p.seats.length === 2;
    if (!p.talk.length) return [el('p.hint', {}, 'Nobody said anything.')];
    const out = [el('p.hint', {}, `${plural(p.talk.length, 'message')}. Faded ones are still to come; click one to go to its decision.`)];
    let round = null;
    const chat = el('div.chat');
    for (const m of p.talk) {
      if (m.round !== round) { round = m.round; chat.append(el('div.chatround', {}, round ? `Round ${round}` : 'Setup')); }
      const hit = q && m.text.toLowerCase().includes(q);
      chat.append(el('button.bubble.msg', {
        class: `${two && m.seatNo === p.seats[1] ? 'right' : ''} ${hit ? 'hit' : ''}`, style: { '--seat': seatCss(m.seatNo) },
        dataset: { index: String(m.index) }, title: `Decision ${m.index + 1}`, onclick: () => p.show(m.index),
      }, el('span.blabel', {}, `${playerName(m.seatNo)} · round ${m.round}, turn ${m.turn_no + 1}`), el('span', { html: marked(m.text, q) })));
    }
    out.push(chat);
    return out;
  }

  /** One seat's coach notes, each followed by the player's reply and the action it took. */
  _coach() {
    const p = this.panel, q = p.finder.query;
    const seats = p.seats.filter(s => p.header.seats[s].settings?.coach);
    const list = p.entries.filter(e => e.seatNo === this.coachSeat && (e.aux.some(a => a.role === 'coach') || e.toCoach));
    const shown = this.onlyAnswered ? list.filter(e => e.toCoach) : list;
    const answered = list.filter(e => e.toCoach).length, flagged = list.filter(e => e.flags.coachFlagged).length;
    const out = [
      this._seatPicker(seats, this.coachSeat, s => { this.coachSeat = s; }),
      el('p.hint', {}, `${plural(list.length, 'review')}: ${flagged} flagged a problem, ${answered} answered by the player.`),
      el('label.check', {}, el('input', { type: 'checkbox', checked: this.onlyAnswered, onchange: e => { this.onlyAnswered = e.target.checked; this._render(); } }), ' Only where the player answered'),
    ];
    const thread = el('div.chat.thread');
    let round = null;
    for (const e of shown) {
      if (e.round !== round) { round = e.round; thread.append(el('div.chatround', {}, `Round ${round}`)); }
      const coach = e.aux.find(a => a.role === 'coach');
      const turn = el('div.cturn', { dataset: { index: String(e.index) } });
      if (coach) {
        turn.append(el('button.bubble.coachmsg', { class: e.flags.coachFlagged ? 'flagged' : 'calm', onclick: () => p.show(e.index), title: `Decision ${e.index + 1}` },
          el('span.blabel', {}, `Coach · round ${e.round}, turn ${e.turn_no + 1}${e.flags.coachFlagged ? ' · ⚑' : ''}`),
          el('span', { html: coach.notes ? prose(coach.notes, q) : '<i>No notes.</i>' })));
      }
      turn.append(el('button.bubble.right.playermsg', { class: e.toCoach ? '' : 'none', style: { '--seat': seatCss(e.seatNo) }, onclick: () => p.show(e.index) },
        el('span.blabel', {}, `${playerName(e.seatNo)}${e.toCoach ? '' : ' did not reply'}`),
        e.toCoach ? el('span', { html: marked(e.toCoach, q) }) : null,
        el('span.played', { html: `played: ${rich(e.d.labels?.[e.d.choice] ?? '')}` })));
      thread.append(turn);
    }
    if (!shown.length) thread.append(el('p.hint', {}, this.onlyAnswered ? 'The player never answered.' : 'No coach reviews.'));
    out.push(thread);
    return out;
  }

  _rules() {
    const p = this.panel, h = p.header, st = h.seats[this.seat]?.settings || {}, q = p.finder.query;
    const text = el('div.reply.rules-text', { html: marked(st.system_prompt || '(no system prompt in the log)', q) });
    const hits = q ? (st.system_prompt || '').toLowerCase().split(q).length - 1 : 0;
    return [
      this._seatPicker(p.seats, this.seat, s => { this.seat = s; }),
      el('p.hint', {}, seatFacts(st).join(' · ')),
      q ? el('p.hint', {}, hits ? `${hits} ${hits === 1 ? 'match' : 'matches'} for "${q}" (marked)` : `"${q}" does not appear in the system prompt.`) : null,
      text,
      st.coach_system_prompt ? el('details.coachrules', { open: !!q && st.coach_system_prompt.toLowerCase().includes(q) },
        el('summary', {}, "What the coach was told"), el('div.reply.rules-text', { html: marked(st.coach_system_prompt, q) })) : null,
    ];
  }
}

/** A language-model seat's settings as short phrases (the Rules page and the Game tab). */
export function seatFacts(st) {
  return [
    st.model && `model ${st.model}`,
    st.prompt && `prompt "${st.prompt}"`,
    st.reasoning === 'full' ? 'asked to reason in a few paragraphs' : st.reasoning ? 'asked to reason briefly' : 'answers only',
    st.thinking ? `hidden thinking: ${st.thinking}` : null,
    st.plan ? 'keeps a plan' : null,
    st.talk ? 'table talk' : null,
    st.coach ? 'coach' : null,
    st.digest ? 'reads talk in a digest call' : null,
    st.outcomes ? 'shown outcomes' : null,
    st.compact ? 'compact position text' : null,
    st.max_tokens != null ? `max ${st.max_tokens} tokens${st.plan ? ` (+600 at actions)` : ''}` : null,
    st.temperature != null ? `temperature ${st.temperature}` : null,
  ].filter(Boolean);
}

/** A seat's token use over the game, one line per kind of call (the Game tab). */
export function tokenLines(entries, seatNo) {
  const t = tokenTotals(entries, seatNo), names = { main: 'main replies', coach: 'coach calls', digest: 'digest calls' };
  const line = (k, v) => `${plural(v.calls, names[k] ? names[k].replace(/s$/, '') : k)}: ${v.prompt.toLocaleString()} in, ${v.completion.toLocaleString()} out${v.cost ? `, $${v.cost.toFixed(3)}` : ''}${v.cut ? `, ${v.cut} cut off` : ''}`;
  const keys = Object.keys(t).filter(k => t[k].calls);
  const all = keys.reduce((a, k) => ({ prompt: a.prompt + t[k].prompt, completion: a.completion + t[k].completion, cost: a.cost + t[k].cost }), { prompt: 0, completion: 0, cost: 0 });
  return [...keys.map(k => line(k, t[k])),
    keys.length > 1 ? `All calls: ${all.prompt.toLocaleString()} in, ${all.completion.toLocaleString()} out${all.cost ? `, $${all.cost.toFixed(3)}` : ''}` : null].filter(Boolean);
}
