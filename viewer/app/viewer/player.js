// ReplayPlayer — moves through a replay's positions and drives the table.
//
// One *step* (log format section 9) is: the board before a decision, who is deciding,
// the options, the option chosen, and what happened next. step() plays one: it shows the
// choice, animates each event it caused, and arrives at the next position.
//
// Events fired (addEventListener):
//   position  { index }                    the current position changed (instantly or by playing)
//   stage     { index, stage, event }      progress inside a step: 'choice', then 'event' per
//                                          event (event = its index), then 'done'
//   playing   { playing }                  autoplay started or stopped

import { tweens } from '../../components/tabletop/src/index.js';
import { applyEvent, cloneState } from './replay/reduce.js';

export class ReplayPlayer extends EventTarget {
  /**
   * @param {object} replay  from buildReplay()
   * @param {import('./scene/GameTable.js').GameTable} game
   */
  constructor(replay, game) {
    super();
    this.replay = replay;
    this.game = game;
    this.index = 0;
    this.playing = false;
    this.speed = 1;
    /** 'turn': the camera follows whose turn it is; 'decider': whoever is deciding; a number: stay at that seat. */
    this.follow = 'turn';
    this._running = null;    // promise of the step being animated
    /** Set to [] to collect { index, event } for animations that did not end where the state says. */
    this.checks = null;
    this._cancel = false;
    this._show(0, false);
  }

  get last() { return this.replay.positions.length - 1; }
  get position() { return this.replay.positions[this.index]; }
  get busy() { return !!this._running; }

  setSpeed(speed) {
    this.speed = speed;
    this.game.setSpeed(speed);
  }

  setFollow(follow) {
    this.follow = follow;
    const seat = this._seatFor(this.position);
    if (seat != null) this.game.focus(seat);
  }

  // Which seat to watch at a position (null = leave the camera alone).
  _seatFor(pos) {
    if (typeof this.follow === 'number') return this.follow;
    if (this.follow === 'free') return null;
    const decider = typeof pos.decision?.player === 'number' ? pos.decision.player : null;
    if (this.follow === 'decider') return decider ?? pos.turn;
    return pos.turn ?? decider;
  }

  // Show a position instantly.
  _show(index, animateCamera = true) {
    this.index = Math.max(0, Math.min(this.last, index));
    const pos = this.position;
    this.game.setState(pos.state, { decision: pos.decision });
    const seat = this._seatFor(pos);
    if (seat != null && seat !== this.game.focusSeat) this.game.focus(seat, { animate: animateCamera });
    this._emit('position', { index: this.index });
  }

  /** Stop whatever is animating and wait until it has unwound. */
  async _stop() {
    this.playing && this._emit('playing', { playing: false });
    this.playing = false;
    if (!this._running) return;
    this._cancel = true;
    let done = false;
    this._running.finally(() => { done = true; });
    // animations are chains of awaits; keep finishing whatever is active until the chain ends
    while (!done) {
      this.game.flush();
      await new Promise(r => setTimeout(r, 0));
    }
    this._cancel = false;
  }

  /** Jump straight to a position. */
  async goto(index) {
    await this._stop();
    this._show(index);
  }

  back() { return this.goto(this.index - 1); }

  /** Jump to the start of the next / previous turn (or round). */
  async jump(list, dir) {
    const here = this.index;
    const target = dir > 0
      ? list.find(x => x.index > here)?.index ?? this.last
      : [...list].reverse().find(x => x.index < here)?.index ?? 0;
    return this.goto(target);
  }

  /** Play one step with animation. Resolves when the next position is showing. */
  async step() {
    if (this._running) { await this.skip(); return; }
    if (this.index >= this.last) return;
    this._running = this._playStep(this.index).finally(() => { this._running = null; });
    await this._running;
  }

  /** Finish the step that is animating right now. */
  async skip() {
    if (!this._running) return;
    const running = this._running;
    let done = false;
    running.finally(() => { done = true; });
    while (!done) {
      this.game.flush();
      await new Promise(r => setTimeout(r, 0));
    }
  }

  async _playStep(index) {
    const pos = this.replay.positions[index];
    const game = this.game;
    const ctx = { decision: pos.decision };
    this._emit('stage', { index, stage: 'choice', event: -1 });
    await tweens.wait(pos.decision?.info?.replies ? 1.1 : 0.55);   // time to read the choice

    const live = cloneState(pos.state);
    for (let k = 0; k < pos.events.length && !this._cancel; k++) {
      const e = pos.events[k];
      this._emit('stage', { index, stage: 'event', event: k });
      if (e.e === 'turn_start' && this.follow === 'turn' && e.p !== game.focusSeat) await game.focus(e.p);
      await game.animate(e, live, { ...ctx, eventIndex: k });
      applyEvent(live, e, ctx);
      if (this._cancel) break;
      // debugging aid: note every event whose animation left the table different from the state
      const before = this.checks ? game.signature() : null;
      game.reconcile(live);
      if (before && before !== game.signature()) this.checks.push({ index, event: e.e, seq: e.seq, before, after: game.signature() });
    }
    if (this._cancel) return;
    this._emit('stage', { index, stage: 'done', event: pos.events.length });
    // the next position is the truth (a snapshot when the log has one)
    this._show(index + 1);
  }

  /** Autoplay from here until the end or pause(). */
  async play() {
    if (this.playing) return;
    if (this._running) await this.skip();
    this.playing = true;
    this._emit('playing', { playing: true });
    while (this.playing && this.index < this.last) {
      await this.step();
      if (this.playing) await tweens.wait(0.25);
    }
    if (this.playing) { this.playing = false; this._emit('playing', { playing: false }); }
  }

  async pause() {
    if (!this.playing) return;
    this.playing = false;
    this._emit('playing', { playing: false });
    await this.skip();
  }

  toggle() { return this.playing ? this.pause() : this.play(); }

  _emit(type, detail) { this.dispatchEvent(new CustomEvent(type, { detail })); }
}
