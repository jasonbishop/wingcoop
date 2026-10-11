"""Tree-search agent: information-set Monte Carlo tree search (single-observer ISMCTS).

Each iteration samples the hidden cards, walks down the tree with UCB1 over the
options legal in that sample, adds one node, plays the rest of the game out
with random (or greedy) moves, and scores the final state with the objective.
The agent knows nothing about cards beyond what those simulations show.

Other players are modelled as maximizing the same kind of objective as this
agent (the same motivation weight, applied to their own score), because an
agent is told only its own objective. Group decisions inside the tree are
scored by the mean of all players' utilities.
"""
import math
import random as _random
import time

from ..engine import api
from .base import Agent

# Decisions that get the full budget; the rest get `minor_iterations` when that is set.
MAJOR = frozenset({"action", "play_extra", "setup_keep_birds"})


class Node:
    __slots__ = ("n", "w", "avail", "children")

    def __init__(self):
        self.n = 0          # visits
        self.w = 0.0        # total reward for the player who chose the move leading here
        self.avail = 0      # times this move was legal when its parent was visited
        self.children = {}


class MCTSAgent(Agent):
    type = "mcts"

    def __init__(self, iterations=400, ms=None, minor_iterations=None, c=0.7, rollout="random", seed=0,
                 greedy_weights=None):
        if rollout not in ("random", "greedy"):
            raise ValueError("rollout must be 'random' or 'greedy'")
        self.iterations = iterations
        self.ms = ms                      # a time budget makes games non-reproducible
        self.minor_iterations = minor_iterations
        self.c = c
        self.rollout = rollout
        self.seed = seed
        self.greedy_weights = greedy_weights
        self._info = None

    def settings(self):
        return {"iterations": self.iterations, "ms": self.ms, "minor_iterations": self.minor_iterations,
                "c": self.c, "rollout": self.rollout, "seed": self.seed}

    def start(self, config, player_index, objective):
        super().start(config, player_index, objective)
        self.n = config.n
        self.rng = _random.Random(self.seed * 1_000_003 + player_index * 7 + 3)
        self.rollout_agents = None
        if self.rollout == "greedy":
            from .greedy import GreedyAgent
            self.rollout_agents = []
            for j in range(self.n):
                a = GreedyAgent(self.greedy_weights, self.seed + 101)
                a.start(config, j, objective)
                self.rollout_agents.append(a)

    def utilities(self, s):
        tot = api.totals(s)
        group = s.group_score
        team = group
        for x in tot:
            team += x
        u = self.objective.utility
        return [u(x, team, group) for x in tot]

    def finish(self, s):
        if self.rollout_agents is None:
            api.play_random(s, self.rng)
            return
        while s.pend is not None:
            p = s.pend[0]
            if p == api.GROUP:
                api.apply_in_place(s, self.rng.choice(s.pend[2]))
            else:
                d = api.pending_decision(s)
                api.apply_in_place(s, self.rollout_agents[p].choose(api.observe(s, p), d))

    def choose(self, observation, decision):
        rng = self.rng
        n_players = self.n
        budget = self.iterations
        if self.minor_iterations is not None and decision.kind not in MAJOR:
            budget = self.minor_iterations
        deadline = time.perf_counter() + self.ms / 1000.0 if self.ms else None
        root = Node()
        lo = hi = None
        c = self.c
        done = 0
        while True:
            if deadline is not None:
                if time.perf_counter() >= deadline and done >= len(decision.options):
                    break
            elif done >= budget:
                break
            done += 1
            s = observation.sample(rng)
            node = root
            path = []
            while True:
                pend = s.pend
                if pend is None:
                    break
                opts = pend[2]
                kids = node.children
                untried = [o for o in opts if o not in kids]
                if untried:
                    o = untried[int(rng.random() * len(untried))]
                    child = kids[o] = Node()
                    for x in opts:
                        if x in kids:
                            kids[x].avail += 1
                    path.append((child, pend[0]))
                    api.apply_in_place(s, o)
                    break
                span = (hi - lo) if hi is not None and hi > lo else 1.0
                best = None
                best_score = None
                for o in opts:
                    k = kids[o]
                    k.avail += 1
                    score = (k.w / k.n - lo) / span + c * math.sqrt(math.log(k.avail) / k.n)
                    if best_score is None or score > best_score:
                        best_score = score
                        best = o
                child = kids[best]
                path.append((child, pend[0]))
                api.apply_in_place(s, best)
                node = child
            self.finish(s)
            u = self.utilities(s)
            mean_u = sum(u) / n_players
            for x in u:
                if lo is None or x < lo:
                    lo = x
                if hi is None or x > hi:
                    hi = x
            for child, p in path:
                child.n += 1
                child.w += mean_u if p == api.GROUP else u[p]
        kids = root.children
        ranked = sorted(kids, key=lambda o: (-kids[o].n, -kids[o].w / kids[o].n))
        self._info = {"iterations": done,
                      "top": [[o, kids[o].n, round(kids[o].w / kids[o].n, 3)] for o in ranked[:3]]}
        # A legal option the search never reached (tiny budgets) cannot be the answer.
        return ranked[0]

    def info(self):
        return self._info
