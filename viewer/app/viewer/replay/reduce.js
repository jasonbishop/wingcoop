// Applies replay-log events to a state object (docs/replay-log-format.md, sections 4.6 and 8).
//
// The state is the `state` object of a snapshot. Logs with a snapshot before every
// decision never need this to find a position, but the viewer still uses it to know
// what the table looks like between two events of one step. Logs with per-turn
// snapshots need it for every position inside a turn.
//
// Only the fields a viewer draws are maintained. Engine internals (rng, stack,
// registers, pending) are dropped by cloneState().

/** Fields the viewer draws; everything else in a snapshot is ignored. */
export const VIEW_FIELDS = [
  'phase', 'round', 'turn_no', 'first', 'turn', 'actions_left',
  'deck', 'discard', 'tray', 'feeder', 'bonus_deck', 'bonus_discard', 'tucked',
  'goals', 'goal_points', 'group_score', 'goal_log', 'players', 'variant',
  'looked',   // reducer bookkeeping, not part of a snapshot: a deck card a predator is looking at
];

/** A deep copy of the viewer-relevant part of a state. */
export function cloneState(state) {
  const out = {};
  for (const k of VIEW_FIELDS) if (state[k] !== undefined) out[k] = structuredClone(state[k]);
  return out;
}

/** Find a bird on a player's mat: { habitat, slot, entry } or null. */
export function findBird(state, p, bird) {
  const board = state.players[p]?.board;
  if (!board) return null;
  for (let h = 0; h < board.length; h++) {
    const slot = board[h].findIndex(b => b.bird === bird);
    if (slot >= 0) return { habitat: h, slot, entry: board[h][slot] };
  }
  return null;
}

/** Find a bird on any mat: { p, habitat, slot, entry } or null. */
export function findBirdAnywhere(state, bird) {
  for (let p = 0; p < state.players.length; p++) {
    const at = findBird(state, p, bird);
    if (at) return { p, ...at };
  }
  return null;
}

const TURNS_PER_ROUND = [8, 7, 6, 5];

function removeOne(list, value) {
  const i = list.indexOf(value);
  if (i >= 0) list.splice(i, 1);
  return i >= 0;
}

// A hidden card (-1) stands in for any card of a list in a live player's view.
function removeCard(list, card) {
  return removeOne(list, card) || removeOne(list, -1);
}

function popDeck(state, card) {
  const deck = state.deck;
  if (!deck.length) return;
  if (card != null && deck[deck.length - 1] !== card && deck[deck.length - 1] !== -1) {
    // not the top card: take it from wherever it is rather than corrupt the count
    if (removeOne(deck, card)) return;
  }
  deck.pop();
}

const HANDLERS = {
  setup(s, e) {
    s.goals = e.goals.slice();
    s.first = e.first;
    s.tray = e.tray.slice();
    s.feeder = e.feeder.slice();
  },

  setup_kept_birds(s, e) {
    const pl = s.players[e.p];
    for (const b of pl.hand) if (!e.birds.includes(b)) s.discard.push(b);
    pl.hand = e.birds.slice();
  },

  setup_discarded_food(s, e) {
    for (const f of e.food) s.players[e.p].food[f]--;
  },

  bonus_kept(s, e, ctx) {
    const pl = s.players[e.p];
    if (s.phase === 'setup') {
      for (const b of pl.bonus) if (b !== e.bonus) s.bonus_discard.push(b);
      pl.bonus = [e.bonus];
      return;
    }
    // A power: two cards came off the bonus deck, one was kept. The offered cards are
    // the options of the keep_bonus decision that caused this event.
    const offered = ctx?.decision?.kind === 'keep_bonus'
      ? ctx.decision.options.map(o => o[1])
      : [e.bonus];
    for (const b of offered) {
      // No event reports the bonus discard pile being shuffled into a new bonus deck;
      // a card that can only have come from the discard pile shows that it happened.
      if (!s.bonus_deck.includes(b) && s.bonus_discard.includes(b)) {
        s.bonus_deck = s.bonus_deck.concat(s.bonus_discard);
        s.bonus_discard = [];
      }
      removeOne(s.bonus_deck, b);
    }
    for (const b of offered) if (b !== e.bonus) s.bonus_discard.push(b);
    if (!pl.bonus.includes(e.bonus)) pl.bonus.push(e.bonus);
  },

  group_decision(s, e) {
    if (e.kind === 'set_difficulty') s.variant = { ...s.variant, 'coop.d': e.choice[1] };
  },

  round_start(s, e) {
    s.round = e.round;
    s.first = e.first;
    s.turn = e.first;
    s.actions_left = s.players.map(() => TURNS_PER_ROUND[e.round - 1]);
    s.phase = 'turns';
  },

  turn_start(s, e) {
    s.turn = e.p;
    s.turn_no = e.turn_no;
    s.round = e.round;
    s.phase = 'turns';
    s.players[e.p].pink_used = [];
  },

  action() {},

  food_spent(s, e) {
    const food = s.players[e.p].food;
    e.food.forEach((n, f) => { food[f] -= n; });
  },

  egg_discarded(s, e) {
    const at = findBird(s, e.p, e.bird);
    if (at) at.entry.eggs--;
  },

  card_discarded(s, e) {
    removeCard(s.players[e.p].hand, e.bird);
    s.discard.push(e.bird);
  },

  bird_played(s, e) {
    removeCard(s.players[e.p].hand, e.bird);
    s.players[e.p].board[e.habitat].splice(e.slot, 0, { bird: e.bird, eggs: 0, cached: 0, tucked: 0 });
  },

  die_taken(s, e) {
    removeOne(s.feeder, e.face);
    s.players[e.p].food[e.food]++;
  },

  feeder_reset(s, e) {
    s.feeder = e.dice.slice();
  },

  food_gained(s, e) {
    s.players[e.p].food[e.food] += e.n;
  },

  cards_drawn(s, e) {
    for (const b of e.birds) {
      if (e.source === 'tray') removeOne(s.tray, b);
      else if (e.source === 'deck') popDeck(s, b);
      s.players[e.p].hand.push(b);
    }
  },

  cards_revealed(s, e) {
    // American Oystercatcher: the cards were taken one at a time from the tray or the
    // deck by draw_card decisions that log no event of their own; this is the first
    // event to name them. A snapshot taken in between already has them removed.
    for (const b of e.birds) if (!removeOne(s.tray, b)) removeOne(s.deck, b);
  },

  card_tucked(s, e) {
    if (e.source === 'hand') removeCard(s.players[e.p].hand, e.card ?? -1);
    // A card a predator has just looked at is already off the deck (see `predator`).
    else if (e.source === 'deck' && !(e.card != null && e.card === s.looked)) popDeck(s, e.card);
    s.looked = null;
    const at = findBird(s, e.p, e.bird);
    if (at) at.entry.tucked++;
    s.tucked.push(e.card ?? -1);
  },

  eggs_laid(s, e) {
    const at = findBird(s, e.p, e.bird);
    if (at) at.entry.eggs += e.n;
  },

  food_cached(s, e) {
    const at = findBird(s, e.p, e.bird);
    if (at) at.entry.cached += e.n;
    if (e.source === 'player') s.players[e.p].food[e.food] -= e.n;
  },

  power(s, e) {
    if (e.color === 'pink') {
      const used = s.players[e.p].pink_used;
      if (!used.includes(e.bird)) used.push(e.bird);
    }
  },

  predator(s, e) {
    if (e.kind !== 'look') return;
    // The card leaves the deck when it is looked at. A hit is followed by its own
    // card_tucked event; a miss goes to the discard pile with no further event.
    popDeck(s, e.card);
    if (e.success) s.looked = e.card;
    else s.discard.push(e.card);
  },

  bird_moved(s, e) {
    const board = s.players[e.p].board;
    const i = board[e.source].findIndex(b => b.bird === e.bird);
    if (i < 0) return;
    const [entry] = board[e.source].splice(i, 1);
    board[e.to].push(entry);
  },

  tray_refill(s, e) {
    const before = s.tray;
    // cards that left the tray without being drawn were cleared to the discard pile (round end)
    for (const b of before) if (!e.tray.includes(b)) s.discard.push(b);
    for (const b of e.tray) if (!before.includes(b)) popDeck(s, b);
    s.tray = e.tray.slice();
    // During the turns of a round this event is also the end of the turn.
    if (s.phase === 'turns') {
      s.actions_left[s.turn]--;
      s.turn = (s.turn + 1) % s.players.length;
      s.turn_no++;
    }
  },

  deck_reshuffled(s, e) {
    // The event carries only a count, so the new order is unknown: keep the right cards
    // in some order and let popDeck() find each one as it is drawn.
    if (Array.isArray(e.cards)) s.deck = e.cards.slice();
    else s.deck = s.discard.slice();
    s.discard = [];
  },

  round_end(s, e) {
    s.goal_log.push([e.round, e.counts, e.points, e.group_delta, e.info]);
    s.group_score = e.group_score;
    e.points.forEach((pts, p) => { s.goal_points[p] += pts; });
    s.first = (s.first + 1) % s.players.length;
    s.round = e.round + 1;
    s.phase = 'round_end';
  },

  final_scoring(s) {
    s.phase = 'over';
  },
};

/**
 * Apply one event in place.
 * @param {object} state  a cloneState() copy
 * @param {object} event  an event line
 * @param {{decision?: object}} [ctx]  the decision line that caused the event, when known
 * @returns {boolean} false if the event name is not known
 */
export function applyEvent(state, event, ctx) {
  const fn = HANDLERS[event.e];
  if (!fn) return false;
  fn(state, event, ctx);
  return true;
}

/** Apply a list of events to a copy of `state` and return the copy. */
export function applyEvents(state, events, ctx) {
  const s = cloneState(state);
  for (const e of events) applyEvent(s, e, ctx);
  return s;
}

export const KNOWN_EVENTS = Object.keys(HANDLERS);
