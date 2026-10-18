"""Group policies: they answer group decisions such as setting the co-op difficulty.

Unlike agents, a group policy may know which plugin raised the decision,
because it is answering that plugin's own question.
"""
import random as _random
import re

from ..engine import api


class GroupPolicy:
    label = ""

    def start(self, config, table=None, seed=0):
        """`table` builds fresh copies of the table's own agents (needed by `estimate`)."""
        self.config = config
        self.table = table
        self.seed = seed

    def choose(self, observation, decision):
        raise NotImplementedError

    def decide(self, state, decision):
        """The choice for a group decision; the policy sees what the whole table may see."""
        return self.choose(api.observe(state, decision.player), decision)

    def info(self):
        return None


def _nearest(options, target):
    return min(options, key=lambda o: (abs(o[1] - target), o[1]))


class Fixed(GroupPolicy):
    """fixed(d): always d (or the closest difficulty the rules allow)."""

    def __init__(self, d):
        self.d = d
        self.label = f"fixed({d})"

    def choose(self, observation, decision):
        return _nearest(decision.options, self.d)


class Ladder(GroupPolicy):
    """ladder(start, on_success, on_fail): step the difficulty after each round, within the allowed changes."""

    def __init__(self, start, on_success, on_fail):
        self.start_d, self.on_success, self.on_fail = start, on_success, on_fail
        self.label = f"ladder({start},{on_success:+d},{on_fail:+d})"

    def choose(self, observation, decision):
        s = observation.state
        d = s.variant.get("coop.d")
        if d is None or not s.goal_log:
            return _nearest(decision.options, self.start_d)
        success = s.goal_log[-1][4][2]
        return _nearest(decision.options, d + (self.on_success if success else self.on_fail))


class Estimate(GroupPolicy):
    """estimate: play the coming round with the table's own agents for each allowed difficulty,
    and pick the difficulty with the best average change in group score."""

    def __init__(self, rollouts=2):
        self.rollouts = rollouts
        self.label = "estimate" if rollouts == 2 else f"estimate({rollouts})"
        self._info = None

    def start(self, config, table=None, seed=0):
        super().start(config, table, seed)
        self.rng = _random.Random(seed * 31 + 5)

    def choose(self, observation, decision):
        if self.table is None:
            raise RuntimeError("the estimate policy needs the table's agents")
        samples = [observation.sample(self.rng) for _ in range(self.rollouts)]
        seeds = [self.rng.getrandbits(30) for _ in range(self.rollouts)]
        means = []
        for option in decision.options:
            total = 0.0
            for sim, seed in zip(samples, seeds):   # the same hidden cards and agent seeds for every option
                s = sim.copy()
                base = s.group_score
                api.apply_in_place(s, option)
                play_round(s, self.table.make_agents(seed))
                total += s.group_score - base
            means.append(total / self.rollouts)
        best = max(range(len(means)), key=lambda i: (means[i], -decision.options[i][1]))
        self._info = {"estimates": [[decision.options[i][1], round(means[i], 3)] for i in range(len(means))]}
        return decision.options[best]

    def info(self):
        return self._info


class TalkVote(GroupPolicy):
    """talk: the seats that talk (language-model agents with table talk) set the difficulty together. Each
    proposes a d in seat order, seeing the proposals before theirs in the table talk; if they all agree, that d is
    set, otherwise each proposes once more, and then the lowest proposal is set. The runner seats the voters."""

    label = "talk"

    def __init__(self):
        self.voters = []
        self._info = None

    def choose(self, observation, decision):
        raise RuntimeError("the talk policy decides from the full state (decide)")

    def decide(self, state, decision):
        if not self.voters:
            raise RuntimeError("the talk group policy needs seats that talk")
        votes, proposals = [], {}
        for rnd in (1, 2):
            for agent in self.voters:
                option = agent.choose(api.observe(state, agent.player), decision, vote=rnd)
                proposals[agent.player] = option
                info = agent.info() or {}
                votes.append({"pass": rnd, "player": agent.player, "d": option[1], "round": state.round,
                              "turn_no": state.turn_no, **info})
            if len({o[1] for o in proposals.values()}) == 1:
                break
        chosen = min(proposals.values(), key=lambda o: o[1])
        self._info = {"votes": votes, "agreed": len({o[1] for o in proposals.values()}) == 1, "d": chosen[1]}
        return chosen

    def info(self):
        return self._info


def play_round(s, agents):
    """Play the state forward in place until the current round has been scored."""
    r = s.round
    while s.pend is not None and s.round == r:
        p = s.pend[0]
        if p == api.GROUP:
            break
        d = api.pending_decision(s)
        api.apply_in_place(s, agents[p].choose(api.observe(s, p), d))


def parse(spec):
    """Build a policy from its text form: fixed(2), ladder(2,+1,0), estimate, estimate(4), talk."""
    if isinstance(spec, GroupPolicy):
        return spec
    text = str(spec).replace(" ", "")
    if text == "talk":
        return TalkVote()
    m = re.fullmatch(r"fixed\((\d)\)", text)
    if m:
        return Fixed(int(m[1]))
    m = re.fullmatch(r"ladder\((\d),([+-]?\d),([+-]?\d)\)", text)
    if m:
        return Ladder(int(m[1]), int(m[2]), int(m[3]))
    m = re.fullmatch(r"estimate(?:\((\d+)\))?", text)
    if m:
        return Estimate(int(m[1]) if m[1] else 2)
    raise ValueError(f"unknown group policy: {spec!r}")
