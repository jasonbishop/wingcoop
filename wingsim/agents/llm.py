"""Language-model agent (optional, for spot checks).

Calls any OpenAI-compatible chat endpoint (OpenRouter, Ollama, LM Studio,
vLLM). The prompt holds a rules summary, the objective in plain words, the
observation as text and a numbered list of legal options; the reply is parsed
as an option number. If it cannot be parsed the agent asks once more, then
picks at random and records that it did. Every prompt and reply is kept for
the replay log.

All text about cards comes from the engine (api.describe_observation and
api.describe_decision); this module only assembles and sends it.
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


def parse_choice(reply, n):
    """The option number (1-based) named in a reply, or None."""
    if not reply:
        return None
    m = re.findall(r"ANSWER\s*[:=]?\s*\**\s*(\d+)", reply, flags=re.IGNORECASE)
    numbers = m if m else re.findall(r"\d+", reply)
    if not numbers:
        return None
    k = int(numbers[-1])
    return k if 1 <= k <= n else None


class LLMAgent(Agent):
    type = "llm"

    def __init__(self, model, base_url="https://openrouter.ai/api/v1", api_key_env="OPENROUTER_API_KEY",
                 prompt="default", reasoning=False, thinking=None, temperature=0.0, max_tokens=None,
                 timeout=120, budget_usd=None, max_calls=None, seed=0, extra_body=None):
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.api_key_env = api_key_env
        self.prompt = prompt
        self.reasoning = bool(reasoning)   # ask for a few visible sentences before the answer
        # Hidden model-side thinking: None switches it off (on OpenRouter); "low", "medium" or "high"
        # asks for that much effort. Thinking tokens count against max_tokens and are billed.
        self.thinking = thinking
        self.temperature = temperature
        if max_tokens is None:
            max_tokens = (300 if reasoning else 16) + (4000 if thinking else 0)
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
                "max_tokens": self.max_tokens,
                "system_prompt": getattr(self, "system", None)}

    def start(self, config, player_index, objective):
        super().start(config, player_index, objective)
        self.rng = _random.Random(self.seed * 9973 + player_index)
        if not os.environ.get(self.api_key_env):
            load_env()
        self.system = prompts.template(self.prompt).format(
            player=player_index, players=config.n, objective=objective.describe(),
            rules=api.rules_summary(config),
            answer_format=ANSWER_REASONED if self.reasoning else ANSWER_ONLY)

    # ------------------------------------------------------------ the endpoint

    def call(self, messages):
        if self.budget_usd is not None and SPEND["cost_usd"] >= self.budget_usd:
            raise BudgetExceeded(f"language-model budget of ${self.budget_usd:.2f} is spent")
        if self.max_calls is not None and SPEND["calls"] >= self.max_calls:
            raise BudgetExceeded(f"language-model call limit of {self.max_calls} reached")
        body = {"model": self.model, "messages": messages, "temperature": self.temperature,
                "max_tokens": self.max_tokens}
        if "openrouter" in self.base_url:
            body["usage"] = {"include": True}
            body["reasoning"] = {"effort": self.thinking} if self.thinking else {"enabled": False}
        body.update(self.extra_body)
        headers = {"Content-Type": "application/json"}
        key = os.environ.get(self.api_key_env)
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
        what, labels = api.describe_decision(observation)
        lines = [api.describe_observation(observation), "", "DECISION: " + what, "", "Your options:"]
        lines += [f"{i}. {label}" for i, label in enumerate(labels, 1)]
        return "\n".join(lines)

    def choose(self, observation, decision):
        n = len(decision.options)
        user = self.build_prompt(observation, decision)
        system = {"role": "system", "content": self.system}
        if self.model.startswith("anthropic/"):   # let the provider cache the long, unchanging system prompt
            system = {"role": "system", "content": [{"type": "text", "text": self.system,
                                                     "cache_control": {"type": "ephemeral"}}]}
        messages = [system, {"role": "user", "content": user}]
        replies = []
        reply, usage = self.call(messages)
        replies.append(reply)
        k = parse_choice(reply, n)
        if k is None:
            self.stats["retries"] += 1
            messages += [{"role": "assistant", "content": reply or "(no answer)"},
                         {"role": "user", "content": f"That was not a valid choice. Reply with one number "
                                                     f"from 1 to {n}: the option you choose."}]
            reply, usage = self.call(messages)
            replies.append(reply)
            k = parse_choice(reply, n)
        fallback = k is None
        if fallback:
            self.stats["fallbacks"] += 1
            k = self.rng.randrange(n) + 1
        self._info = {"model": self.model, "prompt": user, "replies": replies, "chosen": k,
                      "fallback": "random" if fallback else None,
                      "usage": {key: usage.get(key) for key in ("prompt_tokens", "completion_tokens", "cost",
                                                                "reasoning_tokens", "finish_reason")}}
        return decision.options[k - 1]

    def info(self):
        return self._info
