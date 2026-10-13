// GameTable — the whole game on one table, drawn from a state-shaped object.
//
//   const game = new GameTable({ container, replay });
//   game.setState(position.state, { decision: position.decision });   // instant: jump / scrub
//   await game.animate(event, stateBeforeTheEvent, ctx);              // one event, animated
//   game.reconcile(stateAfterTheEvent);                               // make sure the table agrees
//
// The table never works anything out from rules: setState() shows what the state says
// (section 5 of the log format), and animate() only decides how a logged event should
// move pieces that are already there. A card id of -1 is drawn face down, so the same
// table can show a live player's partial view (section 9).

import * as THREE from 'three';
import { Tabletop, LazySusan, Plaque, tweens, assetsReady, worldPoint } from '../../../components/tabletop/src/index.js';
import { BirdFeeder, seededRandom } from '../../../components/birdfeeder/src/index.js';
import { PlayerMat } from '../../../components/player-mat/src/index.js';
import { GoalBoard } from '../../../components/goal-board/src/index.js';
import { BirdCard, BonusCard, CardDeck, CardPile, CardRow, CardFan, setCardDetail } from '../../../components/cards/src/index.js';
import { createCube, createFirstPlayerToken } from '../../../components/pieces/src/index.js';
import { findBird } from '../replay/reduce.js';
import { CardBook, FOODS, HABITATS, DIE_FACES, SEAT_COLORS, eggKinds, seatCss, seatLabel } from '../data.js';
import { SEAT, CENTRE, SUSAN_RADIUS, tableSize, seatPosition, seatRotation, seatView } from './layout.js';

const v3 = (x, y, z) => new THREE.Vector3(x, y, z);
const TURNS_PER_ROUND = [8, 7, 6, 5];

// ============================================================================ Seat

/** One player's side of the table: mat, food, hand, bonus cards, name plate, turn cubes. */
class Seat {
  constructor(index, header) {
    this.index = index;
    this.color = SEAT_COLORS[index % SEAT_COLORS.length];
    this.object3d = new THREE.Group();
    this.object3d.name = `seat-${index}`;

    this.mat = new PlayerMat({ name: index });
    this.mat.supply.position.set(SEAT.supply[0], 0, SEAT.supply[1]);
    this.object3d.add(this.mat.object3d);

    this.hand = new CardFan({ maxWidth: SEAT.handWidth });
    this.hand.object3d.position.set(SEAT.hand[0], 0, SEAT.hand[1]);
    this.object3d.add(this.hand.object3d);

    this.bonus = new CardFan({ maxWidth: 4.9, gap: 0.15 });
    this.bonus.object3d.position.set(SEAT.bonus[0], 0, SEAT.bonus[1]);
    this.object3d.add(this.bonus.object3d);

    this.plaque = new Plaque();
    this.plaque.object3d.position.set(SEAT.plaque[0], 0, SEAT.plaque[1]);
    this.plaque.object3d.userData.pick = { type: 'seat', seat: index };
    this.plaque.setText({ title: `Player ${index}`, subtitle: seatLabel(header, index), color: seatCss(index) });
    this.object3d.add(this.plaque.object3d);

    this.cubes = new THREE.Group();
    this.cubes.name = 'turn-cubes';
    this.cubes.position.set(SEAT.cubes[0], 0, SEAT.cubes[1]);
    this.object3d.add(this.cubes);
  }

  /** Cubes for the turns this player still has this round. */
  setTurnsLeft(n) {
    while (this.cubes.children.length > n) this.cubes.remove(this.cubes.children[this.cubes.children.length - 1]);
    while (this.cubes.children.length < n) {
      const k = this.cubes.children.length;
      const cube = createCube(this.color);
      cube.position.set((k % 4) * 0.45, 0, Math.floor(k / 4) * 0.45);
      this.cubes.add(cube);
    }
  }

  /** World position of a point given relative to the mat's centre. */
  world(x, z, y = 0) { return worldPoint(this.object3d, v3(x, y, z)); }

  setState(player, state, book) {
    const mat = { supply: {} };
    player.board.forEach((row, h) => {
      mat[HABITATS[h]] = row.map(b => {
        const bird = book.bird(b.bird) || { id: b.bird, name: `Bird ${b.bird}` };
        return {
          bird,
          eggs: eggKinds(b.bird, b.eggs),
          cached: new Array(b.cached).fill(bird.caches || 'seed'),
          tucked: b.tucked,
        };
      });
    });
    player.food.forEach((n, f) => { mat.supply[FOODS[f]] = n; });
    this.mat.setState(mat);
    this.hand.setState(player.hand, id => new BirdCard(book.bird(id), { faceUp: id >= 0 }));
    this.bonus.setState(player.bonus, id => new BonusCard(book.bonus(id), { faceUp: id >= 0 }));
    this.setTurnsLeft(state.phase === 'turns' ? state.actions_left[this.index] : 0);
    this.plaque.setText({ highlight: state.phase === 'turns' && state.turn === this.index });
  }
}

// ============================================================================ GameTable

export class GameTable extends EventTarget {
  /**
   * @param {object} o
   * @param {HTMLElement} o.container
   * @param {object} o.replay            from buildReplay(): header, cards, players
   * @param {'high'|'low'} [o.quality]   'low' halves shadow and card texture sizes
   */
  constructor({ container, replay, quality = 'high' }) {
    super();
    const n = (this.n = replay.players);
    this.book = new CardBook(replay.cards);
    this.seed = Number(replay.header.seed) || 1;
    this.focusSeat = 0;
    this.viewKind = 'seat';
    setCardDetail(quality === 'low' ? 0.4 : 0.6);

    const size = tableSize(n);
    const table = (this.table = new Tabletop({ container, size: [size, size], shape: 'round', shadowMapSize: quality === 'low' ? 2048 : 4096 }));
    table.controls.maxDistance = 190;
    table.addEventListener('pick', e => this.dispatchEvent(new CustomEvent('pick', { detail: e.detail })));

    // ---- the turntable and the shared pieces on it
    const susan = (this.susan = table.add(new LazySusan({ radius: SUSAN_RADIUS })));
    const on = ([x, z], extra = {}) => ({ parent: susan.top, position: [x, 0, z], ...extra });
    this.board = table.add(new GoalBoard(), on(CENTRE.board));
    this.feeder = table.add(
      new BirdFeeder({ scene: susan.top, camera: table.camera, domElement: table.renderer.domElement, clickToTake: false }),
      on(CENTRE.feeder, { scale: CENTRE.feederScale }),
    );
    this.deck = table.add(new CardDeck({ count: 0 }), on(CENTRE.deck));
    this.tray = table.add(new CardRow({ slots: 3, gap: 0.25 }), on(CENTRE.tray));
    this.discard = table.add(new CardPile(), on(CENTRE.discard));
    this.bonusDeck = table.add(new CardDeck({ count: 0, kind: 'bonus' }), on(CENTRE.bonusDeck));
    this.bonusDiscard = table.add(new CardPile({ kind: 'bonus' }), on(CENTRE.bonusDiscard));
    // cards held up for a choice (a draft, or bonus cards to pick from)
    this.offer = table.add(new CardFan({ maxWidth: 7.2, gap: 0.2 }), on(CENTRE.reveal));
    this.offer.object3d.position.y = 0.02;

    // ---- the seats
    this.seats = [];
    for (let i = 0; i < n; i++) {
      const seat = new Seat(i, replay.header);
      table.add(seat, { position: seatPosition(i, n) });
      seat.object3d.rotation.y = seatRotation(i, n);
      this.seats.push(seat);
    }

    this.firstToken = createFirstPlayerToken();
    table.scene.add(this.firstToken);
    this._first = null;
    this._looked = null;     // { id, card }: a deck card a predator is looking at
    this._rolls = 0;

    this.focus(0, { animate: false });
  }

  /** Resolves when the textures loaded so far are ready. */
  get ready() { return Promise.all([assetsReady(), this.feeder.ready]); }

  // ------------------------------------------------------------------ camera

  /**
   * Watch the game from a seat: the turntable turns to face it and the camera swings round.
   * @param {number} seat
   * @param {{animate?:boolean, view?:'seat'|'mat'|'centre'|'table'}} [opts]
   */
  async focus(seat, { animate = true, view = this.viewKind } = {}) {
    this.focusSeat = seat;
    this.viewKind = view;
    await Promise.all([
      this.susan.turnTo(seatRotation(seat, this.n), { animate, duration: 1.0 }),
      this.table.setView(seatView(view, seat, this.n), { animate, duration: 1.1, orbit: true }),
    ]);
  }

  /** Playback speed for every animation on the table. */
  setSpeed(speed) {
    tweens.speed = speed;
    this.feeder.options.speed = speed;
    this.table.cameraSpeed = Math.max(1, speed);
  }

  /** Jump every running animation to its end. */
  flush() {
    tweens.finishAll();
    this.feeder.skip();
    this.table.finishCamera();
  }

  // ------------------------------------------------------------------ state (instant)

  /**
   * Show a state, instantly. Only what differs from the table is rebuilt.
   * @param {object} state                         a state-shaped object (log format section 5)
   * @param {{decision?: object|null}} [opts]      the decision pending in this state, if known
   */
  setState(state, { decision = null } = {}) {
    this.flush();
    if (this._looked) { this._looked.card.dispose(); this._looked = null; }
    this.reconcile(state);
    this._syncOffer(decision);
    this.board.setState(this._boardState(state, decision));
  }

  /**
   * After an animated event: make the table agree with the state. If the animation did
   * its job nothing moves. Cards in mid-choice (held up, looked at) are left alone.
   */
  reconcile(state) {
    const book = this.book;
    this._syncFeeder(state.feeder);
    this.deck.count = state.deck.length;
    this._syncTray(state.tray, { animate: false });
    this.discard.setState({ count: state.discard.length, top: book.bird(state.discard[state.discard.length - 1]) });
    this.bonusDeck.count = state.bonus_deck.length;
    this.bonusDiscard.setState({ count: state.bonus_discard.length, top: book.bonus(state.bonus_discard[state.bonus_discard.length - 1]) });
    this.board.setState(this._boardState(state, null, true));
    state.players.forEach((pl, i) => this.seats[i]?.setState(pl, state, book));
    this._placeFirstToken(state.first, false);
  }

  // The goal board: a cube per player on the square for their count (0 to 5) once a round
  // has been scored, and a ring on the medallion for the round's difficulty (co-op goals).
  _boardState(state, decision, keepMarkers = false) {
    const goals = state.goals.map(id => this.book.goal(id));
    const cubes = [], markers = [];
    for (const [round, counts, , , info] of state.goal_log || []) {
      counts.forEach((c, p) => cubes.push({ round, square: Math.max(0, Math.min(5, c)), color: SEAT_COLORS[p] }));
      if (info && info[0] === 'coop') markers.push({ round, medallion: info[1], color: info[2] ? 'green' : 'red' });
    }
    const round = state.round;
    const live = state.phase !== 'setup' && state.phase !== 'over' && round >= 1 && round <= 4;
    if (keepMarkers) {
      // between events of one step the marker is whatever the animations left
      const cur = this.board.getState().markers.find(m => m.round === round);
      if (cur && !markers.some(m => m.round === round)) markers.push(cur);
    } else {
      const d = state.variant?.['coop.d'];
      // while the group is still choosing, the difficulty in the state is last round's
      if (live && d != null && decision?.kind !== 'set_difficulty' && !markers.some(m => m.round === round)) {
        markers.push({ round, medallion: d, color: 'gold' });
      }
    }
    return { goals, cubes, markers, active: live ? round : null };
  }

  _syncFeeder(faces) {
    const want = faces.map(f => DIE_FACES[f]);
    const have = this.feeder.getDice().filter(d => !d.taken).map(d => d.face);
    if (want.length === have.length && [...want].sort().join() === [...have].sort().join()) return;
    this.feeder.setDice(want);
  }

  // Put these birds in the tray, left to right. Cards already there slide to their new
  // place; when animated, missing ones are drawn from the deck and ones no longer wanted
  // go to the discard pile.
  _syncTray(ids, { animate }) {
    const row = this.tray;
    const have = new Map();
    row.slots.forEach(c => { if (c) have.set(c.bird?.id, c); });
    const next = new Array(row.slots.length).fill(null);
    const jobs = [];
    let drawn = 0;
    ids.slice(0, next.length).forEach((id, i) => {
      let card = have.get(id);
      const to = row.slotPosition(i);
      if (card) {
        have.delete(id);
        if (card.object3d.parent !== row.object3d || card.object3d.position.distanceToSquared(to) > 1e-8) {
          jobs.push(card.moveTo(row.object3d, to, { faceUp: true, animate, duration: 0.35, arc: 0 }));
        }
      } else if (animate) {
        card = this.deck.lift(this.book.bird(id));
        jobs.push(card.moveTo(row.object3d, to, { faceUp: true, duration: 0.7, arc: 1.4, delay: 0.25 + 0.15 * drawn++ }));
      } else {
        card = new BirdCard(this.book.bird(id), { faceUp: id >= 0 });
        card.moveTo(row.object3d, to, { animate: false });
      }
      next[i] = card;
    });
    let k = 0;
    for (const card of have.values()) {
      if (animate) jobs.push(this.discard.add(card, { delay: 0.1 * k++ }));
      else card.dispose();
    }
    row.slots = next;
    return Promise.all(jobs);
  }

  // Cards held up for the pending choice. They are not in the state (they have left the
  // deck and are not yet anywhere else); the decision's options name them.
  _syncOffer(decision) {
    let keys = [], make = () => null;
    if (decision?.kind === 'draft_pick') {
      keys = decision.options.filter(o => o[0] === 'card').map(o => o[1]);
      make = id => new BirdCard(this.book.bird(id), { faceUp: true });
    } else if (decision?.kind === 'keep_bonus') {
      keys = decision.options.filter(o => o[0] === 'bonus').map(o => `b${o[1]}`);
      make = key => new BonusCard(this.book.bonus(Number(key.slice(1))), { faceUp: true });
    }
    this.offer.setState(keys, make);
  }

  _placeFirstToken(seat, animate) {
    if (seat == null || !this.seats[seat]) return null;
    const to = this.seats[seat].world(SEAT.firstToken[0], SEAT.firstToken[1]);
    if (this._first === seat && this.firstToken.position.distanceToSquared(to) < 1e-6) return null;
    this._first = seat;
    if (!animate) { this.firstToken.position.copy(to); return null; }
    return tweens.to(this.firstToken, { position: to }, { duration: 0.9, arc: 2.5 });
  }

  /** Everything on the table as plain data (for checks: two equal signatures look the same). */
  signature() {
    return JSON.stringify({
      feeder: this.feeder.getDice().filter(d => !d.taken).map(d => d.face).sort(),
      deck: this.deck.count,
      tray: this.tray.slots.map(c => c?.bird?.id ?? null),
      discard: [this.discard.count, this.discard.getState().top?.id ?? null],
      bonusDeck: this.bonusDeck.count,
      bonusDiscard: [this.bonusDiscard.count, this.bonusDiscard.getState().top?.id ?? null],
      board: this.board.getState(),
      first: this._first,
      seats: this.seats.map(s => {
        const m = s.mat.getState();
        for (const h of HABITATS) m[h] = m[h].map(x => x && { ...x, bird: x.bird?.id });
        return { mat: m, hand: s.hand.keys, bonus: s.bonus.keys, cubes: s.cubes.children.length };
      }),
    });
  }

  // ------------------------------------------------------------------ events (animated)

  /**
   * Animate one event.
   * @param {object} e      an event line
   * @param {object} state  the state before the event
   * @param {{decision?: object, eventIndex?: number}} [ctx]
   */
  async animate(e, state, ctx = {}) {
    const fn = this[`_on_${e.e}`];
    if (fn) await fn.call(this, e, state, ctx);
    else await tweens.wait(0.12);
  }

  _where(state, p, bird) {
    const at = findBird(state, p, bird);
    return at ? { ...at, habitat: HABITATS[at.habitat] } : null;
  }

  async _pulse(seat, at) {
    if (!at) return;
    const g = seat.mat.slotGroup(at.habitat, at.slot);
    const base = seat.mat.slotPosition(at.habitat, at.slot);
    await tweens.to(g, { position: base.clone().add(v3(0, 0.5, 0)) }, { duration: 0.16, ease: 'out' });
    await tweens.to(g, { position: base }, { duration: 0.28 });
    g.position.copy(base);
  }

  async _on_setup_kept_birds(e, state) {
    const seat = this.seats[e.p];
    const out = state.players[e.p].hand.filter(b => !e.birds.includes(b));
    await Promise.all(out.map((b, k) => {
      const card = seat.hand.take(b);
      return card && this.discard.add(card, { delay: 0.12 * k });
    }));
  }

  async _on_setup_discarded_food(e) {
    await Promise.all(e.food.map(f => this.seats[e.p].mat.spendFood(FOODS[f])));
  }

  async _on_bonus_kept(e, state) {
    const seat = this.seats[e.p];
    if (state.phase === 'setup') {
      const out = state.players[e.p].bonus.filter(b => b !== e.bonus);
      await Promise.all(out.map(b => {
        const card = seat.bonus.take(b);
        return card && this.bonusDiscard.add(card);
      }));
      return;
    }
    // a power: the kept card comes from the ones held up, the rest are discarded
    const kept = this.offer.take(`b${e.bonus}`) || this.bonusDeck.lift(this.book.bonus(e.bonus));
    const rest = this.offer.keys.map(key => this.offer.take(key));
    await Promise.all([
      seat.bonus.add(e.bonus, kept, { faceUp: true }),
      ...rest.map(card => this.bonusDiscard.add(card)),
    ]);
  }

  async _on_group_decision(e, state) {
    if (e.kind === 'set_difficulty') await this.board.setMarker(state.round, e.choice[1], { color: 'gold' });
    await tweens.wait(0.25);
  }

  async _on_round_start(e) {
    for (const seat of this.seats) seat.setTurnsLeft(TURNS_PER_ROUND[e.round - 1] ?? 0);
    await Promise.all([this.board.setActiveRound(e.round), this._placeFirstToken(e.first, true)]);
  }

  async _on_turn_start(e) {
    for (const seat of this.seats) seat.plaque.setText({ highlight: seat.index === e.p });
    await tweens.wait(0.15);
  }

  async _on_action() { await tweens.wait(0.2); }

  async _on_food_spent(e) {
    const mat = this.seats[e.p].mat, jobs = [];
    e.food.forEach((n, f) => { for (let k = 0; k < n; k++) jobs.push(mat.spendFood(FOODS[f])); });
    await Promise.all(jobs);
  }

  async _on_egg_discarded(e, state) {
    const at = this._where(state, e.p, e.bird);
    if (at) await this.seats[e.p].mat.removeEggs(at.habitat, at.slot, 1);
  }

  async _on_card_discarded(e) {
    const seat = this.seats[e.p];
    const card = seat.hand.take(e.bird);
    if (card) await this.discard.add(card);
  }

  async _on_bird_played(e) {
    const seat = this.seats[e.p];
    const card = seat.hand.take(e.bird) || this.book.bird(e.bird);
    await seat.mat.playBird(HABITATS[e.habitat], e.slot, card, { duration: 0.75 });
  }

  async _on_die_taken(e) {
    const mat = this.seats[e.p].mat;
    const die = this.feeder.getDice().find(d => !d.taken && d.face === DIE_FACES[e.face]);
    let from = null;
    if (die) { from = this.feeder.dieWorldPosition(die.index); this.feeder.take(die.index); }
    await mat.addFood(FOODS[e.food], { from });
  }

  async _on_feeder_reset(e, state, ctx) {
    const random = seededRandom(this.seed * 7919 + e.seq * 31 + (ctx.eventIndex || 0));
    await this.feeder.roll({ faces: e.dice.map(f => DIE_FACES[f]), random });
    await tweens.wait(0.2);
  }

  async _on_food_gained(e) {
    const mat = this.seats[e.p].mat;
    await Promise.all(Array.from({ length: e.n }, (_, k) => tweens.wait(0.12 * k + 0.001).then(() => mat.addFood(FOODS[e.food]))));
  }

  async _on_cards_drawn(e) {
    const seat = this.seats[e.p];
    for (const b of e.birds) {
      let card = null, opts = { faceUp: true };
      if (e.source === 'tray') {
        const i = this.tray.slots.findIndex(c => c?.bird?.id === b);
        if (i >= 0) card = this.tray.take(i);
      } else if (e.source === 'draft') card = this.offer.take(b);
      if (!card) { card = this.deck.lift(this.book.bird(b)); opts = { faceUp: b >= 0, arc: 1.6, duration: 0.8 }; }
      await seat.hand.add(b, card, opts);
    }
    // the cards left in the tray close up to the left
    if (e.source === 'tray') await this._syncTray(this.tray.slots.filter(Boolean).map(c => c.bird?.id), { animate: true });
  }

  async _on_cards_revealed(e, state) {
    for (const b of e.birds) {
      const i = this.tray.slots.findIndex(c => c?.bird?.id === b);
      let card;
      if (i >= 0) card = this.tray.take(i);
      else if (state.deck.includes(b)) card = this.deck.lift(this.book.bird(b));
      else {
        // taken earlier by a draw that logged no event: it is already off the deck
        card = new BirdCard(this.book.bird(b), { faceUp: false });
        this.deck.object3d.add(card.object3d);
        card.object3d.position.copy(this.deck.top);
      }
      await this.offer.add(b, card, { faceUp: true, duration: 0.5 });
    }
  }

  async _on_card_tucked(e, state) {
    const seat = this.seats[e.p];
    const at = this._where(state, e.p, e.bird);
    if (!at) return;
    let card;
    if (e.source === 'hand') card = seat.hand.take(e.card ?? -1);
    else if (this._looked && this._looked.id === e.card) card = this._looked.card;
    else card = this.deck.lift(this.book.bird(e.card ?? -1));
    this._looked = null;
    await seat.mat.tuck(at.habitat, at.slot, 1, { from: card ? [card] : [] });
  }

  async _on_predator(e, state) {
    const seat = this.seats[e.p];
    if (e.kind !== 'look') { await tweens.wait(0.5); return; }
    // hold the deck's top card up beside the deck, then tuck it (the next event) or discard it
    const card = this.deck.lift(this.book.bird(e.card));
    await card.moveTo(this.susan.top, v3(CENTRE.deck[0], 1.1, CENTRE.deck[1] - 2.3), { faceUp: true, duration: 0.55, arc: 0.6 });
    await tweens.wait(0.45);
    if (e.success) this._looked = { id: e.card, card };
    else await this.discard.add(card);
    void seat;
  }

  async _on_eggs_laid(e, state) {
    const at = this._where(state, e.p, e.bird);
    if (!at) return;
    const kinds = eggKinds(e.bird, at.entry.eggs + e.n).slice(at.entry.eggs);
    await this.seats[e.p].mat.layEggs(at.habitat, at.slot, e.n, kinds);
  }

  async _on_food_cached(e, state) {
    const at = this._where(state, e.p, e.bird);
    if (!at) return;
    for (let k = 0; k < e.n; k++) {
      await this.seats[e.p].mat.cacheFood(at.habitat, at.slot, FOODS[e.food], { fromSupply: e.source === 'player' });
    }
  }

  async _on_power(e, state) {
    await this._pulse(this.seats[e.p], this._where(state, e.p, e.bird));
  }

  async _on_bird_moved(e, state) {
    const seat = this.seats[e.p];
    const at = this._where(state, e.p, e.bird);
    if (!at) return;
    const card = seat.mat.removeBird(at.habitat, at.slot);
    await seat.mat.playBird(HABITATS[e.to], state.players[e.p].board[e.to].length, card, { duration: 0.75 });
  }

  async _on_tray_refill(e, state) {
    await this._syncTray(e.tray, { animate: true });
    // during a round this is also the end of the turn: that player has one turn fewer left
    if (state.phase === 'turns') this.seats[state.turn]?.setTurnsLeft(state.actions_left[state.turn] - 1);
  }

  async _on_deck_reshuffled() { await tweens.wait(0.3); }

  async _on_round_end(e, state) {
    for (let p = 0; p < e.counts.length; p++) {
      const from = this.seats[p].world(SEAT.plaque[0], SEAT.plaque[1], 1);
      await this.board.placeCube(e.round, { square: Math.max(0, Math.min(5, e.counts[p])) }, SEAT_COLORS[p], { from });
    }
    if (e.info && e.info[0] === 'coop') await this.board.setMarker(e.round, e.info[1], { color: e.info[2] ? 'green' : 'red' });
    for (const seat of this.seats) seat.setTurnsLeft(0);
    await tweens.wait(0.6);
    // the first-player token passes to the left and the next round's goal comes up
    await Promise.all([
      this.board.setActiveRound(e.round < 4 ? e.round + 1 : null),
      this._placeFirstToken((state.first + 1) % this.n, true),
    ]);
  }

  async _on_final_scoring() {
    await this.board.setActiveRound(null);
    await tweens.wait(0.3);
  }

  dispose() {
    this.flush();
    this.table.dispose();
  }
}
