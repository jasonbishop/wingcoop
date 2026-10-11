"""Plugin 1: cooperative round goals.

Replaces normal goal scoring. Each player's count for the round goal is capped
at 5 (the blue side's maximum). If every player reaches the difficulty d, the
group score rises by mean(count) x d; otherwise it falls by the penalty. The
group sets d after setup and may change it after rounds 1 to 3.
"""
from . import Plugin
from ..engine import rules


class CoopGoals(Plugin):
    name = "coop_goals"

    def __init__(self, penalty="avg_x_d", allowed_changes=(0, 1), difficulty_range=(1, 5)):
        super().__init__(penalty=penalty, allowed_changes=list(allowed_changes),
                         difficulty_range=list(difficulty_range))
        self.penalty = penalty
        if penalty.startswith("flat:"):
            self.flat = float(penalty.split(":", 1)[1])
        elif penalty not in ("avg_x_d", "d_x_d"):
            raise ValueError(f"unknown penalty: {penalty}")
        self.allowed_changes = tuple(sorted(allowed_changes))
        lo, hi = difficulty_range
        if not 1 <= lo <= hi <= 5:
            raise ValueError("difficulty_range must lie within 1 to 5")
        self.lo, self.hi = lo, hi

    def on_setup(self, s):
        s.variant["coop.d"] = None

    def before_round(self, s, r):
        d = s.variant["coop.d"]
        if d is None:
            options = range(self.lo, self.hi + 1)
        else:
            options = [d + c for c in self.allowed_changes if self.lo <= d + c <= self.hi] or [d]
        rules.push_group_decision(s, self, "set_difficulty", [("difficulty", x) for x in options])

    def on_group_choice(self, s, kind, choice):
        s.variant["coop.d"] = choice[1]

    def round_end_scoring(self, s, counts):
        d = s.variant.get("coop.d")
        n = len(counts)
        if d is None:   # asked before the group has set a difficulty (during setup)
            return [0.0] * n, 0.0, ("coop", None, None)
        capped = [c if c < 5 else 5 for c in counts]
        mean = sum(capped) / n
        success = min(capped) >= d
        if success:
            delta = mean * d
        elif self.penalty == "avg_x_d":
            delta = -mean * d
        elif self.penalty == "d_x_d":
            delta = -float(d * d)
        else:
            delta = -self.flat
        return [0.0] * n, delta, ("coop", d, success)
