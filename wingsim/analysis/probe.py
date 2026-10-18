"""Ask a language model one logged decision again, as many times as wanted, with changed settings.

The game is replayed from its full log up to the chosen decision, so the position is exact. The language-model
seat is rebuilt with the logged settings, any of which can be changed (model, endpoint, reasoning, hidden
thinking, plan, outcomes, goal status, table talk, temperature), and is given the plan it held at that point (or
none) and the table talk said before it. With the logged settings the rebuilt prompt should match the logged one;
the script says whether it does.

Each reply is saved to a JSON-lines file (prompt, replies, hidden thinking when the server returns it, the
choice, the plan written, tokens and cost) and a tally of the choices is printed.

Replays default to temperature 0.7, so that repeated asks can differ; --temperature 0 asks as the game did
(a local server then gives the same reply every time).

Usage:
  # what the prompt looks like with full reasoning, without calling anything
  python -m wingsim.analysis.probe logs/llm-prompts-moe/coop_plan_after/103-2p-w1.0-fixed_2.jsonl.gz --turn 19 --reasoning full --show-prompt
  # 10 replays on the local Qwen with full reasoning
  python -m wingsim.analysis.probe <log> --turn 19 --reasoning full -n 10
  # the same on OpenRouter, with hidden thinking, no plan, and a spending cap
  python -m wingsim.analysis.probe <log> --turn 19 --model z-ai/glm-5.3 --reasoning full --thinking medium --plan off -n 10 --budget-usd 3
"""
import argparse
import collections
import json
import pathlib
import re
import time

from ..agents import llm
from ..agents.base import Objective
from ..agents.talk import TableTalk
from ..engine import api
from ..engine.log import api_options, read_log

OPENROUTER = "https://openrouter.ai/api/v1"


def position(lines, seq=None, turn=None, player=None):
    """Replay a log up to one decision: (config, state, decision, its log line)."""
    header = lines[0]
    if player is None:
        player = next(i for i, s in enumerate(header["seats"]) if s.get("type") == "llm")
    decisions = [ln for ln in lines if ln["t"] == "decision"]
    if seq is not None:
        target = next((ln for ln in decisions if ln["seq"] == seq), None)
    else:
        target = next((ln for ln in decisions if ln["turn_no"] == turn and ln["player"] == player
                       and ln["kind"] == "action"), None)
    if target is None:
        raise SystemExit(f"no such decision in the log (seq {seq}, turn {turn}, player {player})")
    c = header["config"]
    cfg = api.GameConfig(c["players"], c["plugins"], c["open_hands"], c["win_condition"], c.get("team_target"))
    s = api.new_game(cfg, header["seed"])
    for ln in decisions:
        d = api.pending_decision(s)
        if api_options(d.options) != ln["options"]:
            raise SystemExit(f"decision {ln['seq']}: the engine no longer plays this log the same way")
        if ln is target:
            return cfg, s, d, target
        api.apply_in_place(s, d.options[ln["choice"]])
    raise SystemExit("the log ended before the decision")


def turn_notes(lines, target):
    """What the seat had chosen earlier in the same turn, as LLMAgent keeps it (shown at non-action decisions;
    kept only on the seat's own turns, and not during setup)."""
    owner = {ln["turn_no"]: ln["player"] for ln in lines if ln["t"] == "decision" and ln["kind"] == "action"}
    if owner.get(target["turn_no"]) != target["player"]:
        return (None, [])
    notes = []
    for ln in lines:
        if ln is target:
            break
        if (ln["t"] == "decision" and not ln["kind"].startswith("setup_")
                and ln["player"] == target["player"] and ln["turn_no"] == target["turn_no"]
                and ln.get("info") and ln["info"].get("replies")):
            why = None
            if ln["kind"] == "action":
                why = llm.strip_reply(ln["info"]["replies"][-1])
                why = re.sub(r"ANSWER\s*[:=].*", "", why, flags=re.S | re.IGNORECASE).strip()[:llm.NOTE_LIMIT] or None
            notes.append((ln["labels"][ln["choice"]], why))
    return (target["turn_no"], notes) if notes else (None, [])


def posts(ln):
    """The table-talk messages a logged decision added: [(round, turn number, player, text)]. A group
    decision under the talk policy holds the proposals of the difficulty, each posted with its message."""
    info = (ln.get("info") or {}) if ln["t"] == "decision" else {}
    if info.get("votes"):
        return [(v["round"], v["turn_no"], v["player"], v["posted"]) for v in info["votes"] if v.get("posted")]
    return [(ln["round"], ln["turn_no"], ln["player"], info["said"])] if info.get("said") else []


def table_talk(lines, target):
    """The table talk as it stood at the decision: who talks, and what was said before it."""
    members = [i for i, s in enumerate(lines[0]["seats"]) if (s.get("settings") or {}).get("talk")]
    table = TableTalk(members)
    for ln in lines:
        if ln is target:
            break
        for message in posts(ln):
            table.post(*message)
    return table


def harness_state(lines, target):
    """The coach and digest state the seat held just before the decision, rebuilt from its earlier decisions:
    {"my_actions", "coach_notes", "last_coach", "to_coach", "talk_notes", "talk_seen", "posted"}."""
    p = target["player"]
    state = {"my_actions": [], "coach_notes": (None, None), "last_coach": None, "to_coach": None, "talk_notes": None,
             "talk_seen": 0}
    posted = 0
    for ln in lines:
        if ln is target:
            break
        if ln["t"] != "decision":
            continue
        info = ln.get("info") or {}
        if ln["player"] == p and ln["kind"] == "action":
            apply_aux(state, ln, info, posted)
            state["my_actions"].append((ln["round"], ln["turn_no"], ln["labels"][ln["choice"]]))
            if "to_coach" in info:
                state["to_coach"] = (ln["round"], ln["turn_no"], info["to_coach"]) if info["to_coach"] else None
        posted += len(posts(ln))
    state["posted"] = posted
    return state


def apply_aux(state, ln, info, posted):
    """What a logged action decision's extra calls left behind (coach notes, talk notes, messages read)."""
    for c in info.get("aux") or []:
        if c["role"] == "digest":
            state["talk_seen"] = posted
            if c["notes"]:
                state["talk_notes"] = (ln["round"], ln["turn_no"], c["notes"])
        elif c["role"] == "coach":
            state["coach_notes"] = (ln["turn_no"], c["notes"])
            state["last_coach"] = (ln["round"], ln["turn_no"], c["notes"])


def set_harness(agent, state):
    agent.my_actions = list(state["my_actions"])
    agent.coach_notes = state["coach_notes"]
    agent.talk_notes = state["talk_notes"]
    agent.talk_seen = state["talk_seen"]
    agent.last_coach = state["last_coach"]
    agent.to_coach = state["to_coach"]


def build_agent(header, player, args):
    """The language-model seat with the logged settings, changed where the arguments say."""
    logged = dict(header["seats"][player]["settings"])
    model = args.model or logged["model"]
    base_url = args.base_url or (logged["base_url"] if not args.model else OPENROUTER)
    reasoning = {"logged": logged["reasoning"], "off": False, "brief": True, "full": "full"}[args.reasoning]
    thinking = logged.get("thinking") if args.thinking == "logged" else (None if args.thinking == "off" else args.thinking)
    plan = logged.get("plan", False) if args.plan == "logged" else args.plan != "off"
    extra = json.loads(args.extra_body) if args.extra_body else None
    if extra is None and "openrouter.ai" not in base_url:
        # Local Qwen servers: hidden thinking is a chat-template switch (the log does not record extra_body).
        extra = {"chat_template_kwargs": {"enable_thinking": bool(thinking)}}
    opts = dict(model=model, base_url=base_url, prompt=logged.get("prompt", "default"), reasoning=reasoning,
                thinking=thinking, plan=plan, extra_body=extra, timeout=args.timeout, budget_usd=args.budget_usd,
                outcomes=logged.get("outcomes", False) if args.outcomes is None else args.outcomes,
                compact=logged.get("compact", False),
                goal_status=logged.get("goal_status", False) if args.goal_status is None else args.goal_status,
                talk=logged.get("talk", False) if args.talk is None else args.talk,
                coach=logged.get("coach", False) if args.coach is None else args.coach,
                digest=logged.get("digest", False) if args.digest is None else args.digest,
                reply_format=logged.get("reply_format", "lines"), temperature=args.temperature)
    default = llm.LLMAgent(**opts).max_tokens
    if args.max_tokens:
        opts["max_tokens"] = args.max_tokens
    elif (reasoning, thinking) == (logged["reasoning"], logged.get("thinking")):
        opts["max_tokens"] = max(default, logged.get("max_tokens") or 0)
    else:       # the logged limit, raised for hidden thinking when that is newly on
        opts["max_tokens"] = max(default, (logged.get("max_tokens") or 0) + (4000 if thinking and not logged.get("thinking") else 0))
    return llm.LLMAgent(**opts), opts


def main():
    ap = argparse.ArgumentParser(description="Ask a language model one logged decision again, with changed settings")
    ap.add_argument("log", help="a full game log (.jsonl.gz)")
    where = ap.add_mutually_exclusive_group(required=True)
    where.add_argument("--seq", type=int, help="the decision's seq number in the log")
    where.add_argument("--turn", type=int, help="the language-model seat's action decision on this turn number")
    ap.add_argument("--player", type=int, help="the seat to ask (default: the first language-model seat)")
    ap.add_argument("-n", type=int, default=1, help="how many times to ask (default 1)")
    ap.add_argument("--model", help="model id (default: the logged one); a new model goes to OpenRouter unless --base-url")
    ap.add_argument("--base-url", help="endpoint (default: the logged one, or OpenRouter for a new --model)")
    ap.add_argument("--reasoning", choices=["logged", "off", "brief", "full"], default="logged")
    ap.add_argument("--thinking", choices=["logged", "off", "low", "medium", "high"], default="logged",
                    help="hidden model-side thinking")
    ap.add_argument("--plan", choices=["logged", "on", "off", "empty"], default="logged",
                    help="logged/on: the plan feature with the plan the seat held then; empty: the feature with no "
                         "plan yet; off: no plan feature")
    ap.add_argument("--outcomes", action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument("--goal-status", action=argparse.BooleanOptionalAction, default=None)
    ap.add_argument("--talk", action=argparse.BooleanOptionalAction, default=None,
                    help="table talk (default: as logged); the messages said before the decision are shown")
    ap.add_argument("--coach", action=argparse.BooleanOptionalAction, default=None,
                    help="a coach call before the action (default: as logged)")
    ap.add_argument("--digest", action=argparse.BooleanOptionalAction, default=None,
                    help="a table-talk digest call before the action, when others said something new")
    ap.add_argument("--temperature", type=float, default=0.7)
    ap.add_argument("--max-tokens", type=int)
    ap.add_argument("--extra-body", help="extra request fields as JSON (default for a local server: "
                                         "the Qwen enable_thinking switch, on when --thinking is)")
    ap.add_argument("--timeout", type=float, default=900)
    ap.add_argument("--budget-usd", type=float, help="stop once this much has been spent")
    ap.add_argument("--show-prompt", action="store_true", help="print the system and user prompt and stop")
    ap.add_argument("--label", help="a name for this variant, used in the output file name")
    ap.add_argument("--out", help="output file (default results/probes/<game>-seq<N>-<label>.jsonl)")
    args = ap.parse_args()

    lines = read_log(args.log)
    header = lines[0]
    cfg, s, d, target = position(lines, args.seq, args.turn, args.player)
    player = target["player"]
    agent, opts = build_agent(header, player, args)
    seat = header["seats"][player]
    agent.start(cfg, player, Objective(seat.get("w", 0.0), cfg.n, seat.get("group_share", False)))
    if seat["settings"].get("votes") and agent.talk:
        agent.join_vote()
    logged_info = target.get("info") or {}
    if agent.plan:
        agent.current_plan = None if args.plan == "empty" else logged_info.get("plan")
        agent.turn_notes = turn_notes(lines, target)
    if agent.talk:
        agent.table = table_talk(lines, target)
        if player not in agent.table.members:     # talk switched on for a seat that did not talk
            agent.table.members = sorted(agent.table.members + [player])
    before = harness_state(lines, target)
    set_harness(agent, before)
    if d.kind == "action":      # the prompt as logged also holds this decision's own coach and talk notes
        shown_state = dict(before, my_actions=list(before["my_actions"]))
        apply_aux(shown_state, target, logged_info, before["posted"])
        set_harness(agent, shown_state)
    obs = api.observe(s, player)
    user = agent.build_prompt(obs, d)[0]
    same = user == logged_info.get("prompt")
    print(f"{args.log} seq {target['seq']}: round {target['round']}, turn {target['turn_no']}, player {player}, "
          f"{target['kind']}; logged choice: {target['labels'][target['choice']]}")
    shown = {k: opts[k] for k in ("model", "base_url", "reasoning", "thinking", "plan", "outcomes", "goal_status",
                                  "talk", "coach", "digest", "temperature", "max_tokens")}
    print("settings:", shown)
    print("rebuilt prompt", "matches the logged one" if same else "differs from the logged one (settings changed)")
    if args.show_prompt:
        print("\n===== SYSTEM\n" + agent.system + "\n\n===== USER\n" + user)
        return

    label = args.label or "-".join(f"{k}={v}" for k, v in (("model", agent.model.split("/")[-1]),
                                                             ("reasoning", args.reasoning), ("thinking", args.thinking),
                                                             ("plan", args.plan)))
    out = pathlib.Path(args.out or f"results/probes/{pathlib.Path(args.log).name.split('.')[0]}"
                                   f"-{pathlib.Path(args.log).parent.name}-seq{target['seq']}-{label}.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)
    tally = collections.Counter()
    said_before = len(agent.table.messages) if agent.talk else 0
    with open(out, "a") as f:
        f.write(json.dumps({"t": "probe", "log": args.log, "seq": target["seq"], "settings": shown,
                            "logged_choice": target["choice"] + 1, "prompt": user, "system": agent.system}) + "\n")
        for i in range(args.n):
            start_stats = dict(agent.stats)
            if agent.plan:
                agent.current_plan = None if args.plan == "empty" else logged_info.get("plan")
            if agent.talk:      # each ask sees the table as it was, not the earlier asks' messages
                agent.table.messages = agent.table.messages[:said_before]
            set_harness(agent, before)     # and makes its own coach and digest calls
            t0 = time.time()
            try:
                choice = agent.choose(obs, d)
            except llm.BudgetExceeded as e:
                print(e)
                break
            info = agent.info()
            k = info["chosen"]
            name = target["labels"][k - 1] + (" (random fallback)" if info["fallback"] else "")
            tally[name] += 1
            spent = {key: agent.stats[key] - start_stats[key] for key in ("prompt_tokens", "completion_tokens", "cost_usd")}
            f.write(json.dumps({"t": "reply", "i": i + 1, "chosen": k, "label": name, "seconds": time.time() - t0,
                                **{key: info.get(key) for key in ("replies", "thinking", "plan_updated", "said",
                                                                   "aux", "usage_all", "fallback")}, **spent}) + "\n")
            f.flush()
            print(f"  {i + 1}/{args.n}: {k}. {name[:80]}  ({spent['completion_tokens']} tokens out, "
                  f"${spent['cost_usd']:.4f}, {time.time() - t0:.0f}s)", flush=True)
    st = agent.stats
    print(f"\n{sum(tally.values())} replies, {st['calls']} calls, {st['prompt_tokens']:,} tokens in, "
          f"{st['completion_tokens']:,} out, ${st['cost_usd']:.4f}")
    for name, c in tally.most_common():
        print(f"  {c:3}  {name}")
    print("replies saved to", out)


if __name__ == "__main__":
    main()
