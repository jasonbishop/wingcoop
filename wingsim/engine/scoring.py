"""Goal counts, bonus cards and score breakdowns."""


def goal_count(s, j, goal):
    """A player's raw count for a round goal. Ruling 20190921: star nests count as every nest type."""
    board = s.players[j].board
    kind = goal.kind
    prm = goal.param
    if kind == "birds_in_habitat":
        return len(board[prm])
    if kind == "eggs_in_habitat":
        return sum(x[1] for x in board[prm])
    if kind == "total_birds":
        return len(board[0]) + len(board[1]) + len(board[2])
    if kind == "egg_sets":
        return min(sum(x[1] for x in row) for row in board)
    birds = s.cfg.db.birds
    n = 0
    for row in board:
        for x in row:
            nest = birds[x[0]].nest
            if x[1] and (nest == prm or nest == "wild"):
                n += x[1] if kind == "eggs_in_nest" else 1
    return n


def current_goal_counts(s):
    """Every player's count for the current round's goal, or None once the game is over."""
    if s.round > 4:
        return None
    goal = s.cfg.db.goals[s.goals[s.round - 1]]
    return tuple(goal_count(s, j, goal) for j in range(len(s.players)))


def score_goal_counts(s, counts):
    """Round-end scoring for the given counts: (points per player, group score change, info).

    The base game scores the blue side of the goal board: 1 point per item, at
    most 5. A plugin may replace this.
    """
    for pg in s.cfg.scoring_plugins:
        r = pg.round_end_scoring(s, counts)
        if r is not None:
            return r
    return [float(c if c < 5 else 5) for c in counts], 0.0, None


def bonus_count(s, j, card):
    pl = s.players[j]
    board = pl.board
    kind = card.count
    if kind == "column":
        birds = s.cfg.db.birds
        cid = card.id
        n = 0
        for row in board:
            for x in row:
                if cid in birds[x[0]].bonus:
                    n += 1
        return n
    if kind == "birds_with_4_eggs":
        return sum(1 for row in board for x in row if x[1] >= 4)
    if kind == "birds_with_egg":
        return sum(1 for row in board for x in row if x[1] >= 1)
    if kind == "birds_in_smallest_habitat":
        return min(len(board[0]), len(board[1]), len(board[2]))
    if kind == "cards_in_hand":
        return len(pl.hand)
    raise ValueError(kind)


def player_breakdown(s, j):
    d = s.cfg.db
    birds = d.birds
    vp = eggs = cached = tucked = 0
    for row in s.players[j].board:
        for x in row:
            vp += birds[x[0]].vp
            eggs += x[1]
            cached += x[2]
            tucked += x[3]
    bonus = 0
    for b in s.players[j].bonus:
        card = d.bonus[b]
        bonus += card.points(bonus_count(s, j, card))
    goals = s.goal_points[j]
    return {"birds": vp, "bonus": bonus, "eggs": eggs, "cached": cached, "tucked": tucked, "goals": goals,
            "total": vp + bonus + eggs + cached + tucked + goals}


def breakdown(s):
    """Individual scores by category, the group score and the team total, for the state as it stands."""
    players = [player_breakdown(s, j) for j in range(len(s.players))]
    result = {"players": players, "group": s.group_score}
    for pg in s.cfg.final_plugins:
        pg.final_scoring(s, result)
    result["team_total"] = sum(p["total"] for p in result["players"]) + result["group"]
    return result


def totals(s):
    """Individual totals only (fast path used by agents)."""
    if s.cfg.final_plugins:
        return [p["total"] for p in breakdown(s)["players"]]
    d = s.cfg.db
    birds = d.birds
    out = []
    for j, pl in enumerate(s.players):
        t = s.goal_points[j]
        for row in pl.board:
            for x in row:
                t += birds[x[0]].vp + x[1] + x[2] + x[3]
        for b in pl.bonus:
            card = d.bonus[b]
            t += card.points(bonus_count(s, j, card))
        out.append(t)
    return out


def final_scores(s):
    """Final result: the breakdown plus winners. Ties are broken by leftover food."""
    result = breakdown(s)
    best = max(p["total"] for p in result["players"])
    tied = [j for j, p in enumerate(result["players"]) if p["total"] == best]
    most_food = max(sum(s.players[j].food) for j in tied)
    result["winners"] = [j for j in tied if sum(s.players[j].food) == most_food]
    result["leftover_food"] = [sum(pl.food) for pl in s.players]
    return result
