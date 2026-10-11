"""The open_hands setting (on by default).

With open hands every player sees every hand and every bonus card; the deck
order stays hidden. It stands in for the table talk real cooperative players
would have. It may be given at the top level of a condition or, as in the
spec's example file, inside its `plugins` mapping.
"""

DEFAULT = True


def resolve(condition):
    plugins = condition.get("plugins") or {}
    if "open_hands" in plugins:
        return bool(plugins["open_hands"])
    return bool(condition.get("open_hands", DEFAULT))
