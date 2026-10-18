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
- `talk`: table talk. At each of its action decisions the model may add a line
  'SAY: <message>' for the other players; the seats that talk share a TableTalk
  (agents/talk.py) and see the recent messages in every prompt.
- `coach` and `digest` split the work over extra calls before each action decision.
  The coach (prompts/coach.md) reviews the position, the plan, the round goal and the
  player's recent actions and flags up to three problems, without choosing a move.
  The digest (with `talk`) runs when other players have said something new: the
  player reads the talk and notes what it changes. Their notes are shown to the
  player for the rest of the turn (the talk notes until the next digest). The player
  may answer its coach in one line 'TO COACH: <reply>'; the coach sees its own last
  notes and that reply at its next review.
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
from .talk import TableTalk

ANSWER_ONLY = "Reply with only the number of the option you choose. No other text."
ANSWER_REASONED = ("Think briefly (three sentences at most) about which option best serves your objective, "
                   "then finish with a line of the form 'ANSWER: <number>'.")
# reasoning: "full" asks for as much reasoning as the decision needs (for free local models, and for reading
# how the model understands the rules); plain reasoning keeps it to a few sentences, to save paid tokens.
ANSWER_FULL = ("Think through which option best serves your objective, in a few short paragraphs at most: what "
               "each serious option gains now and what it sets up for later rounds. Then finish with a line of the "
               "form 'ANSWER: <number>'.")
PLAN_FORM = "PLAN:\nEngine: ...\nBonus target: ...\nRound goal: ...\nNeed next: ...\nPivot if: ...\nEND PLAN"
PLAN_ASK = ("First check your plan against the position above: does it still hold given what has changed? Keep it, "
            "adjust it or drop it, and say why in one or two sentences. Then give your choice on a line of the form "
            "'ANSWER: <number>'. Then write your updated plan, short, in exactly this form:\n" + PLAN_FORM)
PLAN_LIMIT = 700          # characters kept from a plan
NOTE_LIMIT = 400          # characters kept from the reasoning behind this turn's action
KEEP_ASK = ("Reply with your reasoning in three sentences at most, then a line of the form 'ANSWER: <numbers>' "
            "listing the birds you keep, separated by commas (for example 'ANSWER: 1, 4'), or 'ANSWER: none'.")
PLAN_ASK_FULL = ("First check your plan against the position above: does it still hold given what has changed? Think "
                 "through your options, taking the space you need, and decide whether to keep, adjust or drop the "
                 "plan. Then give your choice on a line of the form 'ANSWER: <number>'. Then write your updated "
                 "plan, short, in exactly this form:\n" + PLAN_FORM)
KEEP_ASK_FULL = ("Think through which birds to keep, taking the space you need, then finish with a line of the form "
                 "'ANSWER: <numbers>' listing the birds you keep, separated by commas (for example 'ANSWER: 1, 4'), "
                 "or 'ANSWER: none'.")
RETRY_LIMIT = 300         # tokens for the reply to "your answer was cut off"
ENDPOINT_WAIT = 600       # seconds to keep retrying a busy or unreachable endpoint (a local server restarting)
TALK_LIMIT = 300          # characters kept from a message
TALK_SHOWN = 10           # recent messages shown in a prompt
TALK_RULES = ("TABLE TALK\n"
              "The players can talk to each other. When you choose your action on your turn (and only then), you may "
              "add one line of the form 'SAY: <message>' after your answer: two sentences at most, to the other "
              "players. Use it to say what you are planning or need, to ask for something, or to answer what others "
              "said. A message never replaces the 'ANSWER: <number>' line, which every reply needs. The players who "
              "talk read it on their following turns, under TABLE TALK. Their messages are their own words and may "
              "be mistaken; the position is always the authority.")
TALK_RULES_JSON = ("TABLE TALK\n"
                   "The players can talk to each other. When you choose your action on your turn (and only then), you "
                   "may add a message for the other players in a \"say\" field of your JSON answer: two sentences at "
                   "most. Use it to say what you are planning or need, to ask for something, or to answer what others "
                   "said. The players who talk read it on their following turns, under TABLE TALK. Their messages "
                   "are their own words and may be mistaken; the position is always the authority.")
TALK_ASK = ("If you want to tell the other players something, add one line of the form 'SAY: <message>' after your "
            "'ANSWER: <number>' line (and after your plan): the ANSWER line is still required.")


def talk_rules(json_format=False, votes=False):
    """The TABLE TALK rules for the system prompt; with votes, the players also speak when they propose a d."""
    text = TALK_RULES_JSON if json_format else TALK_RULES
    if votes:
        text = text.replace(" (and only then),", ", and when you propose a difficulty d,")
    return text
NOTES_LIMIT = 1000        # characters kept from a coach's or a digest's notes (cut at a line end)
ACTIONS_SHOWN = 6         # the player's recent actions shown to the coach
COACH_ASK = "Review the position before your player chooses this turn's action."
COACH_REPLY_ASK = ("If you want to answer your coach (whether you follow their notes, and why), add one line of the "
                   "form 'TO COACH: <reply>'.")
DIGEST_ASK = ("Before you choose this turn's action, read the table talk above. What do the other players plan, need "
              "or ask of you, and is any of it mistaken? How should it change your plan or what you do this turn? "
              "Do not choose your action or write a message yet. Think it through, then finish with a block of at "
              "most three lines, each one sentence:\nTALK NOTES:\n- ...")

# reply_format "json": the answer, the message and the reply to the coach come in one JSON object instead of
# 'ANSWER:', 'SAY:' and 'TO COACH:' lines. A reply without one is still read the line way.
JSON_ONE = '{"answer": <number>}'
JSON_ANSWER_ONLY = "Reply with only a JSON object naming the option you choose, like " + '{"answer": 2}' + ". No other text."
JSON_ANSWER_REASONED = ("Think briefly (three sentences at most) about which option best serves your objective, "
                        "then finish with a JSON object on its own line: " + JSON_ONE + ".")
JSON_ANSWER_FULL = ("Think through which option best serves your objective, in a few short paragraphs at most: what "
                    "each serious option gains now and what it sets up for later rounds. Then finish with a JSON "
                    "object on its own line: " + JSON_ONE + ".")
JSON_PLAN_ASK = ("First check your plan against the position above: does it still hold given what has changed? Keep "
                 "it, adjust it or drop it, and say why in one or two sentences. Then give your choice as a JSON "
                 "object on its own line: " + JSON_ONE + ". Then write your updated plan, short, in exactly this "
                 "form:\n" + PLAN_FORM)
JSON_PLAN_ASK_FULL = ("First check your plan against the position above: does it still hold given what has changed? "
                      "Think through your options, taking the space you need, and decide whether to keep, adjust or "
                      "drop the plan. Then give your choice as a JSON object on its own line: " + JSON_ONE + ". Then "
                      "write your updated plan, short, in exactly this form:\n" + PLAN_FORM)
JSON_KEEP_ASK = ("Reply with your reasoning in three sentences at most, then a JSON object on its own line listing "
                 'the birds you keep (for example {"answer": [1, 4]}, or {"answer": []} for none).')
JSON_KEEP_ASK_FULL = ("Think through which birds to keep, taking the space you need, then finish with a JSON object on "
                      'its own line listing the birds you keep (for example {"answer": [1, 4]}, or {"answer": []} '
                      "for none).")
JSON_TALK_ASK = ('If you want to tell the other players something, add a "say" field to your JSON object: two '
                 "sentences at most. Leave it out to say nothing.")
JSON_COACH_REPLY_ASK = ('If you want to answer your coach (whether you follow their notes, and why), add a "to_coach" '
                        "field to your JSON object: one sentence or two.")
JSON_RE = re.compile(r'\{[^{}]*"answer"[^{}]*\}', re.S)     # a JSON answer object (flat: no nested braces)
JSON_START = r'(?=^[ \t]*(?:```(?:json)?\s*)?\{\s*"answer")'

# The talk group policy (agents/group_policies.py): the players who talk set the co-op difficulty together.
VOTE_RULES = ("SETTING THE DIFFICULTY\n"
              "The players who talk set the co-op difficulty d together, before round 1 and again before each later "
              "round (within the changes the rules allow). Each of them proposes a d in turn, seeing the proposals "
              "made before theirs under TABLE TALK. If all the proposals agree, that d is set. Otherwise each "
              "proposes once more, seeing all the first proposals, and then the lowest proposal is set.")
VOTE_ASK = {1: "Propose the difficulty d for the coming round.",
            2: "The first proposals did not agree (they are under TABLE TALK). Propose once more: after this, the "
               "lowest proposal is set."}

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


def drop_thinking(reply):
    """The reply without hidden reasoning (<think>...</think>). An opening tag with no closing tag is dropped on
    its own: some local servers (mlx-openai-server with a Qwen reasoning parser) put a stray '<think>' before
    the visible answer when thinking is off."""
    reply = re.sub(r"<think>.*?</think>", "", reply or "", flags=re.S)
    return reply.replace("<think>", "")


# A plan block starts with "PLAN:" at the start of a line, as the prompt asks ("my plan: ..." inside the
# reasoning is not one; matching it once cut the ANSWER line off a reply). It ends at "END PLAN", or, when
# the model leaves that out, where an ANSWER or the next plan block begins, or at the end of the reply.
PLAN_START = r"^[*#\s]*PLAN:"
SAY_START = r"^[*#\s]*SAY:"
COACH_START = r"^[*#\s]*TO COACH:"
PLAN_END = (r"(?:END PLAN|(?=(?i:ANSWER)\s*[:=])|(?=" + PLAN_START + r")|(?=" + SAY_START + r")|(?=" + COACH_START
            + r")|" + JSON_START + r"|\Z)")


def strip_reply(reply):
    """The reply without hidden-reasoning tags (<think>...</think>), a plan block, a SAY line or a JSON answer."""
    reply = drop_thinking(reply)
    reply = re.sub(PLAN_START + r".*?" + PLAN_END, "", reply, flags=re.S | re.M)
    reply = re.sub(r"```(?:json)?\s*(" + JSON_RE.pattern + r")\s*```", "", reply)
    reply = JSON_RE.sub("", reply)
    return re.sub("(" + SAY_START + "|" + COACH_START + r").*$", "", reply, flags=re.M)


def parse_json(reply):
    """The last JSON object of the reply that has an "answer" field, as a dict, or None."""
    for text in reversed(JSON_RE.findall(drop_thinking(reply))):
        try:
            obj = json.loads(text)
        except ValueError:
            continue
        if isinstance(obj, dict) and "answer" in obj:
            return obj
    return None


def parse_notes(reply, header="NOTES"):
    """The lines after the reply's last '<header>:' line, or else its last paragraph, without any answer the
    reply gave (a digest sometimes chooses the move anyway); at most NOTES_LIMIT characters, cut at a line end."""
    reply = drop_thinking(reply).strip()
    blocks = re.split(r"^[*#\s]*" + header + r":\**[ \t]*\n?", reply, flags=re.M)
    text = blocks[-1] if len(blocks) > 1 else reply.split("\n\n")[-1]
    text = JSON_RE.sub("", re.sub(r"^[*#\s]*ANSWER\s*[:=].*$", "", text, flags=re.M | re.IGNORECASE))
    text = re.sub(r"```(?:json)?\s*```", "", text).strip()
    if len(text) > NOTES_LIMIT:
        cut = text[:NOTES_LIMIT]
        text = cut[:cut.rfind("\n")] if "\n" in cut else cut
    return text.strip() or None


def clean_message(text):
    """A message as kept: None for nothing, 'none' or the like; at most TALK_LIMIT characters."""
    text = text.strip().strip('*"').strip() if isinstance(text, str) else ""
    if not text or re.fullmatch(r"\W*(nothing|none|null|n/a|-)\W*", text, flags=re.IGNORECASE):
        return None
    return text[:TALK_LIMIT]


def parse_say(reply, start=SAY_START):
    """The message of the reply's last 'SAY:' line (or another such line), or None (also for 'SAY: nothing')."""
    lines = re.findall(start + r"\**\s*(.*)$", drop_thinking(reply), flags=re.M)
    return clean_message(lines[-1]) if lines else None


def parse_plan(reply):
    """The plan block of a reply (between 'PLAN:' and 'END PLAN'), or None."""
    reply = drop_thinking(reply)
    # the last block: the updated plan comes after the answer, and the reasoning may quote the old one
    blocks = re.findall(PLAN_START + r"\**\s*(.*?)\s*" + PLAN_END, reply, flags=re.S | re.M)
    m = blocks[-1] if blocks else None
    if not m or not m.strip():
        return None
    return m.strip()[:PLAN_LIMIT]


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
                 plan=False, outcomes=False, compact=False, goal_status=False, talk=False, coach=False,
                 digest=False, reply_format="lines"):
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
        self.goal_status = bool(goal_status)   # a block on where the table stands on the round goal
        self.talk = bool(talk)                 # table talk; the runner shares one TableTalk between talkers
        self.table = None
        self.coach = bool(coach)               # an extra call that flags problems before each action
        self.digest = bool(digest) and self.talk   # an extra call that reads new table talk before each action
        if reply_format not in ("lines", "json"):
            raise ValueError(f"unknown reply_format: {reply_format!r} (lines or json)")
        self.json = reply_format == "json"     # the answer, message and coach reply as one JSON object
        self.votes = False                     # proposes the co-op difficulty (the talk group policy)
        if self.plan and not reasoning:    # a plan needs visible reasoning; "full" stays full
            reasoning = True
        self.prompt = prompt
        self.full = reasoning == "full"    # as much visible reasoning as the decision needs
        self.reasoning = bool(reasoning)   # visible reasoning before the answer (a few sentences unless full)
        # Hidden model-side thinking: None switches it off (on OpenRouter); "low", "medium" or "high"
        # asks for that much effort. Thinking tokens count against max_tokens and are billed.
        self.thinking = thinking
        self.temperature = temperature
        if max_tokens is None:
            max_tokens = (4000 if self.full else 600 if reasoning else 16) + (4000 if thinking else 0)
        self.plan_max_tokens = max_tokens + 600   # room for the plan at action decisions
        self.max_tokens = max_tokens
        self.last_thinking = None
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
                "reasoning": "full" if self.full else self.reasoning, "thinking": self.thinking, "temperature": self.temperature,
                "max_tokens": self.max_tokens, "plan": self.plan, "outcomes": self.outcomes,
                "compact": self.compact, "goal_status": self.goal_status, "talk": self.talk,
                "coach": self.coach, "digest": self.digest,
                "reply_format": "json" if self.json else "lines", "votes": self.votes,
                "system_prompt": getattr(self, "system", None),
                "coach_system_prompt": getattr(self, "coach_system", None)}

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
            answer_format=self.answer_text("full" if self.full else "reasoned" if self.reasoning else "only"))
        if self.talk:
            self.system += "\n\n" + talk_rules(self.json)
            self.table = TableTalk([player_index])   # alone until the runner seats it at a shared table
        self.coach_system = prompts.template("coach").format(
            player=player_index, players=config.n, objective=objective.describe(),
            rules=api.rules_summary(config)) if self.coach else None
        self.coach_notes = (None, None)   # (turn number, notes) for this player's own turn
        self.talk_notes = None            # (round, turn number, notes) from the latest digest
        self.talk_seen = 0                # table messages already read in a digest
        self.my_actions = []              # (round, turn number, label) of this player's actions so far
        self.last_coach = None            # (round, turn number, notes) of the coach's latest review
        self.to_coach = None              # (round, turn number, reply) the player last gave its coach

    def join_vote(self):
        """Seat this talking player among those who set the co-op difficulty (the talk group policy)."""
        if not self.talk:
            raise ValueError("only a seat that talks can propose the difficulty")
        self.votes = True
        self.system = self.system.replace(talk_rules(self.json), talk_rules(self.json, votes=True))
        self.system += "\n\n" + VOTE_RULES

    def answer_text(self, name):
        """The answer instructions in this seat's reply format."""
        lines = {"only": ANSWER_ONLY, "reasoned": ANSWER_REASONED, "full": ANSWER_FULL, "plan": PLAN_ASK,
                 "plan_full": PLAN_ASK_FULL, "keep": KEEP_ASK, "keep_full": KEEP_ASK_FULL, "talk": TALK_ASK,
                 "coach": COACH_REPLY_ASK}
        as_json = {"only": JSON_ANSWER_ONLY, "reasoned": JSON_ANSWER_REASONED, "full": JSON_ANSWER_FULL,
                   "plan": JSON_PLAN_ASK, "plan_full": JSON_PLAN_ASK_FULL, "keep": JSON_KEEP_ASK,
                   "keep_full": JSON_KEEP_ASK_FULL, "talk": JSON_TALK_ASK, "coach": JSON_COACH_REPLY_ASK}
        return (as_json if self.json else lines)[name]

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
        waited, attempt = 0, 0
        while True:
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
            if waited >= ENDPOINT_WAIT:
                raise last
            delay = min(2 ** attempt, 30)
            time.sleep(delay)
            waited, attempt = waited + delay, attempt + 1
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
        # Hidden thinking, when the server returns it apart from the answer (OpenRouter: "reasoning";
        # mlx-openai-server and vLLM with a reasoning parser: "reasoning_content").
        self.last_thinking = message.get("reasoning_content") or message.get("reasoning") or None
        return message.get("content") or "", usage

    # ------------------------------------------------------------ choosing

    def build_prompt(self, observation, decision, vote=None):
        """The user message, and how its answer is read: "one" (an option number) or "keep" (bird numbers).
        `vote` (1 or 2) makes it a proposal of the co-op difficulty, in that pass of the talk group policy."""
        if self.compact:
            what, labels = api.describe_decision_compact(observation)
        else:
            what, labels = api.describe_decision(observation)
        lines = [api.describe_observation(observation), ""]
        status = api.describe_goal_status(observation) if self.goal_status else None
        if status:
            lines += [status, ""]
        if self.plan:
            lines += ["YOUR PLAN (your own notes from earlier turns; they may be out of date. If they conflict "
                      "with the position above, trust the position):", self.current_plan or "(none yet)", ""]
            turn, notes = self.turn_notes
            if notes and turn == observation.state.turn_no and decision.kind != "action" and vote is None:
                lines.append("THIS TURN SO FAR:")
                for label, why in notes:
                    lines.append(f"- You chose: {label}" + (f" Your reasoning: {why}" if why else ""))
                lines.append("")
        if self.talk:
            lines += self.talk_block() + [""]
        lines += self.notes_block(observation)
        keep = api.describe_keep_birds(observation) if self.compact else None
        if keep:
            lines += ["DECISION: " + what, "", "Your dealt birds:"]
            lines += [f"{i}. {line}" for i, (_, line) in enumerate(keep, 1)]
            lines += ["", self.answer_text("keep_full" if self.full else "keep")]
            return "\n".join(lines), "keep", keep
        after = api.describe_outcomes(observation) if self.outcomes else None
        lines += ["DECISION: " + what, "", "Your options:"]
        for i, label in enumerate(labels, 1):
            lines.append(f"{i}. {label}")
            if after and after[i - 1]:
                lines.append(f"   After: {after[i - 1]}")
        if self.plan and decision.kind == "action":
            lines += ["", self.answer_text("plan_full" if self.full else "plan")]
        if vote:
            lines += ["", VOTE_ASK[vote]]
        if self.talk and (decision.kind == "action" or vote):
            lines += ["", self.answer_text("talk")]
        if self.coach and decision.kind == "action" and self.coach_notes[1]:
            ask = self.answer_text("coach")
            lines += [ask] if self.talk else ["", ask]   # under the SAY line if any
        return "\n".join(lines), "one", None

    def notes_block(self, observation):
        """The coach's notes (for the rest of this turn) and the latest talk notes, as prompt lines."""
        lines = []
        turn, notes = self.coach_notes
        if self.coach and notes and turn == observation.state.turn_no:
            lines += ["COACH NOTES (your coach reviewed this position before your action; advice, not orders, and "
                      "it may be mistaken):", notes, ""]
        if self.digest and self.talk_notes:
            r, t, notes = self.talk_notes
            lines += [f"YOUR NOTES ON THE TABLE TALK (written round {r}, turn {t}):", notes, ""]
        return lines

    def coach_prompt(self, observation):
        lines = [api.describe_observation(observation), ""]
        status = api.describe_goal_status(observation)
        if status:
            lines += [status, ""]
        if self.plan:
            lines += ["YOUR PLAYER'S PLAN:", self.current_plan or "(none yet)", ""]
        if self.last_coach:
            r, t, notes = self.last_coach
            lines += [f"YOUR NOTES LAST TIME (round {r}, turn {t}):", notes or "(none)", ""]
            reply = self.to_coach[2] if self.to_coach and self.to_coach[:2] == (r, t) else None
            lines += ["YOUR PLAYER'S REPLY:", reply or "(no reply)", ""]
        lines.append("YOUR PLAYER'S RECENT ACTIONS (oldest first):")
        recent = self.my_actions[-ACTIONS_SHOWN:]
        lines += [f"- round {r}, turn {t}: {label}" for r, t, label in recent] or ["(none yet)"]
        return "\n".join(lines + ["", COACH_ASK])

    def digest_prompt(self, observation):
        lines = [api.describe_observation(observation), ""]
        if self.plan:
            lines += ["YOUR PLAN:", self.current_plan or "(none yet)", ""]
        lines += self.talk_block() + ["", DIGEST_ASK]
        return "\n".join(lines)

    def consult(self, observation):
        """The extra calls before an action decision: the digest (if others said something new), then the coach.
        Returns their records for the log."""
        s, calls = observation.state, []
        keys = ("prompt_tokens", "completion_tokens", "cost", "reasoning_tokens", "finish_reason")

        def ask(role, system, user, header):
            reply, usage = self.call([{"role": "system", "content": system}, {"role": "user", "content": user}])
            notes = parse_notes(reply, header)
            calls.append({"role": role, "prompt": user, "reply": reply, "thinking": self.last_thinking,
                          "usage": {k: usage.get(k) for k in keys}, "limit": self.max_tokens, "notes": notes})
            return notes

        new = [m for m in self.table.messages[self.talk_seen:] if m["player"] != self.player] if self.digest else []
        if new:
            notes = ask("digest", self.system, self.digest_prompt(observation), "TALK NOTES")
            self.talk_seen = len(self.table.messages)
            if notes:
                self.talk_notes = (s.round, s.turn_no, notes)
        if self.coach:
            notes = ask("coach", self.coach_system, self.coach_prompt(observation), "NOTES")
            self.coach_notes = (s.turn_no, notes)
            self.last_coach = (s.round, s.turn_no, notes)
        return calls

    def talk_block(self):
        """The TABLE TALK lines: who talks, then the recent messages, oldest first."""
        who = ", ".join(f"player {p}" + (" (you)" if p == self.player else "") for p in self.table.members)
        lines = [f"TABLE TALK (players who talk: {who}; the others are bots and neither read nor speak):"]
        shown = self.table.recent(TALK_SHOWN)
        if not shown:
            lines.append("(nothing said yet)")
        for m in shown:
            you = " (you)" if m["player"] == self.player else ""
            lines.append(f"- round {m['round']}, turn {m['turn_no']}, player {m['player']}{you}: {m['text']}")
        return lines

    def choose(self, observation, decision, vote=None):
        """The option chosen. `vote` (1 or 2): this is a proposal of the co-op difficulty, in that pass of the
        talk group policy; the proposal goes to the table talk with the message, if any."""
        n = len(decision.options)
        acting = decision.kind == "action"
        aux = self.consult(observation) if acting and (self.coach or self.digest) else []
        user, mode, keep = self.build_prompt(observation, decision, vote)
        system = {"role": "system", "content": self.system}
        if self.model.startswith("anthropic/"):   # let the provider cache the long, unchanging system prompt
            system = {"role": "system", "content": [{"type": "text", "text": self.system,
                                                     "cache_control": {"type": "ephemeral"}}]}
        messages = [system, {"role": "user", "content": user}]
        planning = self.plan and acting
        limit = self.plan_max_tokens if planning else None

        def read(reply, bare_ok=False):
            obj = parse_json(reply) if self.json else None
            if obj is not None:
                return read_json(obj["answer"])
            if mode == "one":
                bare = bare_ok and re.fullmatch(r"\W*\d+\W*", strip_reply(reply) or "")
                return parse_choice(reply, n, strict=self.reasoning and not bare)
            return kept(parse_numbers(reply, len(keep)))

        def read_json(answer):
            if mode == "one":
                try:
                    k = int(answer)
                except (TypeError, ValueError):
                    return None
                return k if 1 <= k <= n else None
            if isinstance(answer, (int, str)) and not isinstance(answer, bool):
                answer = [] if str(answer).strip().lower() in ("", "none") else [answer]
            try:
                nums = sorted({int(x) for x in answer})
            except (TypeError, ValueError):
                return None
            return kept(nums) if all(1 <= x <= len(keep) for x in nums) else None

        def kept(nums):
            if nums is None:
                return None
            wanted = {keep[k - 1][0] for k in nums}
            for i, o in enumerate(decision.options):
                if set(o[1]) == wanted:
                    return i + 1
            return None

        replies, thoughts, usages, limits = [], [], [], []
        reply, usage = self.call(messages, limit)
        replies.append(reply)
        thoughts.append(self.last_thinking)
        usages.append(usage)
        limits.append(limit or self.max_tokens)
        k = read(reply)
        if k is None:
            self.stats["retries"] += 1
            retry_limit = limit
            if self.json:
                form, line = '{"answer": <number>}', "JSON answer"
            else:
                form, line = "'ANSWER: <number>'", "'ANSWER: <number>' line"
            if mode == "keep":
                again = "That was not a valid answer. " + self.answer_text("keep_full" if self.full else "keep")
            elif planning:
                again = (f"Your reply had no valid {line} (it may have been cut off). Reply now with "
                         f"only {form} (1 to {n})" + (", with any other fields you meant to add" if self.json else "")
                         + ", then your plan in the same form, kept short.")
            elif self.reasoning:
                # The usual cause is reasoning that ran past max_tokens; asking again with the same room only
                # lets it run out again. Some models start reasoning again even when told not to, so the
                # reply gets room for a sentence or two.
                again = (f"Your reply had no {line} (it may have been cut off). Do not start over: "
                         f"in one sentence at most, finish your decision, then give "
                         + (f"the JSON object {form}" if self.json else f"the line {form}") + f" (1 to {n}).")
                retry_limit = RETRY_LIMIT
            elif self.json:
                again = f"That was not a valid choice. Reply with only {form}, the option you choose (1 to {n})."
            else:
                again = f"That was not a valid choice. Reply with one number from 1 to {n}: the option you choose."
            messages += [{"role": "assistant", "content": reply or "(no answer)"}, {"role": "user", "content": again}]
            reply, usage = self.call(messages, retry_limit)
            replies.append(reply)
            thoughts.append(self.last_thinking)
            usages.append(usage)
            limits.append(retry_limit or self.max_tokens)
            k = read(reply, bare_ok=True)
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
        if (self.plan and vote is None and observation.state.phase == api.TURNS
                and observation.state.turn == self.player):
            turn = observation.state.turn_no
            notes = self.turn_notes[1] if self.turn_notes[0] == turn else []
            why = None
            if acting:
                why = strip_reply(replies[-1])
                why = re.sub(r"ANSWER\s*[:=].*", "", why, flags=re.S | re.IGNORECASE).strip()[:NOTE_LIMIT] or None
            label = api.describe_decision(observation)[1][k - 1]
            self.turn_notes = (turn, notes + [(label, why)])
        keys = ("prompt_tokens", "completion_tokens", "cost", "reasoning_tokens", "finish_reason")
        usages = [{key: u.get(key) for key in keys} for u in usages]
        # usage is the last call's (kept for older readers); usage_all and limits are per reply
        self._info = {"model": self.model, "prompt": user, "replies": replies, "chosen": k,
                      "fallback": "random" if fallback else None, "usage": usages[-1],
                      "usage_all": usages, "limits": limits}
        if any(thoughts):
            self._info["thinking"] = thoughts
        if self.plan:
            self._info["plan"] = plan_in
            self._info["plan_updated"] = plan_out
        s = observation.state
        if self.talk and (acting or vote):
            said = self.message(replies, "say", SAY_START)
            self._info["said"] = said
            if vote:
                text = f"(proposes d = {decision.options[k - 1][1]})" + (" " + said if said else "")
                self._info["posted"] = text
                self.table.post(s.round, s.turn_no, self.player, text)
            elif said:
                self.table.post(s.round, s.turn_no, self.player, said)
        if acting and (self.coach or self.digest):
            self._info["aux"] = aux
            self._info["coach"] = next((c["notes"] for c in aux if c["role"] == "coach"), None)
            self._info["digest"] = next((c["notes"] for c in aux if c["role"] == "digest"), None)
        if self.coach and acting:
            reply = self.message(replies, "to_coach", COACH_START)
            self.to_coach = (s.round, s.turn_no, reply) if reply else None
            self._info["to_coach"] = reply
        if acting:
            self.my_actions.append((s.round, s.turn_no, api.describe_decision(observation)[1][k - 1]))
        return decision.options[k - 1]

    def message(self, replies, field, start):
        """A message of the first reply, or else of the retry: the JSON field (in the json format) or the line."""
        for reply in (replies[:1] + replies[1:][-1:]):
            obj = parse_json(reply) if self.json else None
            text = clean_message(obj.get(field)) if obj and field in obj else parse_say(reply, start)
            if text:
                return text
        return None

    def info(self):
        return self._info
