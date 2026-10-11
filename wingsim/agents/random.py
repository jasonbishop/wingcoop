"""Random agent: picks uniformly among the legal options. Used to fuzz-test the engine."""
import random as _random

from .base import Agent


class RandomAgent(Agent):
    type = "random"

    def __init__(self, seed=0):
        self.seed = seed
        self.rng = _random.Random(seed)

    def choose(self, observation, decision):
        return decision.options[self.rng.randrange(len(decision.options))]

    def settings(self):
        return {"seed": self.seed}


class RandomGroupPolicy:
    def __init__(self, seed=0):
        self.rng = _random.Random(seed)

    def choose(self, observation, decision):
        return decision.options[self.rng.randrange(len(decision.options))]

    def info(self):
        return None
