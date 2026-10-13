// The log's conventions (docs/replay-log-format.md, section 2) and the card reference
// (section 7) turned into what the table components draw.

import { HABITAT_COLORS, plainText } from '../../components/cards/src/index.js';
import { PLAYER_COLORS } from '../../components/pieces/src/index.js';
import { birdArt } from './birdArt.js';

export const FOODS = ['invertebrate', 'seed', 'fish', 'fruit', 'rodent'];
export const HABITATS = ['forest', 'grassland', 'wetland'];
/** Die faces 0..5 as birdfeeder face keys. */
export const DIE_FACES = [...FOODS, 'invertebrate_seed'];
export const EGG_KINDS = ['blue', 'speckled', 'cream'];
export const SLOTS = 5;

/** Cube colour of each seat (keys of the pieces' PLAYER_COLORS). */
export const SEAT_COLORS = ['blue', 'red', 'yellow', 'green', 'purple'];
export const seatCss = seat => '#' + PLAYER_COLORS[SEAT_COLORS[seat % SEAT_COLORS.length]].toString(16).padStart(6, '0');

const NEST_TINT = '#a08460', PLAIN_TINT = '#6f8fb0';
const cap = s => s.charAt(0).toUpperCase() + s.slice(1);

/** Eggs have no colour in the game; give each bird a steady mix so the table looks natural. */
export function eggKinds(bird, n) {
  return Array.from({ length: n }, (_, k) => EGG_KINDS[(Math.abs(bird) + k) % EGG_KINDS.length]);
}

/** Card data for the components, one stable object per card id. */
export class CardBook {
  constructor(cards) {
    this.cards = cards;
    this._birds = new Map();
    this._bonus = new Map();
    this._goals = new Map();
  }

  /** Raw reference entry for a bird id (or undefined). */
  rawBird(id) { return this.cards.birds[String(id)]; }
  birdName(id) { return this.rawBird(id)?.name ?? (id === -1 ? 'a hidden card' : `bird ${id}`); }
  bonusName(id) { return this.cards.bonus[String(id)]?.name ?? (id === -1 ? 'a hidden bonus card' : `bonus ${id}`); }

  /** `Bird` data for a BirdCard; null for a hidden (-1) or unknown card. */
  bird(id) {
    if (this._birds.has(id)) return this._birds.get(id);
    const b = this.rawBird(id);
    let out = null;
    if (b) {
      const food = [];
      b.cost.forEach((n, f) => { for (let k = 0; k < n; k++) food.push(FOODS[f]); });
      for (let k = 0; k < (b.wild || 0); k++) food.push('wild');
      out = {
        id, name: b.name, points: b.vp,
        habitats: b.habitats.map(h => HABITATS[h]),
        food, foodOr: !!b.either,
        nest: b.nest === 'none' ? undefined : b.nest,
        eggLimit: b.egg_limit, wingspan: b.wingspan,
        power: b.text || '', powerColor: b.color || 'none',
        tags: [b.predator && 'predator', b.flocking && 'flocking'].filter(Boolean),
        image: birdArt(id, b.name),
        caches: b.caches || null,
      };
    }
    this._birds.set(id, out);
    return out;
  }

  /** `Bonus` data for a BonusCard; null for a hidden or unknown card. */
  bonus(id) {
    if (this._bonus.has(id)) return this._bonus.get(id);
    const b = this.cards.bonus[String(id)];
    const out = b ? { id, name: b.name, condition: b.condition, points: b.vp_text } : null;
    this._bonus.set(id, out);
    return out;
  }

  /** A goal tile for the GoalBoard: { key, label, tint, plain }. */
  goal(id) {
    if (this._goals.has(id)) return this._goals.get(id);
    const g = this.cards.goals[String(id)];
    let out = null;
    if (g) {
      let label = plainText(g.text), tint = PLAIN_TINT;
      switch (g.kind) {
        case 'birds_in_habitat': label = `Birds in ${g.param}`; tint = HABITAT_COLORS[g.param]; break;
        case 'eggs_in_habitat': label = `[egg] in ${g.param}`; tint = HABITAT_COLORS[g.param]; break;
        case 'nest_birds_with_egg': label = `${cap(g.param)} birds with [egg]`; tint = NEST_TINT; break;
        case 'eggs_in_nest': label = `[egg] in ${g.param} nests`; tint = NEST_TINT; break;
        case 'egg_sets': label = 'Sets of [egg] in all 3 rows'; break;
        case 'total_birds': label = 'Total birds'; break;
      }
      out = { key: `goal-${id}`, id, label, tint, plain: goalSentence(g) };
    }
    this._goals.set(id, out);
    return out;
  }
}

function goalSentence(g) {
  switch (g.kind) {
    case 'birds_in_habitat': return `Birds in the ${g.param}`;
    case 'eggs_in_habitat': return `Eggs on ${g.param} birds`;
    case 'nest_birds_with_egg': return `${cap(g.param)}-nest birds with at least 1 egg`;
    case 'eggs_in_nest': return `Eggs in ${g.param} nests`;
    case 'egg_sets': return 'Sets of eggs in wetland, grassland and forest';
    case 'total_birds': return 'Total birds';
    default: return plainText(g.text);
  }
}

/** Running score of one player from a state (section 5.3). Bonus cards are only known at the end. */
export function runningScore(state, p, book) {
  let birds = 0, eggs = 0, cached = 0, tucked = 0;
  for (const row of state.players[p].board) {
    for (const b of row) {
      birds += book.rawBird(b.bird)?.vp ?? 0;
      eggs += b.eggs; cached += b.cached; tucked += b.tucked;
    }
  }
  const goals = state.goal_points?.[p] ?? 0;
  return { birds, eggs, cached, tucked, goals, total: birds + eggs + cached + tucked + goals };
}

/** Short description of a seat's agent from the header. */
export function seatLabel(header, seat) {
  const s = header.seats?.[seat];
  if (!s) return '';
  let kind = s.type;
  if (s.type === 'llm') kind = (s.settings?.model || 'llm').split('/').pop();
  else if (s.type === 'greedy') kind = 'greedy bot';
  else if (s.type === 'mcts') kind = 'tree search';
  else if (s.type === 'random') kind = 'random bot';
  return s.w != null ? `${kind} · w ${s.w}` : kind;
}

export const playerName = p => (p === 'group' || p === -1 ? 'The group' : `Player ${p}`);
