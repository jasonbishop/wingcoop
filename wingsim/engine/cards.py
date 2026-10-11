"""Card database: the core birds, bonus cards and goals, loaded once per process."""
import json
import pathlib

DATA = pathlib.Path(__file__).parent.parent / "data"

FOODS = ("invertebrate", "seed", "fish", "fruit", "rodent")
HABITATS = ("forest", "grassland", "wetland")
INVERTEBRATE, SEED, FISH, FRUIT, RODENT = range(5)
# Die faces 0-4 are the five foods; face 5 is the invertebrate/seed face.
DIE_FACES = 6
FACE_NAMES = FOODS + ("invertebrate/seed",)
ALL_FOODS = (0, 1, 2, 3, 4)


class Bird:
    __slots__ = ("id", "name", "color", "vp", "nest", "egg_limit", "wingspan", "habitats", "cost", "wild",
                 "either", "total_cost", "predator", "flocking", "bonus", "text", "spec", "timing", "steps",
                 "trigger", "rulings")


class BonusCard:
    __slots__ = ("id", "name", "condition", "per", "tiers", "count")

    def points(self, n):
        if self.per is not None:
            return self.per * n
        pts = 0
        for lower, value in self.tiers:
            if n >= lower:
                pts = value
        return pts


class Goal:
    __slots__ = ("id", "text", "kind", "param", "tile")


def _compile_step(step):
    """Turn a JSON effect step into the form the engine runs (names -> indices)."""
    s = dict(step)
    food = s.get("food")
    if isinstance(food, list):
        s["food"] = tuple(FOODS.index(f) for f in food)
    elif food == "any":
        s["food"] = None if s.get("from") == "feeder" or s["op"] == "discard_to_gain" else ALL_FOODS
    elif food == "any_other":
        s["food"] = ALL_FOODS
        s["other"] = True
    elif isinstance(food, str):
        s["food"] = FOODS.index(food)
    if "habitat" in s and s["habitat"] != "this":
        s["habitat"] = HABITATS.index(s["habitat"])
    if "cost" in s:
        cost = dict(s["cost"])
        if isinstance(cost.get("food"), list):
            cost["food"] = tuple(FOODS.index(f) for f in cost["food"])
        elif cost.get("food") == "any":
            cost["food"] = None
        s["cost"] = cost
    if "then" in s:
        s["then"] = tuple(_compile_step(t) for t in s["then"])
    if "if" in s and isinstance(s["if"], dict):
        s["if"] = _compile_step(s["if"])
    return s


class CardDB:
    def __init__(self):
        cards = json.loads((DATA / "cards.json").read_text())
        effects = json.loads((DATA / "effects.json").read_text())
        self.commit = cards["commit"]
        self.birds = {}
        for b in cards["birds"]:
            bird = Bird()
            for k in ("id", "name", "color", "vp", "nest", "egg_limit", "wingspan", "wild", "either",
                      "total_cost", "predator", "flocking", "text"):
                setattr(bird, k, b[k])
            bird.habitats = tuple(b["habitats"])
            bird.cost = tuple(b["cost"])
            bird.bonus = frozenset(b["bonus"])
            bird.rulings = tuple(b["rulings"])
            e = effects.get(str(b["id"]))
            bird.spec = e["spec"] if e else None
            bird.timing = e["spec"]["timing"] if e else None
            bird.steps = tuple(_compile_step(s) for s in e["spec"]["steps"]) if e else ()
            trig = dict(e["spec"]["trigger"]) if e and "trigger" in e["spec"] else None
            if trig and "habitat" in trig:
                trig["habitat"] = HABITATS.index(trig["habitat"])
            if trig and "food" in trig:
                trig["food"] = FOODS.index(trig["food"])
            bird.trigger = trig
            self.birds[bird.id] = bird
        self.bird_ids = tuple(sorted(self.birds))
        self.by_name = {b.name: b for b in self.birds.values()}
        self.bonus = {}
        for b in cards["bonus"]:
            card = BonusCard()
            card.id, card.name, card.condition = b["id"], b["name"], b["condition"]
            card.per = b.get("per")
            card.tiers = tuple(tuple(t) for t in b["tiers"]) if "tiers" in b else None
            card.count = b["count"]
            self.bonus[card.id] = card
        self.bonus_ids = tuple(sorted(self.bonus))
        self.goals = {}
        for g in cards["goals"]:
            goal = Goal()
            goal.id, goal.text, goal.kind, goal.tile = g["id"], g["text"], g["kind"], g["tile"]
            p = g["param"]
            goal.param = HABITATS.index(p) if p in HABITATS else p
            self.goals[goal.id] = goal
        self.tiles = tuple(tuple(t) for t in cards["tiles"])


_DB = None


def db():
    global _DB
    if _DB is None:
        _DB = CardDB()
    return _DB
