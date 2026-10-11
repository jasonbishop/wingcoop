"""Replay logs: one gzipped JSON Lines file per fully logged game.

Line types: one "header", then "snapshot" (complete state at the start of every
turn, hidden information included), "decision" and "event" lines. `replay()`
rebuilds the game from the seed and the logged choices and checks every
snapshot hash.
"""
import gzip
import json
import pathlib
import subprocess

from . import api
from .state import GROUP, TURNS, state_hash, state_to_dict

LOG_VERSION = 1
_GIT = None


def engine_git_hash():
    global _GIT
    if _GIT is None:
        root = pathlib.Path(__file__).resolve().parent.parent.parent
        try:
            head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=root, capture_output=True, text=True,
                                  timeout=10).stdout.strip() or "uncommitted"
            dirty = subprocess.run(["git", "status", "--porcelain", "--", "wingsim"], cwd=root,
                                   capture_output=True, text=True, timeout=10).stdout.strip()
            _GIT = head + ("+dirty" if dirty else "")
        except OSError:
            _GIT = "unknown"
    return _GIT


def _jsonable(x):
    if isinstance(x, (tuple, list)):
        return [_jsonable(v) for v in x]
    if isinstance(x, dict):
        return {str(k): _jsonable(v) for k, v in x.items()}
    return x


class GameLog:
    """Collects log lines in memory; `write()` saves them."""

    def __init__(self, cfg, seed, seats, group_policy=None, experiment=None, condition=None):
        self.lines = [{
            "t": "header", "version": LOG_VERSION, "engine_git": engine_git_hash(),
            "card_commit": cfg.db.commit, "config": cfg.resolved, "seed": seed, "seats": seats,
            "group_policy": group_policy, "experiment": experiment, "condition": condition,
        }]
        self.seq = 0
        self.last_turn = None

    def events(self, state):
        if state.events:
            for ev in state.events:
                line = {"t": "event", "seq": self.seq}
                line.update(_jsonable(ev))
                self.lines.append(line)

    def maybe_snapshot(self, state):
        """Snapshot at the first decision of each turn, and once the game is over."""
        over = api.is_over(state)
        if over:
            key = "end"
        elif state.phase == TURNS and state.pend is not None and state.pend[1] == "action":
            key = state.turn_no
        else:
            return
        if key == self.last_turn:
            return
        self.last_turn = key
        self.lines.append({"t": "snapshot", "turn_no": state.turn_no, "round": state.round,
                           "player": None if over else state.turn, "hash": state_hash(state),
                           "state": state_to_dict(state)})

    def decision(self, state, decision, choice, info):
        self.seq += 1
        self.lines.append({
            "t": "decision", "seq": self.seq, "round": state.round, "turn_no": state.turn_no,
            "player": "group" if decision.player == GROUP else decision.player, "kind": decision.kind,
            "options": _jsonable(decision.options), "choice": decision.options.index(choice),
            "info": _jsonable(info) if info else None,
        })

    def write(self, path):
        path = pathlib.Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as f:
            for line in self.lines:
                f.write(json.dumps(line, separators=(",", ":")) + "\n")
        return path

    def digest(self):
        import hashlib
        h = hashlib.sha1()
        for line in self.lines[1:]:
            h.update(json.dumps(line, sort_keys=True).encode())
        return h.hexdigest()


def read_log(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return [json.loads(line) for line in f]


class ReplayMismatch(AssertionError):
    pass


def replay(path_or_lines):
    """Rebuild a game from its log and check every snapshot. Returns the final state."""
    lines = read_log(path_or_lines) if not isinstance(path_or_lines, list) else path_or_lines
    header = lines[0]
    c = header["config"]
    cfg = api.GameConfig(c["players"], c["plugins"], c["open_hands"], c["win_condition"], c.get("team_target"))
    s = api.new_game(cfg, header["seed"])
    snapshots = [ln for ln in lines if ln["t"] == "snapshot"]
    decisions = [ln for ln in lines if ln["t"] == "decision"]
    si = 0
    last = None

    def check():
        nonlocal si, last
        over = api.is_over(s)
        if over:
            key = "end"
        elif s.phase == TURNS and s.pend is not None and s.pend[1] == "action":
            key = s.turn_no
        else:
            return
        if key == last:
            return
        last = key
        if si >= len(snapshots):
            raise ReplayMismatch(f"no logged snapshot for turn {key}")
        if snapshots[si]["hash"] != state_hash(s):
            raise ReplayMismatch(f"snapshot {si} (turn {key}) differs from the log")
        si += 1

    check()
    for ln in decisions:
        d = api.pending_decision(s)
        if d is None:
            raise ReplayMismatch("log has more decisions than the game")
        if api_options(d.options) != ln["options"]:
            raise ReplayMismatch(f"decision {ln['seq']}: options differ from the log")
        api.apply_in_place(s, d.options[ln["choice"]])
        check()
    if not api.is_over(s):
        raise ReplayMismatch("the logged choices do not finish the game")
    if si != len(snapshots):
        raise ReplayMismatch("log has more snapshots than the game")
    return s


def api_options(options):
    return _jsonable(options)
