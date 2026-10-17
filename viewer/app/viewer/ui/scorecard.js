// The end-of-game scorecard, drawn like the paper score pad: a row per scoring category, a
// column per player, numbers in pen. With co-op goals the round goals belong to the team, so
// they get their own section and column, and the card ends with the combined score
// (players' totals + team score = team_total, format section 5.3).

import { el, rich } from './rich.js';
import { fmt } from '../describe.js';
import { seatCss, seatLabel, playerName } from '../data.js';
import { FOOD_ICONS, EGG_ICONS } from '../../../components/pieces/src/index.js';

const $ = id => document.getElementById(id);

const CARD_BACK = new URL('../../../components/cards/assets/card_back.jpg', import.meta.url).href;
const BONUS_BACK = new URL('../../../components/cards/assets/bonus_back.jpg', import.meta.url).href;

const img = (src, cls) => el('img', { class: cls, src, alt: '' });
const ICONS = {
  birds: () => img(CARD_BACK, 'ic-card'),
  bonus: () => img(BONUS_BACK, 'ic-card'),
  goals: () => el('span.ic-goal', {}, '★'),
  eggs: () => img(EGG_ICONS.cream, 'ic-egg'),
  cached: () => el('span.ic-pair', {}, img(FOOD_ICONS.seed, 'ic-food'), img(FOOD_ICONS.fish, 'ic-food')),
  tucked: () => el('span.ic-pair.ic-tuck', {}, img(CARD_BACK, 'ic-card'), img(CARD_BACK, 'ic-card')),
};
const ROWS = [
  ['birds', 'Birds'], ['bonus', 'Bonus cards'], ['goals', 'End-of-round goals'],
  ['eggs', 'Eggs'], ['cached', 'Food on cards'], ['tucked', 'Tucked cards'],
];

const minus = s => s.replace(/^-/, '−');
const signed = x => (x > 0 ? `+${fmt(x)}` : minus(fmt(x)));

/** The scorecard sheet for a finished game, or null if the log has no final scoring. */
export function scorecard(replay, book, { onClose } = {}) {
  const fs = replay.finalScores;
  if (!fs) return null;
  const h = replay.header, n = fs.players.length, coop = replay.coop;
  const state = replay.positions.at(-1).state;
  const cols = n + 1 + (coop ? 1 : 0);
  const pen = (text, cls = '') => el('td', { class: `pen ${cls}` }, text);
  const blank = () => el('td.na');
  const section = text => el('tr.section', {}, el('th', { colspan: cols }, text));

  const head = el('tr.names', {}, el('th'),
    fs.players.map((_, p) => el('th.player', { style: { '--seat': seatCss(p) } },
      el('span.name', {}, el('span.dot'), el('span.long', {}, playerName(p)), el('span.short', {}, `P${p}`)), el('span.agent', { title: seatLabel(h, p) }, seatLabel(h, p)))),
    coop ? el('th.player.team', {}, el('span.name', {}, 'Team'), el('span.agent', {}, 'co-op goals')) : null);

  // individual scores
  const best = Math.max(...fs.players.map(p => p.total));
  const indiv = [section(coop ? 'Individual scores' : 'Scores')];
  for (const [key, label] of ROWS) {
    if (key === 'goals' && coop) continue;   // under co-op goals they are the team's (below)
    indiv.push(el('tr', {}, el('th', {}, el('span.ic', {}, ICONS[key]()), label),
      fs.players.map(p => pen(minus(fmt(p[key])))), coop ? blank() : null));
  }
  indiv.push(el('tr.subtotal', {}, el('th', {}, coop ? 'Individual total' : 'Total'),
    fs.players.map(p => pen(fmt(p.total), !coop && p.total === best ? 'circled' : '')), coop ? blank() : null));

  // team score: one row per round goal, each player's count, and what it did to the group score
  const team = [];
  if (coop) {
    team.push(section('Team score'));
    team.push(el('tr.colnote', {}, el('th', {}, 'Round goal'), el('td', { colspan: n }, "each player's count"), el('td.teamcol', {}, 'points')));
    for (const [round, counts, , delta, info] of state.goal_log || []) {
      const goal = book.goal(state.goals?.[round - 1]);
      const co = info && info[0] === 'coop';
      team.push(el('tr.round', {},
        el('th', {}, el('span.ic', {}, el('span.ic-round', {}, `R${round}`)),
          el('span.goal', {}, el('span', { html: rich(goal?.label ?? `goal ${state.goals?.[round - 1]}`) }),
            co ? el('small', {}, `difficulty ${info[1]}`) : null)),
        counts.map(c => pen(String(c), 'count')),
        el('td', { class: `pen teamcol ${co ? (info[2] ? 'met' : 'missed') : ''}` },
          co ? el('span.result', { title: info[2] ? 'Goal met' : 'Goal missed' }, info[2] ? '✓' : '✗') : null, signed(delta))));
    }
    team.push(el('tr.subtotal', {}, el('th', {}, 'Team total'), el('td.na', { colspan: n }), pen(signed(fs.group), 'teamcol')));
  }

  // the bottom line
  const foot = [];
  if (coop) {
    const parts = [...fs.players.map(p => fmt(p.total)), fs.group < 0 ? `(${minus(fmt(fs.group))})` : fmt(fs.group)];
    const target = h.config?.team_target;
    foot.push(el('tr.combined', {}, el('th', {}, 'Combined score'),
      el('td', { colspan: n + 1 },
        el('span.sum', {}, `${parts.join(' + ')} =`), el('span.pen.big.circled', {}, fmt(fs.team_total)))));
    if (target != null) {
      foot.push(el('tr.target', {}, el('th', {}, 'Team target'),
        el('td', { colspan: n + 1 }, `${fmt(target)}: ${fs.team_total >= target ? 'reached' : `missed by ${fmt(target - fs.team_total)}`}`)));
    }
  } else {
    const winners = fs.players.map((p, i) => (p.total === best ? playerName(i) : null)).filter(Boolean);
    foot.push(el('tr.combined', {}, el('th', {}, winners.length > 1 ? 'Tied' : 'Winner'),
      el('td', { colspan: n }, el('span.pen.big', {}, winners.join(' & ')))));
  }

  return el('div.sheet', { role: 'dialog', 'aria-modal': 'true', 'aria-label': 'Scorecard' },
    el('button.close', { title: 'Close (Esc)', 'aria-label': 'Close', onclick: () => onClose?.() }, '✕'),
    el('header', {}, el('h2', {}, 'Wingspan'), el('p', {}, coop ? 'Co-op score sheet' : 'Score sheet')),
    el('p.game', {}, [h.title || h.experiment, h.seed != null ? `seed ${h.seed}` : null, `${n} players`].filter(Boolean).join(' · ')),
    el('div.scroll', {}, el('table.sc', { style: { '--players': n } },
      el('thead', {}, head), el('tbody', {}, indiv), coop ? el('tbody', {}, team) : null, el('tfoot', {}, foot))));
}

/** The overlay that holds the scorecard: open(), close(), and Escape or a click outside closes it. */
export class Scorecard {
  constructor(replay, book) {
    this.replay = replay;
    this.book = book;
    this.root = $('scorecard');
    this._onClick = e => { if (e.target === this.root) this.close(); };
    this._onKey = e => { if (e.key === 'Escape' && this.isOpen) { e.stopPropagation(); this.close(); } };
    this.root.addEventListener('click', this._onClick);
    window.addEventListener('keydown', this._onKey, true);
  }

  get available() { return !!this.replay.finalScores; }
  get isOpen() { return !this.root.hidden; }

  open() {
    const sheet = scorecard(this.replay, this.book, { onClose: () => this.close() });
    if (!sheet) return;
    this.root.replaceChildren(sheet);
    this.root.hidden = false;
    sheet.querySelector('.close').focus({ preventScroll: true });
  }

  close() {
    if (this.root.hidden) return;
    this.root.hidden = true;
    this.root.replaceChildren();
  }

  dispose() {
    this.close();
    this.root.removeEventListener('click', this._onClick);
    window.removeEventListener('keydown', this._onKey, true);
  }
}
