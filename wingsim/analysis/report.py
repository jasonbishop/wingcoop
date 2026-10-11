"""Generate the experiment report: Markdown plus charts.

Usage: python -m wingsim.analysis.report results/<experiment>

Conditions are compared on paired seeds: every co-op game is matched with the
baseline game that had the same seed, player count and motivation, so each
difference is between two games that started from the same shuffle.
"""
import json
import pathlib
import sys

import numpy as np
import pandas as pd

# Chart colours: the first three categorical slots of the validated light palette, on its surface.
SURFACE = "#fcfcfb"
INK = "#0b0b0b"
INK_2 = "#52514e"
GRID = "#e6e5e1"
SERIES = ("#2a78d6", "#eb6834", "#1baf7a")


def md_table(df, digits=2):
    def fmt(x):
        if isinstance(x, (float, np.floating)):
            return "" if np.isnan(x) else f"{x:.{digits}f}"
        if isinstance(x, (bool, np.bool_)):
            return "yes" if x else "no"
        return str(x)

    cols = [str(c) for c in df.columns]
    lines = ["| " + " | ".join(cols) + " |", "| " + " | ".join("---" for _ in cols) + " |"]
    for row in df.itertuples(index=False):
        lines.append("| " + " | ".join(fmt(x) for x in row) + " |")
    return "\n".join(lines)


def ci95(x):
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 2:
        return float(x.mean()) if n else float("nan"), float("nan")
    return float(x.mean()), float(1.96 * x.std(ddof=1) / np.sqrt(n))


def paired(games, base="baseline"):
    """One row per co-op game joined to its baseline game (same seed, players and w)."""
    b = games[games.condition == base][["players", "w", "seed", "team_total", "individual_mean", "spread",
                                        "score_sd"]]
    v = games[games.condition != base]
    m = v.merge(b, on=["players", "w", "seed"], suffixes=("", "_base"))
    for col in ("team_total", "individual_mean", "spread", "score_sd"):
        m["d_" + col] = m[col] - m[col + "_base"]
    return m


def paired_summary(m, by):
    rows = []
    for key, g in m.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by, key))
        row["games"] = len(g)
        for col, label in (("d_team_total", "team total"), ("d_individual_mean", "individual mean"),
                           ("d_spread", "spread")):
            mean, half = ci95(g[col])
            row[f"{label} diff"] = mean
            row[f"{label} ±95%"] = half
        rows.append(row)
    return pd.DataFrame(rows)


def success_table(games):
    rows = []
    v = games[games.policy != "none"]
    for r in (1, 2, 3, 4):
        part = v[["players", f"r{r}_d", f"r{r}_success"]].dropna()
        part.columns = ["players", "d", "success"]
        part["round"] = r
        rows.append(part)
    if not rows:
        return pd.DataFrame()
    return pd.concat(rows)


def weakest_link(games):
    v = games[games.policy != "none"]
    rows = []
    for (players, w), g in v.groupby(["players", "w"]):
        fails = one = total_short = 0
        repeat_games = repeat_same = 0
        for row in g.itertuples(index=False):
            missed_sets = []
            for r in (1, 2, 3, 4):
                if getattr(row, f"r{r}_success") is False or getattr(row, f"r{r}_success") == 0:
                    missed = [x for x in str(getattr(row, f"r{r}_missed") or "").split(";") if x]
                    fails += 1
                    one += len(missed) == 1
                    total_short += getattr(row, f"r{r}_shortfall") or 0
                    missed_sets.append(set(missed))
            if len(missed_sets) >= 2:
                repeat_games += 1
                repeat_same += bool(set.intersection(*missed_sets))
        rows.append({"players": players, "w": w, "failed rounds": fails,
                     "one player missed": one / fails if fails else np.nan,
                     "mean shortfall of the worst player": total_short / fails if fails else np.nan,
                     "games with 2+ failures": repeat_games,
                     "same player missed every time": repeat_same / repeat_games if repeat_games else np.nan})
    return pd.DataFrame(rows)


def pick_rates(offers, where="play"):
    """Pick rate for shared-benefit birds vs others, overall and matched on cost and points."""
    o = offers[offers["where"] == where]
    rows = []
    for (cond, w), g in o.groupby(["condition", "w"]):
        sb = g[g.shares_benefit]
        other = g[~g.shares_benefit]
        if sb.offered.sum() == 0 or other.offered.sum() == 0:
            continue
        # Matched comparison: weight the other birds' strata (cost, points) like the shared birds' offers.
        strata = sb.groupby(["cost", "vp"]).offered.sum()
        other_rate = other.groupby(["cost", "vp"])[["offered", "chosen"]].sum()
        num = den = 0.0
        for key, weight in strata.items():
            if key in other_rate.index and other_rate.loc[key, "offered"] > 0:
                num += weight * other_rate.loc[key, "chosen"] / other_rate.loc[key, "offered"]
                den += weight
        rows.append({"condition": cond, "w": w, "shared offers": int(sb.offered.sum()),
                     "shared pick rate": sb.chosen.sum() / sb.offered.sum(),
                     "other pick rate": other.chosen.sum() / other.offered.sum(),
                     "other, matched on cost and points": num / den if den else np.nan})
    out = pd.DataFrame(rows)
    if len(out):
        out["shared minus matched"] = out["shared pick rate"] - out["other, matched on cost and points"]
    return out


def ratio_table(games, by, pairs):
    rows = []
    for key, g in games.groupby(by):
        key = key if isinstance(key, tuple) else (key,)
        row = dict(zip(by, key))
        for label, num, den in pairs:
            if num in g and den in g:
                d = g[den].sum()
                row[label] = g[num].sum() / d if d else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def seat_advantage(games):
    rows = []
    for (cond, players), g in games.groupby(["condition", "players"]):
        first, rest = [], []
        for row in g.itertuples(index=False):
            scores = [getattr(row, f"p{j}_total") for j in range(players)]
            first.append(scores[int(row.first_player)])
            rest.append((sum(scores) - scores[int(row.first_player)]) / (players - 1))
        mean, half = ci95(np.array(first) - np.array(rest))
        rows.append({"condition": cond, "players": players, "first player minus others": mean, "±95%": half})
    return pd.DataFrame(rows)


# ---------------------------------------------------------------- charts

def _axes(ax, title):
    ax.set_facecolor(SURFACE)
    ax.set_title(title, loc="left", fontsize=10, color=INK, pad=8)
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.spines["bottom"].set_color(GRID)
    ax.tick_params(colors=INK_2, labelsize=8, length=0)
    ax.grid(axis="y", color=GRID, linewidth=1)
    ax.set_axisbelow(True)


def _figure(n, width=3.3, height=3.0):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig, axes = plt.subplots(1, n, figsize=(width * n, height), sharey=True, squeeze=False)
    fig.patch.set_facecolor(SURFACE)
    return plt, fig, list(axes[0])


def chart_paired(m, path, policy):
    """Co-op minus baseline team total, by player count; one panel per motivation, one series per share rule."""
    part = m[m.policy == policy]
    ws = sorted(part.w.unique())
    plt, fig, axes = _figure(len(ws))
    shares = sorted(part.group_share.unique())
    labels = {False: "group score not counted as own", True: "equal share counted as own"}
    for ax, w in zip(axes, ws):
        _axes(ax, f"w = {w:g}")
        ax.axhline(0, color=INK_2, linewidth=1)
        for i, share in enumerate(shares):
            g = part[(part.w == w) & (part.group_share == share)]
            xs, ys, es = [], [], []
            for players, gg in g.groupby("players"):
                mean, half = ci95(gg.d_team_total)
                xs.append(players + (i - (len(shares) - 1) / 2) * 0.16)
                ys.append(mean)
                es.append(0 if np.isnan(half) else half)
            ax.errorbar(xs, ys, yerr=es, fmt="none", ecolor=SERIES[i], elinewidth=2, capsize=0)
            ax.plot(xs, ys, "o", color=SERIES[i], markersize=8, markeredgecolor=SURFACE, markeredgewidth=2,
                    label=labels[share])
        ax.set_xticks(sorted(part.players.unique()))
        ax.set_xlabel("players", fontsize=8, color=INK_2)
    axes[0].set_ylabel("team total: co-op minus baseline", fontsize=8, color=INK_2)
    if len(shares) > 1:
        fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2, frameon=False, fontsize=8,
                   labelcolor=INK_2)
    fig.suptitle(f"Change in team total under co-op goals (policy {policy}; bars are 95% intervals)",
                 x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0.07 if len(shares) > 1 else 0, 1, 0.93))
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def chart_success(succ, path):
    """Share of rounds in which every player reached the difficulty, by difficulty; one panel per player count."""
    players = sorted(succ.players.unique())
    plt, fig, axes = _figure(len(players), width=2.6)
    for ax, n in zip(axes, players):
        _axes(ax, f"{n} players")
        g = succ[succ.players == n].groupby("d").success.agg(["mean", "count"])
        ax.bar(g.index, g["mean"], width=0.45, color=SERIES[0])
        for d, row in g.iterrows():
            ax.text(d, row["mean"] + 0.02, f"{row['mean']:.0%}", ha="center", va="bottom", fontsize=8, color=INK_2)
        ax.set_xticks([1, 2, 3, 4, 5])
        ax.set_ylim(0, 1.12)
        ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
        ax.set_yticklabels(["0%", "25%", "50%", "75%", "100%"])
        ax.set_xlabel("difficulty", fontsize=8, color=INK_2)
    fig.suptitle("Rounds in which every player met the difficulty", x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.92))
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def chart_policy(games, path):
    """Mean group score by difficulty policy; one panel per player count."""
    v = games[games.policy != "none"]
    players = sorted(v.players.unique())
    policies = sorted(v.policy.unique())
    plt, fig, axes = _figure(len(players), width=2.9, height=0.5 + 0.42 * len(policies) + 1.0)
    every = [v[(v.players == n) & (v.policy == p)].group_score.mean() for n in players for p in policies]
    span = max(1.0, max(abs(x) for x in every))
    lo, hi = min(0, min(every)) - 0.3 * span, max(0, max(every)) + 0.3 * span   # one scale for every panel
    for ax, n in zip(axes, players):
        _axes(ax, f"{n} players")
        ax.grid(axis="y", visible=False)
        ax.grid(axis="x", color=GRID, linewidth=1)
        means = [v[(v.players == n) & (v.policy == p)].group_score.mean() for p in policies]
        ax.barh(range(len(policies)), means, height=0.42, color=SERIES[0])
        ax.axvline(0, color=INK_2, linewidth=1)
        for i, x in enumerate(means):
            ax.text(x + (0.04 * span if x >= 0 else -0.04 * span), i, f"{x:.1f}", va="center",
                    ha="left" if x >= 0 else "right", fontsize=8, color=INK_2)
        ax.set_xlim(lo, hi)
        ax.set_yticks(range(len(policies)))
        ax.set_yticklabels(policies)
        ax.invert_yaxis()
        ax.set_xlabel("mean group score", fontsize=8, color=INK_2)
    fig.suptitle("Group score by difficulty policy (all motivations pooled)", x=0.01, ha="left", fontsize=11,
                 color=INK)
    fig.tight_layout(rect=(0, 0, 1, 0.9))
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)


def chart_pick(rates, path):
    """Pick rate of shared-benefit birds vs matched other birds, by motivation; one panel per condition."""
    conds = list(rates.condition.unique())
    plt, fig, axes = _figure(len(conds), width=3.6)
    for ax, cond in zip(axes, conds):
        _axes(ax, cond)
        g = rates[rates.condition == cond].sort_values("w")
        ax.plot(g.w, g["shared pick rate"], "-o", color=SERIES[0], linewidth=2, markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, label="shared-benefit birds")
        ax.plot(g.w, g["other, matched on cost and points"], "-o", color=SERIES[1], linewidth=2, markersize=8,
                markeredgecolor=SURFACE, markeredgewidth=2, label="other birds, matched on cost and points")
        ax.set_xticks(sorted(rates.w.unique()))
        ax.set_xlabel("motivation w (0 selfish, 1 team-minded)", fontsize=8, color=INK_2)
        ax.yaxis.set_major_formatter(lambda x, _: f"{x:.0%}")
        ax.set_ylim(bottom=0)
    axes[0].set_ylabel("played when affordable and a slot was free", fontsize=8, color=INK_2)
    fig.legend(*axes[0].get_legend_handles_labels(), loc="lower center", ncol=2, frameon=False, fontsize=8,
               labelcolor=INK_2)
    fig.suptitle("How often a playable bird was played", x=0.01, ha="left", fontsize=11, color=INK)
    fig.tight_layout(rect=(0, 0.08, 1, 0.92))
    fig.savefig(path, dpi=140, facecolor=SURFACE)
    plt.close(fig)


# ---------------------------------------------------------------- report

def write_report(out_dir):
    out_dir = pathlib.Path(out_dir)
    games = pd.read_parquet(out_dir / "games.parquet")
    offers = pd.read_parquet(out_dir / "offers.parquet")
    meta = json.loads((out_dir / "experiment.json").read_text()) if (out_dir / "experiment.json").exists() else {}
    charts = out_dir / "report"
    charts.mkdir(exist_ok=True)
    name = games.experiment.iloc[0]
    has_coop = (games.policy != "none").any()
    L = [f"# {name}: experiment report", ""]
    L += [f"{len(games):,} games; engine `{meta.get('engine_git', 'unknown')}`; "
          f"{games.seed.nunique()} seeds per cell at most; agents: {', '.join(sorted(games.agent.unique()))}.", ""]
    cells = games.groupby(["condition", "players", "w", "policy", "group_share"]).size().reset_index(name="games")
    L += [f"The grid has {len(cells)} cells. Every co-op game is compared with the baseline game on the same "
          "seed, player count and motivation. `group_share` says whether an equal share of the group score "
          "counts as part of a player's own score in the bots' objective.", ""]

    L += ["## Outcomes", "", "Means per cell. Individual mean and spread exclude the group score; "
          "team total includes it.", ""]
    summary = games.groupby(["condition", "policy", "group_share", "players", "w"]).agg(
        games=("seed", "size"), team_total=("team_total", "mean"), individual_mean=("individual_mean", "mean"),
        spread=("spread", "mean"), score_sd=("score_sd", "mean"), group_score=("group_score", "mean"),
        rounds_failed=("rounds_failed", "mean")).reset_index()
    L += [md_table(summary), ""]

    if has_coop:
        m = paired(games)
        if len(m):
            L += ["### Co-op minus baseline, paired by seed", "",
                  "Each difference is a co-op game minus the baseline game with the same seed, player count and "
                  "motivation. An interval that excludes zero is a difference the seeds can resolve.", ""]
            L += [md_table(paired_summary(m, ["policy", "group_share", "players", "w"])), ""]
            policy = "fixed(2)" if "fixed(2)" in set(m.policy) else sorted(m.policy.unique())[0]
            chart_paired(m, charts / "paired_team_total.png", policy)
            L += [f"![Change in team total under co-op goals](report/paired_team_total.png)", ""]

        succ = success_table(games)
        L += ["## Goal success by round and difficulty", "",
              "Share of rounds in which every player's capped count reached the difficulty.", ""]
        by_d = succ.groupby(["players", "d"]).success.agg(rate="mean", rounds="count").reset_index()
        L += [md_table(by_d), ""]
        by_r = succ.groupby(["players", "round"]).success.agg(rate="mean", rounds="count").reset_index()
        L += [md_table(by_r), ""]
        chart_success(succ, charts / "goal_success.png")
        L += ["![Goal success by difficulty](report/goal_success.png)", ""]

        L += ["## Weakest link", "",
              "For each failed round: how often exactly one player missed, how far the worst player fell short, "
              "and, in games with two or more failed rounds, how often one player missed in all of them.", ""]
        L += [md_table(weakest_link(games)), ""]

        L += ["## Difficulty choice", "", "Mean group score by policy, player count, motivation and share rule.", ""]
        v = games[games.policy != "none"]
        L += [md_table(v.groupby(["policy", "group_share", "players", "w"]).agg(
            games=("seed", "size"), group_score=("group_score", "mean"), team_total=("team_total", "mean"),
            rounds_failed=("rounds_failed", "mean")).reset_index()), ""]
        paths = v.assign(path=v[["r1_d", "r2_d", "r3_d", "r4_d"]].astype(int).astype(str).agg("-".join, axis=1))
        top = (paths.groupby(["policy", "path"]).size().reset_index(name="games")
               .sort_values(["policy", "games"], ascending=[True, False]).groupby("policy").head(3))
        L += ["Most common difficulty paths (rounds 1 to 4):", "", md_table(top), ""]
        chart_policy(games, charts / "policy_group_score.png")
        L += ["![Group score by difficulty policy](report/policy_group_score.png)", ""]

    L += ["## Shared-benefit birds", "",
          "Pick rate when available: among \"play a bird\" decisions, each bird that was affordable and had a "
          "slot counts as one offer, and as chosen if it was the bird played. \"Matched\" re-weights the other "
          "birds to the same mix of food cost and points as the shared-benefit birds.", ""]
    rates = pick_rates(offers, "play")
    if len(rates):
        L += [md_table(rates, 3), ""]
        chart_pick(rates, charts / "pick_rate.png")
        L += ["![How often a playable bird was played](report/pick_rate.png)", ""]
    tray = pick_rates(offers, "tray")
    if len(tray):
        L += ["The same for taking a face-up bird from the tray (an offer is a tray card on show when a card "
              "was drawn):", "", md_table(tray, 3), ""]
    use = ratio_table(games, ["condition", "w"], [
        ("shared brown powers used", "brown_shared_used", "brown_shared_offered"),
        ("other brown powers used", "brown_other_used", "brown_other_offered")])
    L += ["How often an activated row's brown power was used rather than skipped:", "", md_table(use, 3), ""]

    L += ["## Denial", "",
          "When a player chose a birdfeeder die and had at least two food types to choose from: how often the "
          "food taken was one another player lacked for a bird in their hand. \"Avoidable\" counts only "
          "choices where some option was needed by another player and some option was not.", ""]
    L += [md_table(ratio_table(games, ["condition", "w"], [
        ("took a needed food", "die_took_needed", "die_choices"),
        ("took a needed food when avoidable", "die_took_needed_avoidable", "die_avoidable")]), 3), ""]
    L += ["Tray-card denial and the help action are not measured in this run.", ""]

    L += ["## Sanity checks", "", "First-player advantage (the round-1 first player's score minus the mean of "
          "the others):", "", md_table(seat_advantage(games)), ""]
    acts = [c for c in ("act_play", "act_food", "act_eggs", "act_cards") if c in games]
    mix = games.groupby(["condition", "players"])[acts].sum()
    mix = mix.div(mix.sum(axis=1), axis=0).reset_index()
    mix.columns = [c.replace("act_", "") for c in mix.columns]
    L += ["Action mix (share of turns):", "", md_table(mix), ""]
    cats = ["birds", "bonus", "eggs", "cached", "tucked", "goals"]
    rows = []
    for (cond, players), g in games.groupby(["condition", "players"]):
        row = {"condition": cond, "players": players}
        for cat in cats:
            row[cat] = np.mean([g[f"p{j}_{cat}"].mean() for j in range(players)])
        row["total"] = g.individual_mean.mean()
        rows.append(row)
    L += ["Mean individual score by category:", "", md_table(pd.DataFrame(rows), 1), ""]
    length = games.groupby(["condition", "players"]).agg(decisions=("decisions", "mean"),
                                                         seconds=("seconds", "mean")).reset_index()
    L += ["Game length (every player takes 26 turns; decisions and run time per game):", "",
          md_table(length), ""]
    logged = games.log.notna().sum()
    L += [f"Full replay logs were kept for {logged} games "
          f"({(games.log_reason == 'sample').sum()} sampled, {logged - (games.log_reason == 'sample').sum()} "
          "flagged as unusual).", ""]
    path = out_dir / "report.md"
    path.write_text("\n".join(L))
    return path


if __name__ == "__main__":
    print(write_report(sys.argv[1]))
