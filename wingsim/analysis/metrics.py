"""Decision-level metrics, tallied by the experiment runner while a game is played.

The runner (not the agents) owns a DecisionTally and shows it the full state,
the decision and the choice at every decision.
"""
from collections import Counter

from .tags import all_tags


def vp_bucket(vp):
    return "0-2" if vp <= 2 else "3-4" if vp <= 4 else "5-6" if vp <= 6 else "7+"


class DecisionTally:
    """Counts per game. `offers` maps (where, shares_benefit, food cost, points bucket) to [offered, chosen]."""

    def __init__(self, db):
        self.db = db
        self.tags = all_tags()
        self.counts = Counter()
        self.offers = {}

    def _offer(self, where, cid, chosen):
        b = self.db.birds[cid]
        key = (where, "shares_benefit" in self.tags[cid], b.total_cost, vp_bucket(b.vp))
        cell = self.offers.setdefault(key, [0, 0])
        cell[0] += 1
        cell[1] += 1 if chosen else 0

    def record(self, s, d, choice):
        c = self.counts
        kind = d.kind
        c["decisions"] += 1
        if kind == "action":
            c["act_" + choice[0]] += 1
            # Pick rate: among birds that were affordable and had a slot, was this one played?
            seen = set()
            for o in d.options:
                if o[0] == "play" and o[1] not in seen:
                    seen.add(o[1])
                    self._offer("play", o[1], choice[0] == "play" and choice[1] == o[1])
        elif kind == "draw_card":
            # The same for taking face-up birds from the tray.
            if len(d.options) > 1:
                for o in d.options:
                    if o[0] == "tray":
                        self._offer("tray", o[1], choice == o)
        elif kind == "take_die":
            self._die(s, d, choice)
        elif kind == "activate_power":
            cid = d.options[0][1]
            b = self.db.birds[cid]
            if b.timing == "brown":
                shared = "shares_benefit" in self.tags[cid]
                c["brown_shared_offered" if shared else "brown_other_offered"] += 1
                if choice[0] == "activate":
                    c["brown_shared_used" if shared else "brown_other_used"] += 1

    def _needed_by_others(self, s, p):
        """Food types another player lacks for a bird in their hand (specific foods in its cost)."""
        need = set()
        birds = self.db.birds
        for j, pl in enumerate(s.players):
            if j == p:
                continue
            for cid in pl.hand:
                b = birds[cid]
                for f in range(5):
                    if b.cost[f] and pl.food[f] < (1 if b.either else b.cost[f]):
                        need.add(f)
        return need

    def _die(self, s, d, choice):
        foods = [o[2] for o in d.options if o[0] == "die"]
        if choice[0] != "die" or len(set(foods)) < 2:
            return
        c = self.counts
        need = self._needed_by_others(s, d.player)
        c["die_choices"] += 1
        took = choice[2] in need
        c["die_took_needed"] += took
        # "Avoidable": some option was needed by another player and some option was not.
        if any(f in need for f in foods) and any(f not in need for f in foods):
            c["die_avoidable"] += 1
            c["die_took_needed_avoidable"] += took
