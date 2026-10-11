"""Play one complete game between agents."""
from .engine import api
from .engine.state import GROUP


def play_game(cfg, seed, agents, group_policy=None, log=None, tally=None, max_decisions=200000):
    """Run a game to the end and return the final state.

    `agents` is one Agent per seat. `group_policy` answers group decisions.
    `log` is an optional engine.log.GameLog; `tally` an optional object with
    record(state, decision, choice) for decision-level metrics.
    """
    s = api.new_game(cfg, seed)
    if log is not None:
        log.events(s)
        log.maybe_snapshot(s)
    for _ in range(max_decisions):
        d = api.pending_decision(s)
        if d is None:
            break
        if d.player == GROUP:
            if group_policy is None:
                raise RuntimeError(f"group decision {d.kind!r} raised but no group policy was given")
            chooser = group_policy
        else:
            chooser = agents[d.player]
        choice = chooser.choose(api.observe(s, d.player), d)
        if tally is not None:
            tally.record(s, d, choice)
        if log is not None:
            log.decision(s, d, choice, chooser.info())
        s = api.apply(s, d, choice)
        if log is not None:
            log.events(s)
            log.maybe_snapshot(s)
    else:
        raise RuntimeError("game did not finish")
    return s
