"""Greedy agent: one-step lookahead with a generic value function.

For every legal option the agent applies it to a copy of the game (hidden cards
sampled), finishes its own follow-up choices greedily, and scores the result.
The value of a position is

    points banked
  + weighted resources (food, cards in hand, room for eggs)
  + engine value: what one use of each row produces, measured by running that
    row's action on a copy of the game, times the expected number of uses left
  + the current round goal, scored by the engine for projected end-of-round counts.

Every player's position is valued with the same function and the results are
combined by the agent's objective. Nothing here looks at a card's name, power
text or tags, or at which plugins are active: all card knowledge comes from
running the engine and from attributes printed on the card.
"""
import random as _random

from ..engine import api
from .base import Agent

# Untuned defaults: a short hill-climb on baseline 3-player self-play picked these so that the
# bot plays a sensible game. Per-condition tuning (milestone 7) replaces them.
DEFAULT_WEIGHTS = {
    "food": 0.9,          # value of the first food token held
    "food_decay": 0.85,   # each further token is worth this fraction of the previous one
    "card": 0.52,         # value of a card in hand
    "card_vp": 0.06,      # plus this much per printed point on it
    "card_decay": 0.86,   # each further card (best first) is worth this fraction of the previous one
    "room": 0.6,          # value of one free egg space that the grassland row could fill
    "rate_forest": 0.20,  # expected uses of each row per remaining turn
    "rate_grassland": 0.27,
    "rate_wetland": 0.19,
    "horizon": 5.0,       # resources lose value linearly over a player's last `horizon` turns
    "goal_rate": 0.30,    # assumed chance per remaining turn of adding 1 to a player's round-goal count
}

GOAL_SAMPLES = 8
YIELD_SAMPLES = 2
_FUTURE = (26, 18, 11, 5, 0, 0)  # turns per player after round r (index r; 0 = whole game)


def _non_skip(rng):
    def chooser(state, pend):
        opts = pend[2]
        real = [o for o in opts if o[0] != "skip"]
        return rng.choice(real) if real else opts[0]
    return chooser


class GreedyAgent(Agent):
    type = "greedy"

    def __init__(self, weights=None, seed=0, chain_budget=48):
        self.w = dict(DEFAULT_WEIGHTS)
        if weights:
            unknown = set(weights) - set(DEFAULT_WEIGHTS)
            if unknown:
                raise ValueError(f"unknown greedy weights: {sorted(unknown)}")
            self.w.update(weights)
        self.seed = seed
        self.chain_budget = chain_budget
        self._info = None

    def settings(self):
        return {"seed": self.seed, "chain_budget": self.chain_budget, "weights": dict(self.w)}

    def start(self, config, player_index, objective):
        super().start(config, player_index, objective)
        w = self.w
        self.n = config.n
        self.rng = _random.Random(self.seed * 1_000_003 + player_index)
        self.sim_rng = _random.Random(self.seed * 7919 + player_index + 17)
        self.chooser = _non_skip(self.sim_rng)
        self.birds = config.db.birds
        self.food_value = [0.0]
        for i in range(400):  # far more food than anyone can hold
            self.food_value.append(self.food_value[-1] + w["food"] * w["food_decay"] ** i)
        self.card_value = {c: w["card"] + w["card_vp"] * b.vp for c, b in self.birds.items()}
        self.card_value[api.HIDDEN] = w["card"] + w["card_vp"] * 3.5
        self.rates = (w["rate_forest"], w["rate_grassland"], w["rate_wetland"])
        self.yields = {}
        # Common random numbers for the goal projection: increments[sample][player][turns left].
        self.increments = []
        for _ in range(GOAL_SAMPLES):
            per_player = []
            for _ in range(self.n):
                run = [0]
                for _ in range(8):
                    run.append(run[-1] + (1 if self.rng.random() < w["goal_rate"] else 0))
                per_player.append(run)
            self.increments.append(per_player)
        self.goal_cache = {}

    # ------------------------------------------------------------ choosing

    def choose(self, observation, decision):
        options = decision.options
        sim = observation.sample(self.rng)
        self.goal_cache = {}
        me = self.player
        turn0 = sim.turn_no
        best = 0
        best_v = None
        values = []
        for i, o in enumerate(options):
            s = sim.copy()
            api.apply_in_place(s, o)
            v = self.settle(s, me, turn0)
            values.append(v)
            if best_v is None or v > best_v:
                best_v = v
                best = i
        order = sorted(range(len(options)), key=lambda i: -values[i])[:3]
        self._info = {"values": [[options[i], round(values[i], 3)] for i in order], "options": len(options)}
        return options[best]

    def info(self):
        return self._info

    def settle(self, s, me, turn0):
        """Finish this agent's own follow-up choices greedily, then value the position."""
        budget = self.chain_budget
        v = None
        while True:
            pend = s.pend
            if pend is None or pend[0] != me or s.turn_no != turn0:
                break
            opts = pend[2]
            if budget <= 0:
                api.apply_in_place(s, opts[0])
                v = None
                continue
            best_s = None
            v = None
            for o in opts:
                s2 = s.copy()
                api.apply_in_place(s2, o)
                v2 = self.value(s2)
                if v is None or v2 > v:
                    v = v2
                    best_s = s2
            budget -= len(opts)
            s = best_s
        return self.value(s) if v is None else v

    # ------------------------------------------------------------ valuing

    def hand_value(self, hand):
        k = len(hand)
        if k == 0:
            return 0.0
        cv = self.card_value
        if k == 1:
            return cv[hand[0]]
        vals = sorted([cv[c] for c in hand], reverse=True)
        decay = self.w["card_decay"]
        total = 0.0
        f = 1.0
        for x in vals:
            total += x * f
            f *= decay
        return total

    def basic_values(self, s):
        """Points banked plus food and cards, per player. Used to measure what a row produces."""
        tot = api.totals(s)
        fv = self.food_value
        out = []
        for j, pl in enumerate(s.players):
            f = pl.food
            out.append(tot[j] + fv[f[0] + f[1] + f[2] + f[3] + f[4]] + self.hand_value(pl.hand))
        return out

    def row_yield(self, s, j, h, room):
        """What one use of player j's row h produces for each player, by running it on a copy."""
        row = s.players[j].board[h]
        key = (j, h, tuple([x[0] for x in row]), (room if room < 4 else 4) if h == 1 else -1)
        y = self.yields.get(key)
        if y is None:
            before = self.basic_values(s)
            y = [0.0] * self.n
            for _ in range(YIELD_SAMPLES):
                after = self.basic_values(api.simulate_turn(s, j, h, self.chooser))
                for k in range(self.n):
                    y[k] += (after[k] - before[k]) / YIELD_SAMPLES
            self.yields[key] = y
        return y

    def project_goal(self, s, counts, tls):
        """Expected round-goal scoring: the engine scores sampled end-of-round counts."""
        key = (s.round, counts, tls)
        hit = self.goal_cache.get(key)
        if hit is not None:
            return hit
        n = self.n
        ind = [0.0] * n
        group = 0.0
        samples = self.increments if any(tls) else self.increments[:1]
        for inc in samples:
            c = tuple([counts[j] + inc[j][tls[j]] for j in range(n)])
            r = self.goal_cache.get(c)
            if r is None:
                r = self.goal_cache[c] = api.score_goal_counts(s, c)
            for j in range(n):
                ind[j] += r[0][j]
            group += r[1]
        k = len(samples)
        out = ([x / k for x in ind], group / k)
        self.goal_cache[key] = out
        return out

    def value(self, s):
        n = self.n
        V = api.totals(s)
        group = s.group_score
        r = s.round
        if r <= 4:
            w = self.w
            horizon = w["horizon"]
            room_w = w["room"]
            fv = self.food_value
            rates = self.rates
            birds = self.birds
            in_turns = s.phase == 2
            future = _FUTURE[r]
            per_round = (8, 7, 6, 5)[r - 1]
            tls = []
            for j in range(n):
                pl = s.players[j]
                tl = s.actions_left[j] if in_turns else per_round
                tls.append(tl)
                t = tl + future
                if t <= 0:
                    continue
                f = pl.food
                res = fv[f[0] + f[1] + f[2] + f[3] + f[4]] + self.hand_value(pl.hand)
                V[j] += res * (t / horizon if t < horizon else 1.0)
                room = 0
                for row in pl.board:
                    for x in row:
                        room += birds[x[0]].egg_limit - x[1]
                for h in (0, 1, 2):
                    y = self.row_yield(s, j, h, room)
                    c = rates[h] * t
                    for k in range(n):
                        if y[k]:
                            gain = c * y[k]
                            if h == 1 and k == j and gain > room_w * room:
                                gain = room_w * room   # eggs to come cannot exceed the room for them
                            V[k] += gain
            counts = api.goal_counts(s)
            ind, gdelta = self.project_goal(s, counts, tuple(tls))
            for j in range(n):
                V[j] += ind[j]
            group += gdelta
        team = group
        for x in V:
            team += x
        return self.objective.utility(V[self.player], team, group)
