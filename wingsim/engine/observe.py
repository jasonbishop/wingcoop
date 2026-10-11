"""Observations: what one player is allowed to see.

An Observation wraps a redacted copy of the state. Hidden cards are replaced by
HIDDEN, so nothing about the deck order (or, with closed hands, other players'
hands and bonus cards) can leak. `sample()` fills the hidden parts with a
random arrangement of the cards the observer has not seen, which is how search
agents simulate with the engine.
"""
from .state import GROUP

HIDDEN = -1
# Decisions whose options list cards from the decider's hand or bonus cards.
_PRIVATE_DECISIONS = frozenset({"setup_keep_birds", "setup_keep_bonus", "keep_bonus", "tuck_card",
                                "discard_card", "bonus_trade", "action", "play_extra"})


class Observation:
    __slots__ = ("player", "state")

    def __init__(self, player, state):
        self.player = player
        self.state = state

    def sample(self, rng):
        """A full state consistent with this observation. `rng` is a random.Random."""
        s = self.state.copy()
        d = s.cfg.db
        seen = set(s.tray)
        seen.update(s.discard)
        for pl in s.players:
            seen.update(pl.hand)
            for row in pl.board:
                for x in row:
                    seen.add(x[0])
        seen_bonus = set()
        for pl in s.players:
            seen_bonus.update(pl.bonus)
        for f in s.stack:
            if f[0] in ("draft", "draft_pick"):
                seen.update(f[2])
            elif f[0] == "bonus_keep":
                seen_bonus.update(f[2])
        pool = [c for c in d.bird_ids if c not in seen]
        rng.shuffle(pool)
        for pl in s.players:
            pl.hand = [pool.pop() if c == HIDDEN else c for c in pl.hand]
        s.tucked = [pool.pop() for _ in s.tucked]
        if len(pool) != len(s.deck):
            raise AssertionError("unseen birds do not match the hidden slots")
        s.deck = pool
        bpool = [b for b in d.bonus_ids if b not in seen_bonus]
        rng.shuffle(bpool)
        for pl in s.players:
            pl.bonus = [bpool.pop() if b == HIDDEN else b for b in pl.bonus]
        for i, f in enumerate(s.stack):
            if f[0] == "bonus_keep" and HIDDEN in f[2]:
                s.stack[i] = (f[0], f[1], tuple(bpool.pop() for _ in f[2]))
        s.bonus_discard = [bpool.pop() for _ in s.bonus_discard]
        if len(bpool) != len(s.bonus_deck):
            raise AssertionError("unseen bonus cards do not match the hidden slots")
        s.bonus_deck = bpool
        s.rng = rng.getrandbits(64)
        return s


def observe(state, player):
    """What `player` (a seat index, or GROUP for the table as a whole) may see."""
    o = state.copy()
    o.rng = 0
    o.deck = [HIDDEN] * len(o.deck)
    o.tucked = [HIDDEN] * len(o.tucked)
    o.bonus_deck = [HIDDEN] * len(o.bonus_deck)
    o.bonus_discard = [HIDDEN] * len(o.bonus_discard)
    if not o.cfg.open_hands:
        for j, pl in enumerate(o.players):
            if j != player:
                pl.hand = [HIDDEN] * len(pl.hand)
                pl.bonus = [HIDDEN] * len(pl.bonus)
        for i, f in enumerate(o.stack):
            if f[0] == "bonus_keep" and f[1] != player:
                o.stack[i] = (f[0], f[1], (HIDDEN,) * len(f[2]))
        pend = o.pend
        if pend is not None and pend[0] != player and pend[0] != GROUP and pend[1] in _PRIVATE_DECISIONS:
            o.pend = (pend[0], pend[1], None)
    return Observation(player, o)
