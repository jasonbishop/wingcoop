import pytest


@pytest.fixture(scope="session")
def db():
    from wingsim.engine.cards import db as load
    return load()
