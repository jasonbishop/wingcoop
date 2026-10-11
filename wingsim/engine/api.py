"""The engine API: the only way agents and plugins touch the game.

    new_game(config, seed) -> State
    pending_decision(state) -> Decision | None   # player, kind, legal options, context
    apply(state, decision, choice) -> State      # raises IllegalChoice on an illegal choice
    observe(state, player) -> Observation        # what that player is allowed to see
    is_over(state) / final_scores(state)
"""
from collections import namedtuple

from . import rules, scoring
from .config import GameConfig
from .observe import HIDDEN, Observation, observe
from .rules import IllegalChoice
from .state import GROUP, OVER, SETUP, TURNS, PRE_ROUND

__all__ = ["GameConfig", "Decision", "GROUP", "HIDDEN", "IllegalChoice", "Observation", "new_game",
           "pending_decision", "apply", "apply_in_place", "observe", "is_over", "final_scores", "scores",
           "totals", "goal_counts", "score_goal_counts", "simulate_turn", "play_random", "turns_left", "round_turns_left"]

Decision = namedtuple("Decision", "player kind options context")


def new_game(config, seed):
    return rules.deal(config, seed)


def pending_decision(state):
    pend = state.pend
    if pend is None:
        return None
    return Decision(pend[0], pend[1], pend[2], {"round": state.round, "turn_no": state.turn_no,
                                                 "turn": state.turn, "frame": state.stack[-1][0]})


def apply(state, decision, choice):
    """Answer the pending decision. Returns a new state; the given one is unchanged."""
    pend = state.pend
    if pend is None:
        raise IllegalChoice("no decision is pending")
    if decision is not None and (decision.player != pend[0] or decision.kind != pend[1]):
        raise IllegalChoice("that is not the pending decision")
    s = state.copy(events=True)
    rules.resume(s, choice)
    return s


def apply_in_place(state, choice):
    """Like apply, but changes the given state. For simulations on private copies."""
    rules.resume(state, choice)


def is_over(state):
    return state.phase == OVER


def final_scores(state):
    return scoring.final_scores(state)


def scores(state):
    """Score breakdown for the state as it stands (provisional before the game ends)."""
    return scoring.breakdown(state)


def totals(state):
    return scoring.totals(state)


def goal_counts(state):
    """Each player's count for the current round's goal, or None after round 4."""
    return scoring.current_goal_counts(state)


def score_goal_counts(state, counts):
    """What the current round's goal would score for the given counts:
    (points per player, group score change, info)."""
    return scoring.score_goal_counts(state, counts)


_FUTURE = (sum(rules.ACTIONS_PER_ROUND[r:]) for r in range(5))
_FUTURE = tuple(_FUTURE)  # _FUTURE[r] = turns per player in rounds r+1..4 (r counted from 0)


def round_turns_left(state, j):
    """Turns player j still has in the current round."""
    if state.phase == TURNS:
        return state.actions_left[j]
    if state.phase in (SETUP, PRE_ROUND):
        return rules.ACTIONS_PER_ROUND[state.round - 1]
    return 0


def turns_left(state, j):
    """Turns player j still has in the whole game."""
    if state.round > 4:
        return 0
    return round_turns_left(state, j) + _FUTURE[state.round]


def simulate_turn(state, player, habitat, chooser):
    """Play out one use of a habitat action by `player` on a copy of the state, in isolation.

    `chooser(state, pending)` answers every choice that comes up, for any player.
    Used by agents to measure what a row (its base action plus its bird powers)
    produces. Returns the resulting state.
    """
    s = state.copy()
    s.pend = None
    s.pinkq = []
    s.eot_discard = 0
    s.food_action = -1
    s.turn = player
    s.stack = [("turn", player, 1), ("act", player, habitat, 0)]
    rules.run(s)
    while s.pend is not None:
        rules.resume(s, chooser(s, s.pend))
    return s


def play_random(state, rng):
    """Finish the game in place with uniformly random choices by every player (a fast rollout)."""
    rules.play_random(state, rng)
