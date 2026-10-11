"""Milestone 2 checks: fuzz, invariants, determinism, replay and hidden information."""
import os
import random

import pytest

from wingsim.agents.random import RandomAgent, RandomGroupPolicy
from wingsim.engine import api, rules
from wingsim.engine.log import GameLog, ReplayMismatch, read_log, replay
from wingsim.engine.observe import HIDDEN
from wingsim.engine.state import state_hash, state_to_dict
from wingsim.game import play_game

from .conftest import random_game
from .helpers import all_cards

COOP = {"coop_goals": {}}


def check_invariants(s):
    d = s.cfg.db
    cards = all_cards(s)
    # All 180 birds are always accounted for: deck + tray + hands + boards + tucked + discard.
    assert len(cards) == 180 and sorted(cards) == sorted(d.bird_ids)
    bonus = list(s.bonus_deck) + list(s.bonus_discard)
    for f in s.stack:
        if f[0] == "bonus_keep":
            bonus.extend(f[2])
    tucked_on_birds = 0
    for pl in s.players:
        bonus.extend(pl.bonus)
        assert min(pl.food) >= 0
        for row in pl.board:
            assert len(row) <= 5
            for x in row:
                assert 0 <= x[1] <= d.birds[x[0]].egg_limit      # egg limits respected
                assert x[2] >= 0 and x[3] >= 0
                tucked_on_birds += x[3]
    assert sorted(bonus) == sorted(d.bonus_ids)
    assert tucked_on_birds == len(s.tucked)
    assert 1 <= len(s.feeder) <= 5 and all(0 <= f <= 5 for f in s.feeder)
    assert len(s.tray) <= 3
    if s.pend is not None:
        assert len(s.pend[2]) >= 2 and len(set(s.pend[2])) == len(s.pend[2])


def fuzz(n, seed, plugins=None, check_every_step=False):
    cfg = api.GameConfig(n, plugins)
    rng = random.Random(seed)
    s = api.new_game(cfg, seed)
    steps = 0
    while s.pend is not None:
        if check_every_step:
            check_invariants(s)
        rules.resume(s, s.pend[2][rng.randrange(len(s.pend[2]))])
        steps += 1
        assert steps < 20000
    assert api.is_over(s) and s.round == 5
    check_invariants(s)
    return s


@pytest.mark.parametrize("n", [2, 3, 4, 5])
def test_fuzz_with_invariants_at_every_decision(n):
    for seed in range(40):
        fuzz(n, seed, check_every_step=True)
        fuzz(n, 1000 + seed, COOP, check_every_step=True)


@pytest.mark.slow
def test_fuzz_10000_random_games():
    """The spec's fuzz check: 10,000 random-agent games across 2 to 5 players with no exceptions."""
    total = int(os.environ.get("WINGSIM_FUZZ_GAMES", "10000"))
    for i in range(total):
        fuzz(2 + i % 4, 50_000 + i, COOP if i % 8 >= 4 else None)


def test_game_length_and_turn_counts():
    for n in (2, 5):
        s = fuzz(n, 3)
        assert s.turn_no == n * 26                        # 8 + 7 + 6 + 5 turns each


def logged_game(n, seed, plugins=None):
    cfg = api.GameConfig(n, plugins, record_events=True)
    agents = [RandomAgent(seed * 7 + i) for i in range(n)]
    log = GameLog(cfg, seed, [{"type": a.type, "settings": a.settings(), "w": 0} for a in agents])
    s = play_game(cfg, seed, agents, RandomGroupPolicy(seed), log=log)
    return s, log


@pytest.mark.parametrize("n,plugins", [(2, None), (4, COOP), (5, None)])
def test_same_seed_and_choices_give_identical_log(n, plugins):
    a_state, a = logged_game(n, 21, plugins)
    b_state, b = logged_game(n, 21, plugins)
    assert a.digest() == b.digest()
    assert state_hash(a_state) == state_hash(b_state)
    c_state, c = logged_game(n, 22, plugins)
    assert a.digest() != c.digest()


@pytest.mark.parametrize("n,plugins", [(2, None), (3, COOP), (5, COOP)])
def test_replay_rebuilds_every_snapshot(tmp_path, n, plugins):
    s, log = logged_game(n, 9, plugins)
    path = log.write(tmp_path / "game.jsonl.gz")
    lines = read_log(path)
    assert lines[0]["t"] == "header" and lines[0]["seed"] == 9 and lines[0]["card_commit"] == "43e5036"
    kinds = {ln["t"] for ln in lines}
    assert kinds == {"header", "snapshot", "decision", "event"}
    snapshots = [ln for ln in lines if ln["t"] == "snapshot"]
    assert len(snapshots) == n * 26 + 1                   # the start of every turn, plus the final state
    assert snapshots[0]["state"]["deck"] and snapshots[0]["state"]["players"][0]["hand"] is not None
    final = replay(path)
    assert state_hash(final) == state_hash(s)
    assert state_to_dict(final) == snapshots[-1]["state"]


def test_replay_detects_a_changed_choice(tmp_path):
    s, log = logged_game(3, 4)
    lines = [dict(ln) for ln in log.lines]
    target = next(ln for ln in lines if ln["t"] == "decision" and ln["kind"] == "action" and ln["turn_no"] == 5)
    target["choice"] = (target["choice"] + 1) % len(target["options"])
    with pytest.raises((ReplayMismatch, api.IllegalChoice, IndexError)):
        replay(lines)


def visible_ids(obj):
    out = []
    stack = [obj]
    while stack:
        x = stack.pop()
        if isinstance(x, dict):
            stack.extend(x.values())
        elif isinstance(x, (list, tuple)):
            stack.extend(x)
        elif isinstance(x, int):
            out.append(x)
    return out


@pytest.mark.parametrize("open_hands", [True, False])
def test_observation_hides_what_the_player_may_not_see(open_hands):
    for seed in range(6):
        cfg = api.GameConfig(4, COOP, open_hands)
        rng = random.Random(seed)
        s = api.new_game(cfg, seed)
        step = 0
        while s.pend is not None:
            step += 1
            if step % 37 == 0:
                viewer = s.pend[0] if s.pend[0] != api.GROUP else 0
                o = api.observe(s, viewer).state
                assert set(o.deck) <= {HIDDEN} and set(o.tucked) <= {HIDDEN} and o.rng == 0
                assert set(o.bonus_deck) <= {HIDDEN} and set(o.bonus_discard) <= {HIDDEN}
                assert o.players[viewer].hand == s.players[viewer].hand
                for j, pl in enumerate(o.players):
                    if j != viewer:
                        if open_hands:
                            assert pl.hand == s.players[j].hand and pl.bonus == s.players[j].bonus
                        else:
                            assert set(pl.hand) <= {HIDDEN} and set(pl.bonus) <= {HIDDEN}
                # Rearranging everything hidden must not change what the viewer sees.
                t = s.copy()
                pool = list(t.deck) + list(t.tucked)
                bpool = list(t.bonus_deck) + list(t.bonus_discard)
                if not open_hands:
                    for j, pl in enumerate(t.players):
                        if j != viewer:
                            pool += pl.hand
                            bpool += pl.bonus
                rng.shuffle(pool)
                rng.shuffle(bpool)
                if not open_hands:
                    for j, pl in enumerate(t.players):
                        if j != viewer:
                            pl.hand = [pool.pop() for _ in pl.hand]
                            pl.bonus = [bpool.pop() for _ in pl.bonus]
                t.tucked = [pool.pop() for _ in t.tucked]
                t.deck = pool
                t.bonus_discard = [bpool.pop() for _ in t.bonus_discard]
                t.bonus_deck = bpool
                t.rng = 12345
                # The pending options list the decider's own cards, which the viewer (the decider) may see.
                assert state_to_dict(api.observe(t, viewer).state) == state_to_dict(o)
            rules.resume(s, s.pend[2][rng.randrange(len(s.pend[2]))])


def test_closed_hands_hide_another_players_options():
    cfg = api.GameConfig(3, None, False)
    s = api.new_game(cfg, 2)
    decider = s.pend[0]
    other = (decider + 1) % 3
    o = api.observe(s, other).state
    assert o.pend[2] is None and set(o.players[decider].hand) == {HIDDEN}
    hidden = set(s.players[decider].hand) | set(s.deck)
    assert not hidden & set(visible_ids(state_to_dict(o)["players"]))


@pytest.mark.parametrize("open_hands", [True, False])
def test_sampled_state_is_consistent_and_playable(open_hands):
    cfg = api.GameConfig(3, COOP, open_hands)
    rng = random.Random(5)
    s = api.new_game(cfg, 8)
    step = 0
    while s.pend is not None:
        step += 1
        if step % 23 == 0 and s.pend[0] != api.GROUP:
            p = s.pend[0]
            sim = api.observe(s, p).sample(rng)
            check_invariants(sim)
            assert sim.pend == s.pend and sim.players[p].hand == s.players[p].hand
            assert sim.tray == s.tray and sim.feeder == s.feeder
            for _ in range(30):                           # the sampled state can be played forward
                if sim.pend is None:
                    break
                api.apply_in_place(sim, sim.pend[2][rng.randrange(len(sim.pend[2]))])
            check_invariants(sim)
        rules.resume(s, s.pend[2][rng.randrange(len(s.pend[2]))])


def test_simulate_turn_leaves_the_real_state_alone():
    cfg, _ = random_game(2, 1)
    s = api.new_game(cfg, 4)
    while s.phase != 2:
        rules.resume(s, s.pend[2][0])
    before = state_hash(s)
    out = api.simulate_turn(s, 1, 0, lambda st, pend: pend[2][0])
    assert state_hash(s) == before
    assert sum(out.players[1].food) == sum(s.players[1].food) + 1 and out.pend is None
