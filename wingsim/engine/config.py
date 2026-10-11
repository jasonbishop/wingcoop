"""Game configuration: player count, plugins and settings. Immutable once built."""
from .cards import db
from ..plugins import Plugin, _overrides, make_plugins
from ..plugins import open_hands as _open_hands


class GameConfig:
    def __init__(self, n_players, plugins=None, open_hands=None, win_condition="individual",
                 team_target=None, record_events=False):
        if not 2 <= n_players <= 5:
            raise ValueError("v1 supports 2 to 5 players")
        if win_condition not in ("individual", "team_total"):
            raise ValueError(f"unknown win_condition: {win_condition}")
        spec = dict(plugins or {})
        if open_hands is None:
            open_hands = _open_hands.resolve({"plugins": spec})
        self.n = n_players
        self.db = db()
        self.open_hands = bool(open_hands)
        self.win_condition = win_condition
        self.team_target = team_target
        self.record_events = record_events
        self.plugins = tuple(make_plugins(spec))
        self.event_plugins = tuple(p for p in self.plugins if _overrides(p, "on_event"))
        self.option_plugins = tuple(p for p in self.plugins if _overrides(p, "extra_options"))
        self.scoring_plugins = tuple(p for p in self.plugins if _overrides(p, "round_end_scoring"))
        self.final_plugins = tuple(p for p in self.plugins if _overrides(p, "final_scoring"))
        self.plugin_tags = {tag: p for p in self.plugins for tag in p.option_tags}
        self.resolved = {
            "players": n_players,
            "plugins": {p.name: p.settings for p in self.plugins},
            "open_hands": self.open_hands,
            "win_condition": win_condition,
            "team_target": team_target,
        }

    def with_events(self, record):
        if record == self.record_events:
            return self
        return GameConfig(self.n, self.resolved["plugins"], self.open_hands, self.win_condition,
                          self.team_target, record)
