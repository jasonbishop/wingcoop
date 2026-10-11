"""Experiment runner: grid expansion, paired seeds, tables, logs and the report."""
import pandas as pd
import pytest

from wingsim import runner
from wingsim.analysis import report
from wingsim.analysis.metrics import DecisionTally
from wingsim.engine import api
from wingsim.engine.log import replay

from .helpers import F, feeder, food, fresh, hand, pick, set_turn

EXP = {
    "name": "unit",
    "seeds": {"start": 3, "count": 2},
    "players": [2, 3],
    "conditions": {
        "baseline": {"plugins": {}, "win_condition": "individual"},
        "coop": {"plugins": {"coop_goals": {"penalty": "avg_x_d", "allowed_changes": [0, 1]}, "open_hands": True},
                 "win_condition": "team_total"},
    },
    "agents": {"type": "random"},
    "motivation": [0.0, 1.0],
    "group_policy": ["fixed(2)", "ladder(2,+1,0)"],
    "group_share": [False, True],
    "logging": {"level": "summary", "full_sample": 0.2, "full_if": ["group_fail_round_4", "spread_gt_40"]},
}


def test_grid_expansion():
    cells = runner.expand(EXP)
    base = [c for c in cells if c["condition"] == "baseline"]
    coop = [c for c in cells if c["condition"] == "coop"]
    assert len(base) == 2 * 2                      # players x motivation; no policy or share dimension
    assert len(coop) == 2 * 2 * 2 * 2              # ... x policy x group_share
    assert all(c["policy"] is None and not c["group_share"] and c["plugins"] == {} for c in base)
    assert all(c["open_hands"] for c in cells)     # on by default, in the baseline too
    assert all("open_hands" not in c["plugins"] for c in cells)
    assert {c["win_condition"] for c in coop} == {"team_total"}


def test_open_hands_can_be_switched_off_per_condition():
    exp = dict(EXP, conditions={"closed": {"plugins": {"open_hands": False}}})
    assert not any(c["open_hands"] for c in runner.expand(exp))


@pytest.fixture(scope="module")
def run(tmp_path_factory):
    root = tmp_path_factory.mktemp("exp")
    games, offers, out = runner.run_experiment(EXP, ".", workers=2, out_root=root / "results",
                                               log_root=root / "logs", progress=False)
    return games, offers, out


def test_tables_and_paired_seeds(run):
    games, offers, out = run
    assert len(games) == (4 + 16) * 2
    assert (out / "games.parquet").exists() and (out / "offers.parquet").exists()
    # Every cell is run on the same list of seeds.
    for _, g in games.groupby(["condition", "players", "w", "policy", "group_share"]):
        assert sorted(g.seed) == [3, 4]
    # Team total = sum of individual scores + group score.
    for row in games.itertuples():
        totals = [getattr(row, f"p{j}_total") for j in range(row.players)]
        assert row.team_total == pytest.approx(sum(totals) + row.group_score)
        assert row.individual_mean == pytest.approx(sum(totals) / row.players)
        assert row.spread == max(totals) - min(totals)
        if row.players == 2:
            assert pd.isna(row.p2_total) and pd.isna(row.r1_c2)
    base = games[games.condition == "baseline"]
    coop = games[games.condition == "coop"]
    assert (base.group_score == 0).all() and (base.policy == "none").all()
    assert coop.r1_d.eq(2).all()                   # both policies start at difficulty 2
    assert (coop.p0_goals == 0).all() and (base[[f"p{j}_goals" for j in range(2)]].sum().sum() > 0)
    # Paired starts: with the same seed, baseline and co-op deal the same four goals.
    m = coop.merge(base, on=["players", "seed", "w"], suffixes=("", "_b"))
    assert len(m) == len(coop) and (m.r1_goal == m.r1_goal_b).all() and (m.r4_goal == m.r4_goal_b).all()
    assert {"offered", "chosen", "shares_benefit", "cost", "vp", "where"} <= set(offers.columns)
    assert (offers.chosen <= offers.offered).all()


def test_full_logs_are_written_and_replay(run):
    games, offers, out = run
    logged = games[games.log.notna()]
    assert len(logged) > 0 and set(logged.log_reason) <= {"sample", "group_fail_round_4", "spread_gt_40"}
    flagged = games[(games.r4_success == False) | (games.spread > 40)]      # noqa: E712
    assert flagged.log.notna().all()               # unusual games are always kept
    for path in logged.log.head(3):
        row = logged[logged.log == path].iloc[0]
        final = replay(path)
        assert api.final_scores(final)["team_total"] == pytest.approx(row.team_total)


def test_report_is_generated(run):
    games, offers, out = run
    path = report.write_report(out)
    text = path.read_text()
    for heading in ("## Outcomes", "paired by seed", "## Goal success", "## Weakest link", "## Difficulty choice",
                    "## Shared-benefit birds", "## Denial", "## Sanity checks"):
        assert heading in text
    assert (out / "report" / "paired_team_total.png").stat().st_size > 5000
    m = report.paired(games)
    assert len(m) == len(games[games.condition == "coop"])
    mean, half = report.ci95([1.0, 2.0, 3.0, 4.0])
    assert mean == 2.5 and half == pytest.approx(1.96 * 1.2909944 / 2)


def test_decision_tally_pick_rate_and_denial(db):
    s = fresh(2)
    shared, = pick(lambda b: b.name == "Osprey")
    other, = pick(lambda b: b.name == "Mallard")
    a, b = hand(s, 0, shared, other)
    s.players[0].food = [3, 3, 3, 3, 3]
    set_turn(s, 0)
    tally = DecisionTally(db)
    d = api.pending_decision(s)
    choice = next(o for o in d.options if o[0] == "play" and o[1] == a)
    tally.record(s, d, choice)
    by_tag = {k[1]: v for k, v in tally.offers.items()}
    assert by_tag[True] == [1, 1] and by_tag[False] == [1, 0] and tally.counts["act_play"] == 1
    # Denial: player 1 holds a bird that needs a fish they lack; player 0 takes the fish.
    needs_fish, = pick(lambda x: x.cost[F["fish"]] >= 1 and not x.either, exclude=[shared, other])
    hand(s, 1, needs_fish)
    food(s, 1, fish=0)
    feeder(s, "fish", "fruit")
    s.players[0].hand = []
    set_turn(s, 0)
    api.apply_in_place(s, ("food",))
    d = api.pending_decision(s)
    tally.record(s, d, ("die", F["fish"], F["fish"]))
    assert tally.counts["die_took_needed"] == 1 and tally.counts["die_took_needed_avoidable"] == 1
    tally.record(s, d, ("die", F["fruit"], F["fruit"]))
    assert tally.counts["die_choices"] == 2 and tally.counts["die_took_needed"] == 1
