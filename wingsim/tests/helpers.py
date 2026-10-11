"""Fixture helpers: build a small, fully controlled game state and drive it with scripted choices."""
from wingsim.engine import api, rules
from wingsim.engine.cards import FACE_NAMES, FOODS, HABITATS, db
from wingsim.engine.state import SETUP

F = {name: i for i, name in enumerate(FOODS)}
H = {name: i for i, name in enumerate(HABITATS)}
FACE = {name: i for i, name in enumerate(FACE_NAMES)}


def bird(name):
    return db().by_name[name].id


def fresh(n=2, seed=1, plugins=None, open_hands=True):
    """A game just past setup with empty hands, no food, an empty tray and a sorted deck.

    Player 0 is about to choose an action. The deck is sorted by id, so draws are predictable.
    """
    cfg = api.GameConfig(n, plugins, open_hands, record_events=True)
    s = api.new_game(cfg, seed)
    while s.pend is not None and (s.phase == SETUP or s.pend[0] == api.GROUP):
        rules.resume(s, s.pend[2][0])
    for pl in s.players:
        s.deck.extend(pl.hand)
        pl.hand = []
        pl.food = [0, 0, 0, 0, 0]
    s.deck.extend(s.tray)
    s.deck.extend(s.discard)
    s.tray = []
    s.discard = []
    s.deck.sort()
    s.first = 0
    set_turn(s, 0)
    s.events = []
    return s


def set_turn(s, p):
    s.turn = p
    s.pend = None
    s.pinkq = []
    s.eot_discard = 0
    s.players[p].pink_used = ()
    s.stack = [("main",), ("turn", p, 0)]
    rules.run(s)


def _take(s, cid):
    for pile in [s.deck, s.tray, s.discard] + [pl.hand for pl in s.players]:
        if cid in pile:
            pile.remove(cid)
            return
    raise AssertionError(f"card {cid} is not available")


def put(s, p, name, habitat, eggs=0, cached=0, tucked=0):
    cid = bird(name)
    _take(s, cid)
    s.players[p].board[H[habitat]].append([cid, eggs, cached, tucked])
    for _ in range(tucked):
        s.tucked.append(s.deck.pop(0))
    return cid


def hand(s, p, *names):
    ids = [bird(n) for n in names]
    for cid in ids:
        _take(s, cid)
        s.players[p].hand.append(cid)
    return ids


def top(s, *names):
    """Put these cards on top of the deck; the first name is drawn first."""
    ids = [bird(n) for n in names]
    for cid in ids:
        _take(s, cid)
    s.deck.extend(reversed(ids))
    return ids


def tray(s, *names):
    ids = [bird(n) for n in names]
    for cid in ids:
        _take(s, cid)
        s.tray.append(cid)
    return ids


def feeder(s, *faces):
    s.feeder = [FACE[f] for f in faces]


def food(s, p, **amounts):
    for name, k in amounts.items():
        s.players[p].food[F[name]] = k


def slot(s, p, name):
    return rules.find(s.players[p], bird(name))[2]


def opts(s):
    return list(s.pend[2])


def drive(s, *script):
    """Answer pending decisions with the scripted choices, in order."""
    for choice in script:
        assert s.pend is not None, f"no decision pending for {choice!r}"
        assert choice in s.pend[2], f"{choice!r} not in {s.pend[1]} options {s.pend[2]!r}"
        rules.resume(s, choice)
    return s


def power(s, p, name, *script):
    """Run one bird's power in isolation, answering its choices from the script."""
    cid = bird(name)
    s.pend = None
    s.stack = [("steps", p, cid, db().birds[cid].steps, 0, ())]
    rules.run(s)
    drive(s, *script)
    assert s.pend is None, f"unanswered decision: {s.pend!r}"
    assert not s.stack
    return s


def turn(s, p, *script):
    """Give player p a turn and answer its decisions; the turn must be over afterwards."""
    before = s.turn_no
    set_turn(s, p)
    drive(s, *script)
    assert s.turn_no == before + 1, f"turn not finished; pending {s.pend!r}"
    return s


def all_cards(s):
    """Every bird card id currently anywhere in the game, with multiplicity."""
    out = list(s.deck) + list(s.tray) + list(s.discard) + list(s.tucked)
    for pl in s.players:
        out.extend(pl.hand)
        out.extend(x[0] for row in pl.board for x in row)
    for f in s.stack:
        if f[0] in ("draft", "draft_pick"):
            out.extend(f[2])
    return out


def pick(pred, n=1, exclude=()):
    """Names of the first n birds (by id) matching a predicate on their printed attributes."""
    d = db()
    skip = set(exclude)
    names = [d.birds[i].name for i in d.bird_ids if pred(d.birds[i]) and d.birds[i].name not in skip]
    assert len(names) >= n
    return names[:n]


def first_until(s, kind, player=None, limit=200):
    """Answer with the first option until a decision of this kind (for this player) is pending."""
    for _ in range(limit):
        if s.pend is None:
            return False
        if s.pend[1] == kind and (player is None or s.pend[0] == player):
            return True
        rules.resume(s, s.pend[2][0])
    raise AssertionError("limit reached")


def template_of(name):
    import json
    import pathlib
    from wingsim.data import build
    effects = json.loads((pathlib.Path(build.__file__).parent / "effects.json").read_text())
    return effects[str(bird(name))]["template"]
