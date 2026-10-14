"""Game state: plain data that copies cheaply.

All randomness comes from `State.rng`, a single integer advanced by the
splitmix64 functions below, so a game is fully determined by its seed and the
list of choices made.
"""
import json

GROUP = -1  # the "player" that owns group decisions

SETUP, PRE_ROUND, TURNS, ROUND_END, OVER = range(5)
PHASE_NAMES = ("setup", "pre_round", "turns", "round_end", "over")

_M = (1 << 64) - 1


def rng_next(s):
    s.rng = z = (s.rng + 0x9E3779B97F4A7C15) & _M
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M
    return z ^ (z >> 31)


def rand_below(s, n):
    return rng_next(s) % n


def shuffle(s, items):
    for i in range(len(items) - 1, 0, -1):
        j = rng_next(s) % (i + 1)
        items[i], items[j] = items[j], items[i]


class Player:
    """One player's mat. A board slot is the list [card id, eggs, cached food, tucked cards]."""
    __slots__ = ("board", "hand", "bonus", "food", "pink_used")

    def __init__(self):
        self.board = [[], [], []]
        self.hand = []
        self.bonus = []
        self.food = [0, 0, 0, 0, 0]
        self.pink_used = ()

    def copy(self):
        p = Player.__new__(Player)
        b = self.board
        p.board = [[x[:] for x in b[0]], [x[:] for x in b[1]], [x[:] for x in b[2]]]
        p.hand = self.hand[:]
        p.bonus = self.bonus[:]
        p.food = self.food[:]
        p.pink_used = self.pink_used
        return p


class State:
    __slots__ = (
        "cfg", "rng", "phase", "round", "first", "turn", "turn_no", "setup_idx", "actions_left",
        "deck", "discard", "tray", "feeder", "bonus_deck", "bonus_discard", "tucked",
        "goals", "goal_points", "group_score", "goal_log", "players", "variant",
        "stack", "pend", "did", "memo", "last_food", "pinkq", "eot_discard", "food_action", "rodent",
        "events",
    )

    def copy(self, events=False):
        s = State.__new__(State)
        s.cfg = self.cfg
        s.rng = self.rng
        s.phase = self.phase
        s.round = self.round
        s.first = self.first
        s.turn = self.turn
        s.turn_no = self.turn_no
        s.setup_idx = self.setup_idx
        s.actions_left = self.actions_left[:]
        s.deck = self.deck[:]
        s.discard = self.discard[:]
        s.tray = self.tray[:]
        s.feeder = self.feeder[:]
        s.bonus_deck = self.bonus_deck[:]
        s.bonus_discard = self.bonus_discard[:]
        s.tucked = self.tucked[:]
        s.goals = self.goals
        s.goal_points = self.goal_points[:]
        s.group_score = self.group_score
        s.goal_log = self.goal_log
        s.players = [p.copy() for p in self.players]
        s.variant = dict(self.variant)
        s.stack = self.stack[:]
        s.pend = self.pend
        s.did = self.did
        s.memo = self.memo
        s.last_food = self.last_food
        s.pinkq = self.pinkq[:]
        s.eot_discard = self.eot_discard
        s.food_action = self.food_action
        s.rodent = self.rodent
        s.events = [] if (events and self.events is not None) else None
        return s

    @property
    def n(self):
        return len(self.players)


def _plain(x):
    if isinstance(x, (tuple, list)):
        return [_plain(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _plain(v) for k, v in x.items()}
    return x


def state_to_dict(s):
    """Complete state, hidden information included, as JSON-ready data."""
    return {
        "rng": s.rng, "phase": PHASE_NAMES[s.phase], "round": s.round, "first": s.first, "turn": s.turn,
        "turn_no": s.turn_no, "actions_left": list(s.actions_left),
        "deck": list(s.deck), "discard": list(s.discard), "tray": list(s.tray), "feeder": list(s.feeder),
        "bonus_deck": list(s.bonus_deck), "bonus_discard": list(s.bonus_discard), "tucked": list(s.tucked),
        "goals": list(s.goals), "goal_points": list(s.goal_points), "group_score": s.group_score,
        "goal_log": _plain(s.goal_log),
        "players": [
            {"board": [[{"bird": x[0], "eggs": x[1], "cached": x[2], "tucked": x[3]} for x in row]
                       for row in p.board],
             "hand": list(p.hand), "bonus": list(p.bonus), "food": list(p.food),
             "pink_used": list(p.pink_used)}
            for p in s.players
        ],
        "variant": _plain(s.variant),
        "set_aside": set_aside(s),
        "stack": [_frame_plain(f) for f in s.stack],
        "pending": _plain(s.pend),
        "registers": [s.did, s.memo, s.last_food, _plain(s.pinkq), s.eot_discard, s.food_action, s.rodent,
                      s.setup_idx],
    }


def set_aside(s):
    """Cards out of every pile while a choice about them is pending: the bonus cards a power drew, and the
    birds taken for the American Oystercatcher draft. They live only in stack frames."""
    birds, bonus = [], []
    for f in s.stack:
        if f[0] in ("draft", "draft_pick"):
            birds.extend(f[2])
        elif f[0] == "bonus_keep":
            bonus.extend(f[2])
    return {"birds": birds, "bonus": bonus}


def _frame_plain(f):
    # "steps" frames hold a reference to a card's compiled steps; log their length only.
    if f[0] in ("steps", "then"):
        return [f[0], f[1], f[2], len(f[3])] + [_plain(v) for v in f[4:]]
    return _plain(f)


def state_hash(s):
    import hashlib
    d = state_to_dict(s)
    del d["set_aside"]  # derived from the stack, which the hash already covers; leaving it out keeps old logs valid
    return hashlib.sha1(json.dumps(d, sort_keys=True).encode()).hexdigest()
