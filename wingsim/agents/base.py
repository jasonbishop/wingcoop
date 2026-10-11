"""Agent interface and the objective every agent maximizes."""


class Objective:
    """utility = (1 - w) x own score + w x (team total / number of players).

    w = 0 is purely selfish, w = 1 purely team-minded. `group_share` decides
    whether an equal share of the group score counts as part of a player's own
    score (it always counts in the team total).
    """

    def __init__(self, w, n_players, group_share=False):
        self.w = float(w)
        self.n = n_players
        self.group_share = bool(group_share)

    def utility(self, own, team_total, group):
        if self.group_share:
            own = own + group / self.n
        return (1.0 - self.w) * own + self.w * team_total / self.n

    def describe(self):
        if self.w == 0:
            who = "Maximize your own final score."
        elif self.w == 1:
            who = "Maximize the team total (all players' scores plus the group score)."
        else:
            who = (f"Maximize {1 - self.w:.2f} x your own final score + {self.w:.2f} x the team total "
                   f"divided by {self.n}.")
        if self.group_share:
            who += " An equal share of the group score counts as part of your own score."
        return who

    def to_dict(self):
        return {"w": self.w, "group_share": self.group_share}


class Agent:
    type = "agent"

    def start(self, config, player_index, objective):
        self.config = config
        self.player = player_index
        self.objective = objective

    def choose(self, observation, decision):
        raise NotImplementedError

    def info(self):
        """Optional reasoning data for the replay log."""
        return None

    def settings(self):
        return {}
