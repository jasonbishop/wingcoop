"""Prompt text for the language-model agent. Edit the .md files here to change what the model is told.

rules.md       the base-game rules summary (house rules are appended by the engine)
default.md     the system prompt template; copy it to try a variant and set `prompt: <name>` on the agent
plan.md        the system prompt for seats with `plan` on
coach.md       the system prompt of the coach call (`coach: true`)
"""
import pathlib

HERE = pathlib.Path(__file__).parent


def rules_text():
    return (HERE / "rules.md").read_text().strip()


def template(name="default"):
    path = HERE / f"{name}.md"
    if not path.exists():
        raise ValueError(f"no prompt template named {name!r} in {HERE}")
    return path.read_text().strip()
