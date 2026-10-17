// Everything on the page that is not the 3D table: the top bar, the Step / Turns / Game
// tabs, the transport and the card inspector. It reads the replay and listens to the
// ReplayPlayer; it never changes the game.
//
// The Step tab is built around one step (log format section 9): who is deciding, the
// options, the one chosen, the agent's own view of it, and what happened next. A live
// game would show the same thing with no option chosen yet.

import { drawCardFace, drawBonusFace } from '../../../components/cards/src/index.js';
import { turnIndex, roundIndex } from '../replay/log.js';
import { runningScore, seatCss, seatLabel, playerName, HABITATS } from '../data.js';
import { describeEvent, DECISION_TITLES, ACTION_NAMES, fmt, eventSeat } from '../describe.js';
import { el, esc, rich } from './rich.js';
import { ModelPanel, decisionCard, dealtBirdList, birdsByNumber, seatFacts, tokenLines } from './model.js';
import { Scorecard } from './scorecard.js';
import { isLlmSeat, llmSeats, modelEntry } from '../llm.js';

const $ = id => document.getElementById(id);
const TURNS_PER_ROUND = [8, 7, 6, 5];
const MANY_OPTIONS = 7;
const sameOption = (a, b) => JSON.stringify(a) === JSON.stringify(b);

export class Hud {
  /**
   * @param {object} replay                 from buildReplay()
   * @param {import('../player.js').ReplayPlayer} player
   * @param {import('../scene/GameTable.js').GameTable} game
   */
  constructor(replay, player, game) {
    this.replay = replay;
    this.player = player;
    this.game = game;
    this.book = game.book;
    this.turns = turnIndex(replay);
    this.rounds = roundIndex(replay);
    this.showAll = false;
    this._off = [];

    this._buildTopbar();
    this._buildTransport();
    this._buildCamera();
    this._buildTabs();
    this._buildTurns();
    this._buildModel();   // before the Game tab, which shows each model seat's token use
    this._buildGame();
    this.scorecard = new Scorecard(replay, this.book);

    // the scorecard comes up when playback plays into the end of the game (not on a jump there)
    let finishing = false;
    this._listen(player, 'position', () => {
      this.showAll = false; this.stage = null; this.render();
      if (finishing && player.index === player.last) this.scorecard.open();
      finishing = false;
    });
    this._listen(player, 'stage', e => {
      this.stage = e.detail; this._renderStage(); this._banner(e.detail);
      finishing = e.detail.stage === 'done' && e.detail.index === player.last - 1;
    });
    this._listen(player, 'playing', () => this._renderPlay());
    this._listen(game, 'pick', e => this._pick(e.detail));
    this.render();
  }

  _listen(target, type, fn) {
    target.addEventListener(type, fn);
    this._off.push(() => target.removeEventListener(type, fn));
  }

  dispose() {
    for (const off of this._off) off();
    this.model?.dispose();
    this.scorecard?.dispose();
    clearTimeout(this._bannerTimer);
    $('inspect').hidden = true;
    $('banner').hidden = true;
  }

  // ------------------------------------------------------------------ top bar

  _buildTopbar() {
    const h = this.replay.header;
    const rules = this.replay.coop ? 'co-op goals' : 'normal rules';
    $('game-title').textContent = [h.experiment, h.condition].filter(Boolean).join(' / ') || 'Replay';
    $('game-sub').textContent = `seed ${h.seed} · ${this.replay.players} players · ${rules}${h.group_policy ? ` · ${h.group_policy}` : ''}`;
    document.title = `${$('game-title').textContent} · seed ${h.seed} · Wingspan replay`;
  }

  _renderTopbar() {
    const pos = this.player.position, s = pos.state, n = this.replay.players;
    // clock
    let clock;
    if (s.phase === 'setup') clock = 'Setup';
    else if (s.phase === 'over') clock = 'Game over';
    else {
      const per = TURNS_PER_ROUND[s.round - 1] ?? 0;
      const who = pos.turn ?? s.turn;
      const done = per - (s.actions_left?.[who] ?? per);
      clock = `Round ${s.round} · turn ${Math.min(per, done + 1)} of ${per} · ${playerName(who)}`;
    }
    $('clock').textContent = clock;

    // scores
    const over = s.phase === 'over' && this.replay.finalScores;
    const chips = [];
    let sum = 0;
    for (let p = 0; p < n; p++) {
      const sc = over ? this.replay.finalScores.players[p] : runningScore(s, p, this.book);
      sum += sc.total;
      const parts = [`birds ${sc.birds}`, `eggs ${sc.eggs}`, `cached ${sc.cached}`, `tucked ${sc.tucked}`];
      if (!this.replay.coop) parts.push(`goals ${fmt(sc.goals)}`);
      parts.push(over ? `bonus ${sc.bonus}` : 'bonus cards count at the end');
      const deciding = pos.decision?.player === p;
      chips.push(el('button.chip', {
        class: `chip${pos.turn === p ? ' turn' : ''}${deciding ? ' deciding' : ''}`,
        style: { '--seat': seatCss(p) },
        title: `${playerName(p)} (${seatLabel(this.replay.header, p)}): ${parts.join(', ')}. Click to watch this seat.`,
        onclick: () => this._watch(p),
      }, el('span.dot'), el('span.name', {}, `P${p}`), el('b', {}, fmt(sc.total))));
    }
    if (this.replay.coop) {
      const g = over ? this.replay.finalScores.group : s.group_score;
      const team = over ? this.replay.finalScores.team_total : sum + g;
      chips.push(el('span.chip.group', { title: 'Shared group score from the co-op round goals, and the team total (all players plus the group score).' },
        el('span.name', {}, 'Group'), el('b', {}, `${g > 0 ? '+' : ''}${fmt(g)}`),
        el('span.name', {}, 'Team'), el('b', {}, fmt(team))));
    }
    $('scores').replaceChildren(...chips);
  }

  _watch(seat) {
    $('follow').value = String(seat);
    this.player.setFollow(seat);
  }

  // ------------------------------------------------------------------ camera controls

  _buildCamera() {
    const follow = $('follow');
    follow.replaceChildren(
      el('option', { value: 'turn' }, 'whose turn it is'),
      el('option', { value: 'decider' }, 'whoever is deciding'),
      ...Array.from({ length: this.replay.players }, (_, p) => el('option', { value: String(p) }, `Player ${p}'s seat`)),
      el('option', { value: 'free' }, 'leave the camera alone'),
    );
    follow.value = typeof this.player.follow === 'number' ? String(this.player.follow) : this.player.follow;
    follow.onchange = () => {
      const v = follow.value;
      this.player.setFollow(/^\d+$/.test(v) ? Number(v) : v);
    };
    for (const b of $('views').querySelectorAll('button')) {
      b.onclick = () => { this.game.focus(this.game.focusSeat, { view: b.dataset.view }); this._renderViews(); };
    }
    this._renderViews();
  }

  _renderViews() {
    for (const b of $('views').querySelectorAll('button')) b.setAttribute('aria-pressed', String(b.dataset.view === this.game.viewKind));
  }

  // ------------------------------------------------------------------ transport

  _buildTransport() {
    const p = this.player;
    const scrub = $('scrub');
    scrub.max = String(p.last);
    $('back').onclick = () => p.back();
    $('step').onclick = () => p.step();
    $('play').onclick = () => p.toggle();
    $('turn-back').onclick = () => p.jump(this.turns, -1);
    $('turn-next').onclick = () => p.jump(this.turns, +1);
    $('round-back').onclick = () => p.jump(this.rounds, -1);
    $('round-next').onclick = () => p.jump(this.rounds, +1);
    $('speed').onchange = e => p.setSpeed(Number(e.target.value));
    p.setSpeed(Number($('speed').value));

    // scrubbing: jump to wherever the slider is, without queueing every value on the way
    let want = null, going = false;
    scrub.oninput = async () => {
      want = Number(scrub.value);
      if (going) return;
      going = true;
      while (want != null) { const to = want; want = null; await p.goto(to); }
      going = false;
    };

    $('ticks').replaceChildren(...this.rounds.filter(r => r.round > 0).map(r =>
      el('span.tick', { style: { left: `${(r.index / Math.max(1, p.last)) * 100}%` }, title: `Round ${r.round}` }, `R${r.round}`)));

    const onKey = e => {
      if (e.target.closest('input, select, textarea, [contenteditable]') || e.metaKey || e.ctrlKey || e.altKey) return;
      if ($('home') && !$('home').hidden) return;
      if (!$('transcript').hidden || this.scorecard.isOpen) return;   // overlays scroll; the replay behind stays put
      if (e.key === ' ') { e.preventDefault(); p.toggle(); }
      else if (e.key === 'ArrowRight') { e.preventDefault(); e.shiftKey ? p.jump(this.turns, +1) : p.step(); }
      else if (e.key === 'ArrowLeft') { e.preventDefault(); e.shiftKey ? p.jump(this.turns, -1) : p.back(); }
      else if (e.key === 'Home') p.goto(0);
      else if (e.key === 'End') p.goto(p.last);
    };
    window.addEventListener('keydown', onKey);
    this._off.push(() => window.removeEventListener('keydown', onKey));
  }

  _renderTransport() {
    const p = this.player;
    $('scrub').value = String(p.index);
    $('where').textContent = p.index >= p.last ? `End · ${p.last} decisions` : `Decision ${p.index + 1} of ${p.last}`;
    $('back').disabled = p.index === 0;
    $('turn-back').disabled = $('round-back').disabled = p.index === 0;
    $('step').disabled = $('turn-next').disabled = $('round-next').disabled = p.index >= p.last;
    this._renderPlay();
  }

  _renderPlay() {
    const p = this.player;
    $('play').textContent = p.playing ? '⏸ Pause' : '▶ Play';
    $('play').disabled = !p.playing && p.index >= p.last;
  }

  // ------------------------------------------------------------------ tabs

  _buildTabs() {
    for (const b of document.querySelectorAll('#side .tabs [data-tab]')) {
      b.onclick = () => {
        for (const o of document.querySelectorAll('#side .tabs [data-tab]')) {
          const on = o === b;
          o.setAttribute('aria-selected', String(on));
          $(`tab-${o.dataset.tab}`).hidden = !on;
        }
        if (b.dataset.tab === 'turns') this._renderTurns(true);
        if (b.dataset.tab === 'model') this.model?.render();
      };
    }
  }

  render() {
    this._renderViews();
    this._renderTopbar();
    this._renderTransport();
    this._renderStep();
    this._renderTurns(false);
    this.model?.render();
  }

  // ------------------------------------------------------------------ Model tab

  _buildModel() {
    const button = document.querySelector('#side .tabs [data-tab="model"]');
    button.hidden = !llmSeats(this.replay.header).length;
    if (button.hidden) { $('tab-model').replaceChildren(); return; }
    this.model = new ModelPanel({ replay: this.replay, player: this.player, book: this.book, box: $('tab-model'), rounds: this.rounds });
  }

  /** Show a tab by name ('step', 'turns', 'model', 'game'). */
  showTab(name) {
    document.querySelector(`#side .tabs [data-tab="${name}"]:not([hidden])`)?.click();
  }

  // ------------------------------------------------------------------ Step tab

  _renderStep() {
    const pos = this.player.position, d = pos.decision, box = $('tab-step');
    if (!d) { box.replaceChildren(...this._finalView()); return; }
    const out = [];
    const group = d.player === 'group';
    const seat = group ? null : d.player;

    out.push(el('div.who', { style: { '--seat': group ? 'var(--moss)' : seatCss(seat) } },
      el('span.dot'), el('b', {}, playerName(d.player)),
      el('span.agent', {}, group ? (this.replay.header.group_policy || 'group policy') : seatLabel(this.replay.header, seat))));
    out.push(el('h2', {}, DECISION_TITLES[d.kind] || d.kind));
    if (!pos.exact) out.push(el('p.note', { title: 'This log has a snapshot only at the start of each turn; the table here was worked out from the events since then.' }, 'Board derived from events'));

    // options, with the agent's own numbers where it gave them
    const notes = this._optionNotes(d);
    const llm = !group && isLlmSeat(this.replay.header, seat);
    const numbered = llm && birdsByNumber(this.replay.header.seats[seat]);
    const dealt = dealtBirdList(d, this.book, { numbered });
    // under the birds: a bot's scored options, or the option number a model answered with
    const under = i => notes.has(i) || (llm && !numbered && i === d.choice);
    if (dealt) out.push(dealt);
    const many = d.options.length > MANY_OPTIONS && !this.showAll;
    const keep = new Set([d.choice, ...notes.keys()]);
    for (let i = 0; i < d.options.length && keep.size < MANY_OPTIONS; i++) keep.add(i);
    const list = el('ol.options');
    d.options.forEach((opt, i) => {
      if (many && !keep.has(i)) return;
      if (dealt && !this.showAll && !under(i)) return;
      const note = notes.get(i);
      const random = i === d.choice && d.info?.fallback;
      list.append(el('li', { class: i === d.choice ? (random ? 'chosen random' : 'chosen') : '', title: i === d.choice ? (random ? "Played at random: the model's answer couldn't be read" : 'The option chosen') : null },
        el('span.mark', {}, i === d.choice ? (random ? '?' : '✓') : ''),
        el('span.label', {}, dealt && llm ? el('span.num', {}, `${i + 1}. `) : null, el('span', { html: rich(d.labels?.[i] ?? JSON.stringify(opt)) })),
        note ? el('span.val', { title: note.title }, note.text) : random ? el('span.val', {}, 'random') : null));
    });
    if (dealt && !this.showAll && list.children.length) out.push(el('p.hint', {}, llm ? `It was shown all ${d.options.length} combinations and answered with an option number:` : 'Its best-scored choices:'));
    out.push(list);
    if (d.options.length > MANY_OPTIONS) {
      out.push(el('button.quiet.more', { onclick: () => { this.showAll = !this.showAll; this._renderStep(); this._renderStage(); } },
        this.showAll ? 'Show fewer options' : `Show all ${d.options.length} options`));
    }

    out.push(...this._agentView(d));

    // what happened next
    const shown = pos.events.map((e, k) => ({ e, k })).filter(({ k }) => !pos.quiet?.[k]);
    out.push(el('h3', {}, 'What happened next'));
    if (!shown.length) out.push(el('p.hint', {}, 'Nothing visible on the table: the next decision follows straight away.'));
    else {
      out.push(el('ol.events', {}, shown.map(({ e, k }) => {
        const p = eventSeat(e);
        return el('li', { dataset: { k: String(k) }, style: p != null ? { '--seat': seatCss(p) } : {}, class: e.e === 'round_end' || e.e === 'final_scoring' ? 'big' : '', html: rich(describeEvent(e, this.book)) });
      })));
    }
    box.replaceChildren(...out);
    box.scrollTop = 0;
    this._renderStage();
  }

  // The agent's estimate for each option it reported on: Map(option index -> { text, title }).
  _optionNotes(d) {
    const notes = new Map(), info = d.info;
    if (!info) return notes;
    const find = opt => d.options.findIndex(o => sameOption(o, opt));
    for (const [opt, value] of info.values || []) {
      const i = find(opt);
      if (i >= 0) notes.set(i, { text: fmt(value), title: "The greedy bot's estimate of its objective after this option" });
    }
    for (const [opt, visits, mean] of info.top || []) {
      const i = find(opt);
      if (i >= 0) notes.set(i, { text: `${visits}× · ${fmt(mean)}`, title: 'Tree search: visits and mean value' });
    }
    for (const [dval, change] of info.estimates || []) {
      const i = d.options.findIndex(o => o[1] === dval);
      if (i >= 0) notes.set(i, { text: `${change > 0 ? '+' : ''}${fmt(change)}`, title: 'Expected change in group score at this difficulty' });
    }
    return notes;
  }

  _agentView(d) {
    const info = d.info, out = [];
    if (!info) return out;
    if (info.replies && isLlmSeat(this.replay.header, d.player)) {
      out.push(el('h3', {}, `What ${esc((info.model || 'the model').split('/').pop())} said`));
      out.push(decisionCard(this.model?.byIndex.get(this.player.index) ?? modelEntry(this.replay.header, this.player.position),
        { options: false, query: this.model?.query, entries: this.model?.entries }));
    } else if (info.options != null && info.values) {
      out.push(el('p.hint', {}, `The bot scored ${info.options} option${info.options === 1 ? '' : 's'}; its best ${info.values.length} are marked.`));
    } else if (info.iterations != null) {
      out.push(el('p.hint', {}, `Tree search ran ${info.iterations} simulations.`));
    }
    return out;
  }

  // Light up the "what happened" list as the step plays.
  _renderStage() {
    const st = this.stage, box = $('tab-step');
    const live = st && st.index === this.player.index;
    for (const li of box.querySelectorAll('.events li')) {
      const k = Number(li.dataset.k);
      li.classList.toggle('done', !!live && (st.stage === 'done' || k < st.event));
      li.classList.toggle('now', !!live && st.stage === 'event' && k === st.event);
      if (live && st.stage === 'event' && k === st.event) li.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
    }
    box.classList.toggle('playing', !!live && st.stage !== 'done');
  }

  // A short notice over the table for the moments that matter.
  _banner(st) {
    if (st.stage !== 'event') return;
    const e = this.replay.positions[st.index]?.events[st.event];
    if (!e) return;
    let text = null, kind = '';
    if (e.e === 'round_start') text = `Round ${e.round}: ${this.book.goal(e.goal)?.plain ?? ''}`;
    else if (e.e === 'round_end') {
      if (e.info && e.info[0] === 'coop') { text = `Round ${e.round}: difficulty ${e.info[1]} ${e.info[2] ? 'met' : 'missed'} (${e.group_delta > 0 ? '+' : ''}${fmt(e.group_delta)})`; kind = e.info[2] ? 'good' : 'bad'; }
      else text = `Round ${e.round} scored: ${e.points.map(fmt).join(' / ')}`;
    } else if (e.e === 'final_scoring') text = 'Game over';
    else if (e.e === 'predator') text = describeEvent(e, this.book);
    else if (e.e === 'feeder_reset') text = 'Birdfeeder refilled';
    if (!text) return;
    const b = $('banner');
    b.innerHTML = rich(text);
    b.className = kind;
    b.hidden = false;
    clearTimeout(this._bannerTimer);
    this._bannerTimer = setTimeout(() => { b.hidden = true; }, 2600 / Math.max(0.5, Math.min(4, this.player.speed)));
  }

  _finalView() {
    const fs = this.replay.finalScores, out = [];
    out.push(el('h2', {}, 'Game over'));
    if (!fs) { out.push(el('p.hint', {}, 'This log has no final scoring.')); return out; }
    out.push(el('button.primary.scorecard-open', { onclick: () => this.scorecard.open() }, 'Show the scorecard'));
    out.push(this._scoreTable(fs));
    if (this.replay.coop) {
      out.push(el('p.total', { html: `Group score <b>${fs.group > 0 ? '+' : ''}${fmt(fs.group)}</b> · team total <b>${fmt(fs.team_total)}</b>` }));
    } else {
      const best = Math.max(...fs.players.map(p => p.total));
      const winners = fs.players.map((p, i) => (p.total === best ? playerName(i) : null)).filter(Boolean);
      out.push(el('p.total', { html: `${esc(winners.join(' and '))} ${winners.length > 1 ? 'tie' : 'wins'} with <b>${fmt(best)}</b>` }));
    }
    return out;
  }

  _scoreTable(fs) {
    const cats = [['birds', 'Birds'], ['bonus', 'Bonus cards'], ['eggs', 'Eggs'], ['cached', 'Cached food'], ['tucked', 'Tucked cards'], ['goals', 'Round goals']];
    const t = el('table.scores');
    t.append(el('tr', {}, el('th'), fs.players.map((_, p) => el('th', { style: { '--seat': seatCss(p) } }, el('span.dot'), `P${p}`))));
    for (const [key, label] of cats) {
      if (key === 'goals' && this.replay.coop) continue;
      t.append(el('tr', {}, el('th', {}, label), fs.players.map(p => el('td', {}, fmt(p[key])))));
    }
    t.append(el('tr.sum', {}, el('th', {}, 'Total'), fs.players.map(p => el('td', {}, fmt(p.total)))));
    return t;
  }

  // ------------------------------------------------------------------ Turns tab

  _buildTurns() {
    const P = this.replay.positions, box = $('tab-turns');
    const rows = [];
    if (P[0]?.state.phase === 'setup') rows.push({ kind: 'head', text: 'Setup', index: 0 });
    let round = 0;
    this.turns.forEach((t, n) => {
      if (t.round !== round) {
        round = t.round;
        const goal = this.book.goal(P[t.index].state.goals[round - 1]);
        rows.push({ kind: 'head', text: `Round ${round}`, sub: goal?.plain, index: this.rounds.find(r => r.round === round)?.index ?? t.index });
      }
      // what the turn was: its action event, found between this turn start and the next
      const end = this.turns[n + 1]?.index ?? P.length - 1;
      let action = null, endRound = null;
      for (let i = t.index; i < end && i < P.length; i++) {
        for (const e of P[i].events) {
          if (!action && e.e === 'action') action = e;
          if (e.e === 'round_end') endRound = e;
        }
      }
      let text = action ? ACTION_NAMES[action.action] ?? action.action : '…';
      if (action?.action === 'play') text = `Play ${this.book.birdName(action.bird)} (${HABITATS[action.habitat]})`;
      rows.push({ kind: 'turn', index: t.index, player: t.player, text, n: t.turn_no + 1 });
      if (endRound) {
        const coop = endRound.info && endRound.info[0] === 'coop';
        rows.push({
          kind: 'end', index: end,
          text: coop
            ? `Counts ${endRound.counts.join(' / ')} · difficulty ${endRound.info[1]} ${endRound.info[2] ? 'met' : 'missed'} · group ${endRound.group_delta > 0 ? '+' : ''}${fmt(endRound.group_delta)}`
            : `Counts ${endRound.counts.join(' / ')} · points ${endRound.points.map(fmt).join(' / ')}`,
          good: coop ? !!endRound.info[2] : null,
        });
      }
    });
    this._turnRows = rows.map(r => {
      const go = () => this.player.goto(r.index);
      if (r.kind === 'head') return { ...r, node: el('button.thead', { onclick: go }, el('b', {}, r.text), r.sub ? el('span', {}, r.sub) : null) };
      if (r.kind === 'end') return { ...r, node: el('div.tend', { class: r.good == null ? '' : r.good ? 'good' : 'bad' }, r.text) };
      return { ...r, node: el('button.trow', { style: { '--seat': seatCss(r.player) }, onclick: go }, el('span.num', {}, String(r.n)), el('span.dot'), el('span.pl', {}, `P${r.player}`), el('span.txt', {}, r.text)) };
    });
    box.replaceChildren(...this._turnRows.map(r => r.node));
  }

  _renderTurns(scroll) {
    if (!this._turnRows) return;
    const here = this.player.index;
    let current = null;
    for (const r of this._turnRows) if (r.kind === 'turn' && r.index <= here) current = r;
    for (const r of this._turnRows) r.node.classList.toggle('current', r === current);
    if (current && (scroll || !$('tab-turns').hidden)) current.node.scrollIntoView({ block: 'nearest' });
  }

  // ------------------------------------------------------------------ Game tab

  _buildGame() {
    const h = this.replay.header, box = $('tab-game'), out = [];
    const row = (k, v) => el('tr', {}, el('th', {}, k), el('td', {}, v));

    out.push(el('h2', {}, 'This game'));
    const meta = el('table.kv');
    meta.append(row('Experiment', h.experiment || '–'), row('Condition', h.condition || '–'), row('Seed', String(h.seed)),
      row('Players', String(this.replay.players)),
      row('Rules', this.replay.coop ? 'Co-op round goals' : 'Normal round goals (blue side)'),
      row('Winning', h.config?.win_condition === 'team_total' ? 'Team total' : 'Individual scores'),
      row('Hands', h.config?.open_hands ? 'Open' : 'Closed'));
    const coop = h.config?.plugins?.coop_goals;
    if (coop) {
      meta.append(row('Penalty', String(coop.penalty)), row('Difficulty', `${coop.difficulty_range?.join(' to ')}; may change by ${coop.allowed_changes?.join(', ')} per round`),
        row('Group policy', h.group_policy || '–'));
    }
    meta.append(row('Snapshots', h.snapshots === 'decision' ? 'Before every decision' : 'At each turn start (boards in between are derived from events)'),
      row('Engine', (h.engine_git || '').slice(0, 12)), row('Log format', `version ${h.version}`));
    if (this.replay.name) meta.append(row('File', this.replay.name));
    out.push(meta);
    for (const w of this.replay.warnings) out.push(el('p.warn', {}, w));

    out.push(el('h3', {}, 'Seats'));
    (h.seats || []).forEach((s, p) => {
      const st = s.settings || {};
      const facts = [];
      if (s.w != null) facts.push(`motivation w = ${s.w} (${s.w === 0 ? 'selfish' : s.w === 1 ? 'team-minded' : 'in between'})`);
      if (s.group_share != null) facts.push(`group share ${s.group_share ? 'counts' : 'does not count'} as own score`);
      if (s.type === 'llm') facts.push(...seatFacts(st));
      if (st.iterations) facts.push(`${st.iterations} simulations`);
      if (st.chain_budget) facts.push(`chain budget ${st.chain_budget}`);
      const card = el('div.seatcard', { style: { '--seat': seatCss(p) } },
        el('div.who', {}, el('span.dot'), el('b', {}, playerName(p)), el('span.agent', {}, seatLabel(h, p))),
        facts.length ? el('p.hint', {}, facts.join(' · ')) : null);
      if (s.type === 'llm' && this.model) {
        const lines = tokenLines(this.model.entries, p);
        if (lines.length) card.append(el('div.tokens', {}, el('b', {}, 'Token use'), el('ul', {}, lines.map(l => el('li', {}, l)))));
      }
      if (st.system_prompt) card.append(el('details', {}, el('summary', {}, 'System prompt'), el('pre.prompt', {}, st.system_prompt)));
      if (st.coach_system_prompt) card.append(el('details', {}, el('summary', {}, "Coach's system prompt"), el('pre.prompt', {}, st.coach_system_prompt)));
      if (st.weights) card.append(el('details', {}, el('summary', {}, 'Value-function weights'), el('pre.prompt', {}, Object.entries(st.weights).map(([k, v]) => `${k}: ${v}`).join('\n'))));
      out.push(card);
    });

    const ends = this.replay.positions.flatMap(p => p.events.filter(e => e.e === 'round_end'));
    if (ends.length) {
      out.push(el('h3', {}, 'Round goals'));
      const t = el('table.scores');
      t.append(el('tr', {}, el('th', {}, 'Round'), ends[0].counts.map((_, p) => el('th', { style: { '--seat': seatCss(p) } }, el('span.dot'), `P${p}`)),
        this.replay.coop ? [el('th', {}, 'Diff.'), el('th', {}, 'Group')] : null));
      for (const e of ends) {
        const co = e.info && e.info[0] === 'coop';
        t.append(el('tr', { title: this.book.goal(e.goal)?.plain },
          el('th', {}, `${e.round}`), e.counts.map(c => el('td', {}, String(c))),
          this.replay.coop ? [el('td', {}, co ? `${e.info[1]} ${e.info[2] ? '✓' : '✗'}` : '–'), el('td', {}, `${e.group_delta > 0 ? '+' : ''}${fmt(e.group_delta)}`)] : null));
      }
      out.push(t, el('p.hint', {}, 'Each player’s count for the round’s goal. Hover a row for the goal.'));
    }
    if (this.replay.finalScores) {
      out.push(el('h3', {}, 'Final scores'), this._scoreTable(this.replay.finalScores),
        el('button.quiet.scorecard-open', { onclick: () => this.scorecard.open() }, 'Show the scorecard'));
      if (this.replay.coop) out.push(el('p.total', { html: `Group score <b>${fmt(this.replay.finalScores.group)}</b> · team total <b>${fmt(this.replay.finalScores.team_total)}</b>` }));
    }
    out.push(el('h3', {}, 'Keys'), el('p.hint', { html: '<kbd>Space</kbd> play / pause · <kbd>→</kbd> play one decision · <kbd>←</kbd> back one · <kbd>Shift</kbd>+<kbd>←</kbd>/<kbd>→</kbd> previous / next turn · <kbd>Home</kbd> / <kbd>End</kbd>. Drag the table to orbit, right-drag to pan, scroll to zoom. Click a card to read it; click a name plate to sit at that seat.' }));
    box.replaceChildren(...out);
  }

  // ------------------------------------------------------------------ inspector

  async _pick(d) {
    const box = $('inspect');
    if (d.type === 'seat') { this._watch(d.seat); return; }
    const bird = d.bird, bonus = d.bonus;
    if (!bird && !bonus && d.type !== 'goal') { box.hidden = true; return; }
    const token = (this._pickToken = {});
    const close = el('button.quiet.close', { onclick: () => { box.hidden = true; }, 'aria-label': 'Close' }, '×');
    if (d.type === 'goal') {
      box.replaceChildren(close, el('h3', {}, `Round ${d.round} goal`), el('p', { html: rich(d.label) }));
      box.hidden = false;
      return;
    }
    const canvas = await (bird ? drawCardFace(bird, { scale: 0.7 }) : drawBonusFace(bonus, { scale: 0.7 }));
    if (this._pickToken !== token) return;
    canvas.className = 'cardimg';
    const facts = [];
    if (bird) {
      const raw = this.book.rawBird(bird.id);
      if (d.type === 'slot') facts.push(`On ${playerName(d.mat)}'s mat (${d.habitat}, column ${d.slot + 1})`);
      if (raw) facts.push(`${raw.vp} point${raw.vp === 1 ? '' : 's'} · ${raw.nest} nest · holds ${raw.egg_limit} egg${raw.egg_limit === 1 ? '' : 's'} · ${raw.wingspan} cm`);
      box.replaceChildren(...[close, canvas, el('h3', {}, bird.name), ...facts.map(f => el('p.hint', {}, f)), bird.power ? el('p', { html: rich(bird.power) }) : null].filter(Boolean));
    } else {
      box.replaceChildren(close, canvas, el('h3', {}, bonus.name), el('p', { html: rich(bonus.condition) }), el('p.hint', { html: rich(bonus.points) }));
    }
    box.hidden = false;
  }
}
