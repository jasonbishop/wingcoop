import pytest

from wingsim.agents.random import RandomAgent, RandomGroupPolicy
from wingsim.engine import api
from wingsim.game import play_game


@pytest.fixture(scope="session")
def db():
    from wingsim.engine.cards import db as load
    return load()


def random_game(n, seed, plugins=None, log=None, open_hands=True, record_events=False):
    cfg = api.GameConfig(n, plugins, open_hands, record_events=record_events or log is not None)
    agents = [RandomAgent(seed * 7 + i) for i in range(n)]
    return cfg, play_game(cfg, seed, agents, RandomGroupPolicy(seed), log=log)
