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

from . import api, describe
from .state import GROUP, TURNS, state_hash, state_to_dict

LOG_VERSION = 2
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
    """Collects log lines in memory; `write()` saves them.

    `snapshots` is "turn" (a snapshot at the start of the game, at the start of
    every turn and at the end) or "decision" (also one before every decision).
    """

    def __init__(self, cfg, seed, seats, group_policy=None, experiment=None, condition=None, snapshots="turn"):
        if snapshots not in ("turn", "decision"):
            raise ValueError("snapshots must be 'turn' or 'decision'")
        self.snapshots = snapshots
        self.lines = [{
            "t": "header", "version": LOG_VERSION, "engine_git": engine_git_hash(),
            "card_commit": cfg.db.commit, "config": cfg.resolved, "seed": seed, "seats": seats,
            "group_policy": group_policy, "experiment": experiment, "condition": condition,
            "snapshots": snapshots,
        }]
        self.seq = 0
        self.last_turn = None
        self.started = False

    def events(self, state):
        if state.events:
            for ev in state.events:
                line = {"t": "event", "seq": self.seq}
                line.update(_jsonable(ev))
                self.lines.append(line)

    def maybe_snapshot(self, state):
        """Snapshot the state as it is just before the next decision (or at the end of the game)."""
        over = api.is_over(state)
        new_turn = (not over and state.phase == TURNS and state.pend is not None and state.pend[1] == "action"
                    and state.turn_no != self.last_turn)
        if new_turn:
            self.last_turn = state.turn_no
        if not (over or new_turn or not self.started or self.snapshots == "decision"):
            return
        self.started = True
        counts = api.goal_counts(state) if state.phase == TURNS else None
        self.lines.append({"t": "snapshot", "before_seq": None if over else self.seq + 1,
                           "turn_no": state.turn_no, "round": state.round,
                           "player": None if over else state.turn, "turn_start": bool(new_turn),
                           "goal_counts": list(counts) if counts is not None else None,
                           "scores": api.scores(state),
                           "hash": state_hash(state), "state": state_to_dict(state)})

    def decision(self, state, decision, choice, info):
        self.seq += 1
        self.lines.append({
            "t": "decision", "seq": self.seq, "round": state.round, "turn_no": state.turn_no,
            "player": "group" if decision.player == GROUP else decision.player, "kind": decision.kind,
            "options": _jsonable(decision.options), "labels": describe.option_labels(state),
            "choice": decision.options.index(choice),
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
    expected = {ln["before_seq"]: ln["hash"] for ln in lines if ln["t"] == "snapshot"}
    decisions = [ln for ln in lines if ln["t"] == "decision"]
    checked = 0
    for ln in decisions:
        d = api.pending_decision(s)
        if d is None:
            raise ReplayMismatch("log has more decisions than the game")
        if ln["seq"] in expected:
            if expected[ln["seq"]] != state_hash(s):
                raise ReplayMismatch(f"snapshot before decision {ln['seq']} differs from the log")
            checked += 1
        if api_options(d.options) != ln["options"]:
            raise ReplayMismatch(f"decision {ln['seq']}: options differ from the log")
        api.apply_in_place(s, d.options[ln["choice"]])
    if not api.is_over(s):
        raise ReplayMismatch("the logged choices do not finish the game")
    if None in expected:
        if expected[None] != state_hash(s):
            raise ReplayMismatch("the final snapshot differs from the log")
        checked += 1
    if checked != len(expected):
        raise ReplayMismatch("the log has snapshots that match no decision")
    return s


def relog(path, out):
    """Write a log again with the current engine: the same game, choices and agent data, with the events and
    fields of the current format. Fails if the engine no longer plays the logged choices the same way."""
    lines = read_log(path)
    header = lines[0]
    c = header["config"]
    cfg = api.GameConfig(c["players"], c["plugins"], c["open_hands"], c["win_condition"], c.get("team_target"),
                         record_events=True)
    log = GameLog(cfg, header["seed"], header["seats"], header["group_policy"], header["experiment"],
                  header["condition"], snapshots=header["snapshots"])
    s = api.new_game(cfg, header["seed"])
    log.events(s)
    log.maybe_snapshot(s)
    for ln in (x for x in lines if x["t"] == "decision"):
        d = api.pending_decision(s)
        if d is None or api_options(d.options) != ln["options"]:
            raise ReplayMismatch(f"decision {ln['seq']}: the game no longer matches the log")
        choice = d.options[ln["choice"]]
        log.decision(s, d, choice, ln["info"])
        s = api.apply(s, d, choice)
        log.events(s)
        log.maybe_snapshot(s)
    if not api.is_over(s):
        raise ReplayMismatch("the logged choices do not finish the game")
    return log.write(out)


def api_options(options):
    return _jsonable(options)


def card_reference(db):
    """Names and printed attributes of every card, for viewers (so one file is enough to render a game)."""
    cards = json.loads((pathlib.Path(__file__).parent.parent / "data" / "cards.json").read_text())
    return {"birds": {str(b["id"]): {k: b[k] for k in ("name", "color", "vp", "nest", "egg_limit", "wingspan",
                                                         "habitats", "cost", "wild", "either", "predator",
                                                         "flocking", "text", "caches", "scientific")}
                      for b in cards["birds"]},
            "bonus": {str(b["id"]): {"name": b["name"], "condition": b["condition"], "vp_text": b["vp_text"]}
                      for b in cards["bonus"]},
            "goals": {str(g["id"]): {"text": g["text"], "kind": g["kind"], "param": g["param"]}
                      for g in cards["goals"]}}


def export(path, out):
    """Write a log as one plain JSON file: {"cards": ..., "lines": [...]}. Easier to load in a browser."""
    lines = read_log(path)
    pathlib.Path(out).write_text(json.dumps({"cards": card_reference(api.GameConfig(2).db), "lines": lines},
                                            separators=(",", ":")))
    return out


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(description="Check, export or rewrite a replay log")
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("check", help="rebuild the game from the log and verify every snapshot")
    c.add_argument("log")
    e = sub.add_parser("export", help="write the log plus card names as one plain JSON file")
    e.add_argument("log")
    e.add_argument("out")
    r = sub.add_parser("relog", help="write the log again in the current format (same game and choices)")
    r.add_argument("log")
    r.add_argument("out")
    args = ap.parse_args(argv)
    if args.cmd == "check":
        s = replay(args.log)
        print("ok:", json.dumps(api.final_scores(s)["team_total"]))
    elif args.cmd == "relog":
        print(relog(args.log, args.out))
    else:
        print(export(args.log, args.out))


if __name__ == "__main__":
    main()
