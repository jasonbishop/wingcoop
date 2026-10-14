"""Language-model agent (optional, for spot checks).

Calls any OpenAI-compatible chat endpoint (OpenRouter, Ollama, LM Studio,
vLLM). The prompt holds a rules summary, the objective in plain words, the
observation as text and a numbered list of legal options; the reply is parsed
as an option number. If it cannot be parsed the agent asks once more, then
picks at random and records that it did. Every prompt and reply is kept for
the replay log.

All text about cards comes from the engine (api.describe_observation,
api.describe_decision and the other describe_* functions); this module only
assembles and sends it.

Optional prompt features, each a setting so that variants can be compared:
- `plan`: the model keeps a short plan. At each "which action" decision it checks
  the plan against the position, answers, and writes an updated plan, which is
  shown with every later prompt. Within its own turn it is also reminded what it
  chose so far and why.
- `outcomes`: each option of an action decision carries a line saying what it
  changes right away (worked out by the engine from what the player can see).
- `compact`: food payments are labelled by the part that differs, and the
  starting birds are chosen by naming them instead of from 32 combinations.
"""
import json
import os
import pathlib
import random as _random
import re
import time
import urllib.error
import urllib.request

from .. import prompts
from ..engine import api
from .base import Agent

ANSWER_ONLY = "Reply with only the number of the option you choose. No other text."
ANSWER_REASONED = ("Think briefly (three sentences at most) about which option best serves your objective, "
                   "then finish with a line of the form 'ANSWER: <number>'.")
PLAN_FORM = "PLAN:\nEngine: ...\nBonus target: ...\nRound goal: ...\nNeed next: ...\nPivot if: ...\nEND PLAN"
PLAN_ASK = ("First check your plan against the position above: does it still hold given what has changed? Keep it, "
            "adjust it or drop it, and say why in one or two sentences. Then give your choice on a line of the form "
            "'ANSWER: <number>'. Then write your updated plan, short, in exactly this form:\n" + PLAN_FORM)
PLAN_LIMIT = 700          # characters kept from a plan
NOTE_LIMIT = 400          # characters kept from the reasoning behind this turn's action
KEEP_ASK = ("Reply with your reasoning in three sentences at most, then a line of the form 'ANSWER: <numbers>' "
            "listing the birds you keep, separated by commas (for example 'ANSWER: 1, 4'), or 'ANSWER: none'.")

# Spending is tracked per process, across every language-model seat in it.
SPEND = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cost_usd": 0.0}


class BudgetExceeded(RuntimeError):
    pass


def load_env(path=".env"):
    """Read KEY=VALUE lines (spaces around '=' allowed) into the environment, without overriding it."""
    p = pathlib.Path(path)
    if not p.exists():
        return
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def strip_reply(reply):
    """The reply without hidden-reasoning tags (<think>...</think>) or a plan block."""
    reply = re.sub(r"<think>.*?(</think>|$)", "", reply or "", flags=re.S)
    return re.sub(r"PLAN:.*?(END PLAN|$)", "", reply, flags=re.S | re.IGNORECASE)


def parse_plan(reply):
    """The plan block of a reply (between 'PLAN:' and 'END PLAN'), or None."""
    reply = re.sub(r"<think>.*?(</think>|$)", "", reply or "", flags=re.S)
    m = re.search(r"PLAN:\s*(.*?)\s*(END PLAN|$)", reply, flags=re.S | re.IGNORECASE)
    if not m or not m.group(1).strip():
        return None
    return m.group(1).strip()[:PLAN_LIMIT]


def parse_numbers(reply, n):
    """The option numbers listed after the last 'ANSWER:' ([] for 'none'), or None if there is no valid list."""
    m = re.findall(r"ANSWER\s*[:=]?\s*\**\s*([^\n]*)", strip_reply(reply), flags=re.IGNORECASE)
    if not m:
        return None
    text = m[-1]
    if re.search(r"\bnone\b", text, flags=re.IGNORECASE):
        return []
    nums = [int(x) for x in re.findall(r"\d+", text)]
    if not nums or any(not 1 <= k <= n for k in nums):
        return None
    return sorted(set(nums))


def parse_choice(reply, n, strict=False):
    """The option number (1-based) named in a reply, or None. Without an 'ANSWER:' line the last number in
    the reply is taken, unless `strict` (for replies that reason first, where that number could be anything)."""
    reply = strip_reply(reply)
    if not reply:
        return None
    m = re.findall(r"ANSWER\s*[:=]?\s*\**\s*(\d+)", reply, flags=re.IGNORECASE)
    numbers = m if (m or strict) else re.findall(r"\d+", reply)
    if not numbers:
        return None
    k = int(numbers[-1])
    return k if 1 <= k <= n else None


class LLMAgent(Agent):
    type = "llm"

    def __init__(self, model, base_url="https://openrouter.ai/api/v1", api_key_env=None,
                 prompt="default", reasoning=False, thinking=None, temperature=0.0, max_tokens=None,
                 timeout=120, budget_usd=None, max_calls=None, seed=0, extra_body=None,
                 plan=False, outcomes=False, compact=False):
        self.model = model
        self.base_url = base_url.rstrip("/")
        # The key is sent only where it belongs: OPENROUTER_API_KEY to OpenRouter, and otherwise only a
        # key named here explicitly (a local server usually needs none).
        if api_key_env is None and "openrouter.ai" in self.base_url:
            api_key_env = "OPENROUTER_API_KEY"
        self.api_key_env = api_key_env
        self.plan = bool(plan)
        self.outcomes = bool(outcomes)
        self.compact = bool(compact)
        if self.plan:
            reasoning = True
        self.prompt = prompt
        self.reasoning = bool(reasoning)   # ask for a few visible sentences before the answer
        # Hidden model-side thinking: None switches it off (on OpenRouter); "low", "medium" or "high"
        # asks for that much effort. Thinking tokens count against max_tokens and are billed.
        self.thinking = thinking
        self.temperature = temperature
        if max_tokens is None:
            max_tokens = (300 if reasoning else 16) + (4000 if thinking else 0)
        self.plan_max_tokens = max_tokens + 600   # room for the plan at action decisions
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.budget_usd = budget_usd      # stop when this process has spent this much
        self.max_calls = max_calls        # or made this many calls
        self.seed = seed
        self.extra_body = dict(extra_body or {})
        self.stats = {"calls": 0, "retries": 0, "fallbacks": 0, "prompt_tokens": 0, "completion_tokens": 0,
                      "cost_usd": 0.0, "seconds": 0.0}
        self._info = None

    def settings(self):
        return {"model": self.model, "base_url": self.base_url, "prompt": self.prompt,
                "reasoning": self.reasoning, "thinking": self.thinking, "temperature": self.temperature,
                "max_tokens": self.max_tokens, "plan": self.plan, "outcomes": self.outcomes,
                "compact": self.compact,
                "system_prompt": getattr(self, "system", None)}

    def start(self, config, player_index, objective):
        super().start(config, player_index, objective)
        self.rng = _random.Random(self.seed * 9973 + player_index)
        self.current_plan = None
        self.turn_notes = (None, [])     # (turn number, [(label chosen, reasoning)]) for this player's own turn
        if self.api_key_env and not os.environ.get(self.api_key_env):
            load_env()
        self.system = prompts.template(self.prompt).format(
            player=player_index, players=config.n, objective=objective.describe(),
            rules=api.rules_summary(config),
            answer_format=ANSWER_REASONED if self.reasoning else ANSWER_ONLY)

    # ------------------------------------------------------------ the endpoint

    def call(self, messages, max_tokens=None):
        if self.budget_usd is not None and SPEND["cost_usd"] >= self.budget_usd:
            raise BudgetExceeded(f"language-model budget of ${self.budget_usd:.2f} is spent")
        if self.max_calls is not None and SPEND["calls"] >= self.max_calls:
            raise BudgetExceeded(f"language-model call limit of {self.max_calls} reached")
        body = {"model": self.model, "messages": messages, "temperature": self.temperature,
                "max_tokens": max_tokens or self.max_tokens}
        if "openrouter" in self.base_url:
            body["usage"] = {"include": True}
            body["reasoning"] = {"effort": self.thinking} if self.thinking else {"enabled": False}
        body.update(self.extra_body)
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env) if self.api_key_env else None
        if key:
            headers["Authorization"] = "Bearer " + key
        data = json.dumps(body).encode()
        last = None
        t0 = time.time()
        for attempt in range(4):
            try:
                req = urllib.request.Request(self.base_url + "/chat/completions", data=data, headers=headers)
                with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                    out = json.loads(resp.read().decode())
                if "choices" not in out:
                    raise RuntimeError(f"endpoint returned no choices: {str(out)[:300]}")
                break
            except urllib.error.HTTPError as e:
                detail = e.read().decode(errors="replace")[:300]
                last = RuntimeError(f"HTTP {e.code} from the model endpoint: {detail}")
                if e.code not in (408, 409, 429, 500, 502, 503, 504):
                    raise last
            except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
                last = RuntimeError(f"could not reach the model endpoint: {e}")
            time.sleep(2 ** attempt)
        else:
            raise last
        usage = out.get("usage") or {}
        cost = float(usage.get("cost") or 0.0)
        for stats in (self.stats, SPEND):
            stats["calls"] += 1
            stats["prompt_tokens"] += int(usage.get("prompt_tokens") or 0)
            stats["completion_tokens"] += int(usage.get("completion_tokens") or 0)
            stats["cost_usd"] += cost
        self.stats["seconds"] += time.time() - t0
        message = out["choices"][0].get("message") or {}
        usage = dict(usage, finish_reason=out["choices"][0].get("finish_reason"),
                     reasoning_tokens=(usage.get("completion_tokens_details") or {}).get("reasoning_tokens"))
        return message.get("content") or "", usage

    # ------------------------------------------------------------ choosing

    def build_prompt(self, observation, decision):
        """The user message, and how its answer is read: "one" (an option number) or "keep" (bird numbers)."""
        if self.compact:
            what, labels = api.describe_decision_compact(observation)
        else:
            what, labels = api.describe_decision(observation)
        lines = [api.describe_observation(observation), ""]
        if self.plan:
            lines += ["YOUR PLAN (your own notes from earlier turns; they may be out of date. If they conflict "
                      "with the position above, trust the position):", self.current_plan or "(none yet)", ""]
            turn, notes = self.turn_notes
            if notes and turn == observation.state.turn_no and decision.kind != "action":
                lines.append("THIS TURN SO FAR:")
                for label, why in notes:
                    lines.append(f"- You chose: {label}" + (f" Your reasoning: {why}" if why else ""))
                lines.append("")
        keep = api.describe_keep_birds(observation) if self.compact else None
        if keep:
            lines += ["DECISION: " + what, "", "Your dealt birds:"]
            lines += [f"{i}. {line}" for i, (_, line) in enumerate(keep, 1)]
            lines += ["", KEEP_ASK]
            return "\n".join(lines), "keep", keep
        after = api.describe_outcomes(observation) if self.outcomes else None
        lines += ["DECISION: " + what, "", "Your options:"]
        for i, label in enumerate(labels, 1):
            lines.append(f"{i}. {label}")
            if after and after[i - 1]:
                lines.append(f"   After: {after[i - 1]}")
        if self.plan and decision.kind == "action":
            lines += ["", PLAN_ASK]
        return "\n".join(lines), "one", None

    def choose(self, observation, decision):
        n = len(decision.options)
        user, mode, keep = self.build_prompt(observation, decision)
        system = {"role": "system", "content": self.system}
        if self.model.startswith("anthropic/"):   # let the provider cache the long, unchanging system prompt
            system = {"role": "system", "content": [{"type": "text", "text": self.system,
                                                     "cache_control": {"type": "ephemeral"}}]}
        messages = [system, {"role": "user", "content": user}]
        planning = self.plan and decision.kind == "action"
        limit = self.plan_max_tokens if planning else None

        def read(reply):
            if mode == "one":
                return parse_choice(reply, n, strict=self.reasoning)
            nums = parse_numbers(reply, len(keep))
            if nums is None:
                return None
            wanted = {keep[k - 1][0] for k in nums}
            for i, o in enumerate(decision.options):
                if set(o[1]) == wanted:
                    return i + 1
            return None

        replies = []
        reply, usage = self.call(messages, limit)
        replies.append(reply)
        k = read(reply)
        if k is None:
            self.stats["retries"] += 1
            if mode == "keep":
                again = "That was not a valid answer. " + KEEP_ASK
            elif planning:
                again = (f"Your reply had no valid 'ANSWER: <number>' line (it may have been cut off). Reply now with "
                         f"only 'ANSWER: <number>' (1 to {n}), then your plan in the same form, kept short.")
            else:
                again = f"That was not a valid choice. Reply with one number from 1 to {n}: the option you choose."
            messages += [{"role": "assistant", "content": reply or "(no answer)"}, {"role": "user", "content": again}]
            reply, usage = self.call(messages, limit)
            replies.append(reply)
            k = read(reply)
        fallback = k is None
        if fallback:
            self.stats["fallbacks"] += 1
            k = self.rng.randrange(n) + 1
        plan_in = self.current_plan
        plan_out = None
        if planning:
            plan_out = parse_plan(replies[0]) or (parse_plan(replies[-1]) if len(replies) > 1 else None)
            if plan_out:
                self.current_plan = plan_out
        if self.plan and observation.state.phase == api.TURNS and observation.state.turn == self.player:
            turn = observation.state.turn_no
            notes = self.turn_notes[1] if self.turn_notes[0] == turn else []
            why = None
            if decision.kind == "action":
                why = strip_reply(replies[-1])
                why = re.sub(r"ANSWER\s*[:=].*", "", why, flags=re.S | re.IGNORECASE).strip()[:NOTE_LIMIT] or None
            label = api.describe_decision(observation)[1][k - 1]
            self.turn_notes = (turn, notes + [(label, why)])
        self._info = {"model": self.model, "prompt": user, "replies": replies, "chosen": k,
                      "fallback": "random" if fallback else None,
                      "usage": {key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "cost",
                                                                "reasoning_tokens", "finish_reason")}}
        if self.plan:
            self._info["plan"] = plan_in
            self._info["plan_updated"] = plan_out
        return decision.options[k - 1]

    def info(self):
        return self._info
