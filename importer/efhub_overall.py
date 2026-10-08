"""Trained max overall, matching the green Max button on eFHUB.

The rating weights, weak-foot term, and point costs are the same ones
eFHUB ships. The button spends training points by position weight per
point, one slider at a time, rather than by the older overall-gain search.
"""

from __future__ import annotations

import math

POSITION_COLUMN = {
    "GK": 0,
    "CB": 1,
    "LB": 2,
    "RB": 3,
    "DMF": 4,
    "CMF": 5,
    "LMF": 6,
    "RMF": 7,
    "AMF": 8,
    "LWF": 9,
    "RWF": 10,
    "SS": 11,
    "CF": 12,
}

# 13 positions x 28 factors. Column 0 is the position's first weight.
WEIGHTS = [
    186, 136, 49, 49, 61, 37, 12, 12, 37, 49, 49, 62, 99,
    0, 14, 61, 61, 61, 98, 98, 98, 171, 159, 159, 173, 210,
    13, 27, 86, 86, 122, 171, 171, 171, 196, 159, 159, 210, 123,
    0, 14, 61, 61, 37, 98, 110, 122, 122, 159, 159, 123, 62,
    0, 0, 37, 37, 24, 49, 73, 61, 73, 86, 86, 86, 37,
    27, 41, 61, 61, 122, 208, 135, 135, 196, 73, 73, 99, 37,
    40, 68, 147, 147, 122, 159, 196, 196, 159, 98, 98, 74, 12,
    0, 27, 24, 24, 37, 73, 86, 86, 184, 159, 159, 284, 358,
    0, 14, 24, 24, 12, 12, 24, 24, 12, 12, 12, 12, 12,
    0, 14, 24, 24, 12, 12, 24, 24, 12, 12, 12, 12, 12,
    0, 55, 24, 24, 61, 24, 12, 12, 24, 24, 24, 25, 62,
    13, 286, 147, 147, 220, 86, 49, 49, 24, 12, 12, 0, 0,
    0, 191, 86, 86, 122, 86, 24, 24, 24, 12, 12, 12, 12,
    0, 82, 37, 37, 98, 37, 12, 12, 12, 12, 12, 12, 12,
    53, 27, 24, 24, 49, 73, 24, 24, 73, 61, 61, 99, 123,
    13, 136, 220, 220, 61, 61, 196, 196, 98, 220, 220, 86, 99,
    40, 150, 184, 184, 61, 86, 159, 159, 86, 159, 159, 99, 123,
    80, 204, 98, 98, 122, 49, 24, 24, 24, 37, 37, 37, 86,
    0, 0, 24, 24, 12, 24, 61, 61, 24, 73, 73, 74, 86,
    133, 109, 37, 37, 37, 12, 12, 12, 12, 24, 24, 37, 62,
    279, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    226, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    226, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    173, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    173, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0,
    0, 68, 196, 196, 196, 196, 147, 147, 86, 49, 49, 49, 37,
    4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4, 4,
    0, 14, 24, 24, 24, 24, 24, 24, 24, 24, 24, 12, 12,
]

STAT_OFFSETS = [
    ("offensiveAwareness", 13),
    ("ballControl", 26),
    ("dribbling", 39),
    ("tightPossession", 52),
    ("lowPass", 65),
    ("loftedPass", 78),
    ("finishing", 91),
    ("setPieceTaking", 104),
    ("curl", 117),
    ("heading", 130),
    ("defensiveAwareness", 143),
    ("ballWinning", 156),
    ("aggression", 169),
    ("kickingPower", 182),
    ("speed", 195),
    ("acceleration", 208),
    ("physicalContact", 221),
    ("balance", 234),
    ("jump", 247),
    ("gkAwareness", 260),
    ("gkReach", 273),
    ("gkCatching", 286),
    ("gkClearing", 299),
    ("gkReflexes", 312),
    ("stamina", 325),
    ("defensiveEngagement", 351),
]

SLIDERS = [
    ("shooting", ("finishing", "setPieceTaking", "curl")),
    ("passing", ("lowPass", "loftedPass")),
    ("dribbling", ("ballControl", "dribbling", "tightPossession")),
    ("dexterity", ("offensiveAwareness", "acceleration", "balance")),
    ("lowerBodyStrength", ("speed", "kickingPower", "stamina")),
    ("aerialStrength", ("heading", "jump", "physicalContact")),
    ("defending", ("defensiveAwareness", "ballWinning", "aggression", "defensiveEngagement")),
    ("gk1", ("gkAwareness", "jump")),
    ("gk2", ("gkClearing", "gkReach")),
    ("gk3", ("gkCatching", "gkReflexes")),
]


def _above_25(value: float) -> int:
    return int(value) - 25 if value > 25 else 0


def _weight(offset: int, column: int) -> int:
    return WEIGHTS[offset + column]


def overall_decimal(position: str, height: int, weak_foot: int, stats: dict) -> float:
    column = POSITION_COLUMN.get((position or "").upper())
    if column is None:
        return 70.0
    total = _weight(0, column) * _above_25((height or 0) - 111)
    for key, offset in STAT_OFFSETS:
        total += _weight(offset, column) * _above_25(stats.get(key) or 0)
    total += _weight(338, column) * _above_25(math.floor(59 * (weak_foot or 0) / 3 + 40))
    raw = (total + 500) / 1000
    return round(max(raw, 40) * 100) / 100


def overall_rating(position: str, height: int, weak_foot: int, stats: dict) -> int:
    column = POSITION_COLUMN.get((position or "").upper())
    if column is None:
        return 70
    total = _weight(0, column) * _above_25((height or 0) - 111)
    for key, offset in STAT_OFFSETS:
        total += _weight(offset, column) * _above_25(stats.get(key) or 0)
    total += _weight(338, column) * _above_25(math.floor(59 * (weak_foot or 0) / 3 + 40))
    rating = math.floor((total + 500) / 1000)
    return 40 if rating < 40 else rating


def _point_cost(level: int) -> int:
    return math.ceil(level / 4)


def _points_for_slider(level: int) -> int:
    return sum(_point_cost(step) for step in range(1, level + 1))


def available_points(level_cap: int) -> int:
    return max(0, (int(level_cap) - 1) * 2)


def apply_progression(stats: dict, sliders: dict[str, int]) -> dict:
    grown = dict(stats)
    for key, affected in SLIDERS:
        amount = sliders.get(key) or 0
        if not amount:
            continue
        for stat in affected:
            grown[stat] = min(99, int(grown.get(stat) or 0) + amount)
    return grown


def max_sliders(stats: dict, position: str, _height: int, _weak_foot: int, points: int) -> dict[str, int]:
    """Spend progression points the way eFHUB's Max button does.

    Each pass locks onto one rank in the weight-per-point list (best, then
    second best, and so on) and buys that slider until it is capped or the
    next level costs more than the points left. Height and weak foot change
    the rating, not which slider gets the next point.
    """
    column = POSITION_COLUMN.get((position or "").upper())
    sliders = {key: 0 for key, _affected in SLIDERS}
    if column is None:
        return sliders
    grown = {key: int(value or 0) for key, value in stats.items()}
    remaining = points
    offsets = {key: offset for key, offset in STAT_OFFSETS}
    for rank in range(len(SLIDERS)):
        if remaining <= 0:
            break
        while remaining > 0:
            scored: list[tuple[float, int]] = []
            for index, (key, affected) in enumerate(SLIDERS):
                if sliders[key] >= 25:
                    scored.append((0.0, index))
                    continue
                weight_sum = 0
                for stat in affected:
                    if grown.get(stat, 0) >= 99:
                        continue
                    offset = offsets.get(stat)
                    if offset is not None:
                        weight_sum += _weight(offset, column)
                if weight_sum == 0:
                    scored.append((0.0, index))
                    continue
                scored.append((weight_sum / _point_cost(sliders[key] + 1), index))
            scored.sort(key=lambda item: item[0], reverse=True)
            if rank >= len(scored) or scored[rank][0] <= 0:
                break
            key, affected = SLIDERS[scored[rank][1]]
            cost = _point_cost(sliders[key] + 1)
            if remaining < cost:
                break
            sliders[key] += 1
            remaining -= cost
            for stat in affected:
                if grown.get(stat, 0) < 99:
                    grown[stat] = grown.get(stat, 0) + 1
    return sliders


def trained_max_overall(detail: dict) -> int | None:
    stats = detail.get("stats") or {}
    if not stats:
        return None
    position = str(detail.get("position") or "")
    if position.upper() not in POSITION_COLUMN:
        return None
    level_cap = detail.get("levelCap")
    if not level_cap:
        return None
    height = int(detail.get("height") or 0)
    weak_foot = int(detail.get("weakFootAccuracy") or 0)
    points = available_points(int(level_cap))
    if points <= 0:
        rating = overall_rating(position, height, weak_foot, stats)
        listed = detail.get("overallRating")
        return int(listed) if listed else rating
    sliders = max_sliders(stats, position, height, weak_foot, points)
    grown = apply_progression(stats, sliders)
    return overall_rating(position, height, weak_foot, grown)
