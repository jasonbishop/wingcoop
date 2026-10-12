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

    def rules_text(self):
        if self.penalty == "avg_x_d":
            fail = "it falls by (average count) x d"
        elif self.penalty == "d_x_d":
            fail = "it falls by d x d"
        else:
            fail = f"it falls by {self.flat:g}"
        changes = ", ".join(f"{c:+d}" if c else "no change" for c in self.allowed_changes)
        return ("HOUSE RULE - cooperative round goals. Round goals score no individual points. Instead the "
                f"table shares a group score. Before round 1 the group sets a difficulty d from {self.lo} to "
                f"{self.hi}. At the end of each round, every player's count for the round goal is capped at 5. "
                "If EVERY player's count is at least d, the group score rises by (average count) x d; "
                f"otherwise {fail}. After each of rounds 1 to 3 the group may change d by: {changes}. "
                "The team total is the sum of all players' scores plus the group score.")

    def status_text(self, s):
        d = s.variant.get("coop.d")
        if d is None:
            return "Co-op goals: the difficulty has not been set yet. Group score 0."
        return f"Co-op goals: difficulty d = {d} this round. Group score so far: {s.group_score:g}."

    def option_label(self, s, option):
        if option[0] == "difficulty":
            return f"Set the difficulty to {option[1]}"
        return ""
