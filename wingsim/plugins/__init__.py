"""Rule-variant plugins. A plugin changes the game only through these hooks."""


class Plugin:
    name = ""
    option_tags = ()  # first elements of the option tuples this plugin adds

    def __init__(self, **settings):
        self.settings = settings

    def on_setup(self, s):
        """After normal setup: initialize entries in s.variant (immutable values only)."""

    def before_round(self, s, r):
        """Before rounds 1 to 4: may raise group decisions with rules.push_group_decision."""

    def on_group_choice(self, s, kind, choice):
        """A group decision this plugin raised has been answered."""

    def extra_options(self, s, p, when):
        """Extra legal options for player p; `when` is "turn_start" or "turn_end"."""
        return ()

    def apply_option(self, s, p, option):
        """Carry out one of this plugin's extra options."""

    def on_event(self, s, kind, data):
        """After every engine event."""

    def round_end_scoring(self, s, counts):
        """Replace goal scoring: return (points per player, group score change, info) or None.

        Must be a pure function of the state and counts, because agents also use
        it to ask what a hypothetical set of counts would score.
        """
        return None

    def final_scoring(self, s, result):
        """Adjust result["players"][i] entries or result["group"] at scoring time."""

    def rules_text(self):
        """This plugin's rules in plain words, for the language-model agent's rules summary."""
        return ""

    def status_text(self, s):
        """One line describing this plugin's current state, for observations shown as text."""
        return ""

    def option_label(self, s, option):
        """A short description of one of this plugin's options, or "" if it is not this plugin's."""
        return ""


def _overrides(plugin, method):
    return getattr(type(plugin), method) is not getattr(Plugin, method)


def make_plugins(spec):
    """Build plugin instances from a {name: settings} mapping, in a fixed order."""
    from .coop_goals import CoopGoals

    registry = {"coop_goals": CoopGoals}
    try:
        from .help_action import HelpAction
        registry["help_action"] = HelpAction
    except ImportError:
        pass
    out = []
    for name in sorted(spec or {}):
        if name == "open_hands":
            continue  # a setting, resolved by plugins.open_hands
        if name not in registry:
            raise ValueError(f"unknown plugin: {name}")
        out.append(registry[name](**(spec[name] or {})))
    return out
