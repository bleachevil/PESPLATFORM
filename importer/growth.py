"""Level caps and stat growth from base OVR to maxed overall."""

from __future__ import annotations

from importer.fields import ABILITIES, ABILITY_KEYS

STAT_CAP = 99

MAX_LEVEL_BY_TYPE = {
    "standard": 25,
    "featured": 30,
    "highlight": 30,
    "trending": 30,
    "epic": 35,
    "legendary": 35,
    "big time": 35,
    "bigtime": 35,
}

OVR_GAIN_BY_TYPE = {
    "standard": 8,
    "featured": 12,
    "highlight": 12,
    "trending": 11,
    "epic": 15,
    "legendary": 16,
    "big time": 16,
    "bigtime": 16,
}

POS_WEIGHTS = {
    "GK": {
        "gk_awareness": 1.0, "gk_reflexes": 0.98, "gk_reach": 0.94, "gk_parrying": 0.92, "gk_catching": 0.9,
        "jumping": 0.82, "physical_contact": 0.8, "kicking_power": 0.78,
    },
    "CB": {
        "defensive_awareness": 1.0, "tackling": 0.96, "physical_contact": 0.94, "heading": 0.92,
        "aggression": 0.9, "jumping": 0.88, "defensive_engagement": 0.9, "low_pass": 0.78,
    },
    "LB": {
        "speed": 0.96, "stamina": 0.94, "defensive_awareness": 0.9, "tackling": 0.88, "lofted_pass": 0.86,
        "acceleration": 0.92, "defensive_engagement": 0.86, "crossing": 0.8,
    },
    "RB": {
        "speed": 0.96, "stamina": 0.94, "defensive_awareness": 0.9, "tackling": 0.88, "lofted_pass": 0.86,
        "acceleration": 0.92, "defensive_engagement": 0.86,
    },
    "DMF": {
        "defensive_awareness": 0.96, "low_pass": 0.94, "ball_control": 0.88, "stamina": 0.9,
        "aggression": 0.88, "tackling": 0.9, "lofted_pass": 0.86, "defensive_engagement": 0.92,
    },
    "CMF": {
        "low_pass": 0.98, "ball_control": 0.94, "stamina": 0.92, "lofted_pass": 0.9,
        "dribbling": 0.84, "defensive_engagement": 0.82, "offensive_awareness": 0.8,
    },
    "LMF": {"speed": 0.96, "dribbling": 0.94, "stamina": 0.9, "acceleration": 0.94, "lofted_pass": 0.86, "curl": 0.82},
    "RMF": {"speed": 0.96, "dribbling": 0.94, "stamina": 0.9, "acceleration": 0.94, "lofted_pass": 0.86, "curl": 0.82},
    "AMF": {
        "ball_control": 0.98, "offensive_awareness": 0.94, "low_pass": 0.94, "dribbling": 0.92,
        "finishing": 0.84, "tight_possession": 0.9, "curl": 0.86,
    },
    "LWF": {
        "dribbling": 0.98, "speed": 0.96, "acceleration": 0.96, "offensive_awareness": 0.9,
        "finishing": 0.86, "tight_possession": 0.88, "curl": 0.84,
    },
    "RWF": {
        "dribbling": 0.98, "speed": 0.96, "acceleration": 0.96, "offensive_awareness": 0.9,
        "finishing": 0.86, "tight_possession": 0.88, "curl": 0.84,
    },
    "SS": {
        "offensive_awareness": 0.96, "finishing": 0.94, "ball_control": 0.9, "dribbling": 0.9,
        "kicking_power": 0.88, "acceleration": 0.86,
    },
    "CF": {
        "finishing": 1.0, "offensive_awareness": 0.96, "kicking_power": 0.9, "heading": 0.86,
        "speed": 0.84, "physical_contact": 0.82, "ball_control": 0.84,
    },
}


def _card_key(card_type: str) -> str:
    return (card_type or "standard").strip().lower()


def default_level() -> int:
    return 1


def default_max_level(mode: str, card_type: str) -> int:
    if (mode or "") == "authentic":
        return 1
    return MAX_LEVEL_BY_TYPE.get(_card_key(card_type), 25)


def default_max_overall(mode: str, card_type: str, overall: int) -> int:
    overall = int(overall or 0)
    if (mode or "") == "authentic":
        return overall
    return overall + OVR_GAIN_BY_TYPE.get(_card_key(card_type), 8)


def _weight(position: str, key: str) -> float:
    pos = (position or "CF").upper()
    if pos == "GK":
        if key.startswith("gk_") or key in {"jumping", "physical_contact", "kicking_power"}:
            return POS_WEIGHTS["GK"].get(key, 0.55)
        return 0.0
    if key.startswith("gk_"):
        return 0.0
    return POS_WEIGHTS.get(pos, {}).get(key, 0.32)


def grown_stat(current: int, position: str, key: str, overall: int, max_overall: int) -> int:
    current = int(current or 0)
    delta = max(0, int(max_overall or 0) - int(overall or 0))
    weight = _weight(position, key)
    if delta <= 0 or weight <= 0:
        return current
    gain = int(round(delta * (0.28 + 0.62 * weight)))
    return min(STAT_CAP, current + max(0, gain))


SECONDARY_POSITIONS = {
    "GK": [],
    "CB": ["DMF", "RB", "LB"],
    "LB": ["LMF", "CB", "DMF"],
    "RB": ["RMF", "CB", "DMF"],
    "DMF": ["CB", "CMF"],
    "CMF": ["DMF", "AMF"],
    "LMF": ["LB", "LWF", "AMF"],
    "RMF": ["RB", "RWF", "AMF"],
    "AMF": ["SS", "CMF", "LWF", "RWF"],
    "LWF": ["LMF", "SS", "CF"],
    "RWF": ["RMF", "SS", "CF"],
    "SS": ["CF", "AMF", "LWF", "RWF"],
    "CF": ["SS", "LWF", "RWF"],
}

POS_GRID_LAYOUT = [
    ["LWF", "CF", "RWF"],
    ["LMF", "AMF", "RMF"],
    [None, "CMF", None],
    ["LB", "CB", "RB"],
    [None, "DMF", None],
    [None, "GK", None],
]


def position_familiarity(primary: str, secondaries: list[str], pos: str) -> int:
    primary = (primary or "CF").upper()
    pos = (pos or "").upper()
    if pos == primary:
        return 90
    if pos in {s.upper() for s in secondaries}:
        return 86
    if pos == "GK":
        return 40 if primary != "GK" else 90
    if primary == "GK":
        return 40
    attack = {"LWF", "CF", "RWF", "SS"}
    wide = {"LMF", "RMF", "LB", "RB"}
    mid = {"AMF", "CMF"}
    back = {"CB", "DMF"}
    if primary in attack:
        if pos in attack:
            return 80
        if pos in {"LMF", "RMF"}:
            return 86
        if pos == "AMF":
            return 80
        if pos == "CMF":
            return 72
        if pos in {"LB", "RB"}:
            return 80
        if pos == "CB":
            return 71
        if pos == "DMF":
            return 48
    if primary in back or primary in {"LB", "RB"}:
        if pos in back or pos in {"LB", "RB"}:
            return 80
        if pos in mid:
            return 72
        if pos in wide:
            return 70
        return 48
    if pos in mid or pos in wide:
        return 72
    if pos in back:
        return 64
    return 48


def familiarity_tone(value: int) -> str:
    if value >= 86:
        return "high"
    if value >= 72:
        return "mid"
    if value >= 60:
        return "ok"
    return "low"

_DEFAULT_BOOSTERS = [
    {"id": "breakthrough", "name": "Breakthrough", "bonuses": {"dribbling": 4, "speed": 4, "kicking_power": 4, "physical_contact": 4}},
    {"id": "finishing", "name": "Finishing", "bonuses": {"finishing": 4, "offensive_awareness": 4, "heading": 4, "kicking_power": 4}},
]

BOOSTERS_BY_POS = {
    "GK": [
        {"id": "saving", "name": "Saving", "bonuses": {"gk_awareness": 4, "gk_reflexes": 4, "gk_reach": 4, "gk_parrying": 4}},
        {"id": "build-up", "name": "Build Up", "bonuses": {"gk_catching": 4, "kicking_power": 4, "lofted_pass": 4, "low_pass": 4}},
    ],
    "CB": [
        {"id": "destroyer", "name": "Destroyer", "bonuses": {"defensive_awareness": 4, "tackling": 4, "physical_contact": 4, "heading": 4}},
        {"id": "build-up", "name": "Build Up", "bonuses": {"low_pass": 4, "defensive_awareness": 4, "jumping": 4, "aggression": 4}},
    ],
    "LB": [
        {"id": "full-back", "name": "Full-back Finisher", "bonuses": {"speed": 4, "stamina": 4, "lofted_pass": 4, "defensive_awareness": 4}},
        {"id": "defensive", "name": "Defensive", "bonuses": {"tackling": 4, "defensive_engagement": 4, "physical_contact": 4, "stamina": 4}},
    ],
    "RB": [
        {"id": "full-back", "name": "Full-back Finisher", "bonuses": {"speed": 4, "stamina": 4, "lofted_pass": 4, "defensive_awareness": 4}},
        {"id": "defensive", "name": "Defensive", "bonuses": {"tackling": 4, "defensive_engagement": 4, "physical_contact": 4, "stamina": 4}},
    ],
    "DMF": [
        {"id": "anchor", "name": "Anchor", "bonuses": {"defensive_awareness": 4, "tackling": 4, "low_pass": 4, "physical_contact": 4}},
        {"id": "orchestrator", "name": "Orchestrator", "bonuses": {"low_pass": 4, "lofted_pass": 4, "ball_control": 4, "stamina": 4}},
    ],
    "CMF": [
        {"id": "box-to-box", "name": "Box-to-Box", "bonuses": {"stamina": 4, "low_pass": 4, "ball_control": 4, "defensive_engagement": 4}},
        {"id": "creator", "name": "Creator", "bonuses": {"low_pass": 4, "lofted_pass": 4, "dribbling": 4, "offensive_awareness": 4}},
    ],
    "AMF": [
        {"id": "hole-player", "name": "Hole Player", "bonuses": {"offensive_awareness": 4, "ball_control": 4, "finishing": 4, "dribbling": 4}},
        {"id": "classic-10", "name": "Classic No. 10", "bonuses": {"low_pass": 4, "lofted_pass": 4, "curl": 4, "ball_control": 4}},
    ],
    "LWF": [
        {"id": "breakthrough", "name": "Breakthrough", "bonuses": {"dribbling": 4, "speed": 4, "kicking_power": 4, "physical_contact": 4}},
        {"id": "prolific", "name": "Prolific Winger", "bonuses": {"speed": 4, "finishing": 4, "curl": 4, "offensive_awareness": 4}},
    ],
    "RWF": [
        {"id": "breakthrough", "name": "Breakthrough", "bonuses": {"dribbling": 4, "speed": 4, "kicking_power": 4, "physical_contact": 4}},
        {"id": "prolific", "name": "Prolific Winger", "bonuses": {"speed": 4, "finishing": 4, "curl": 4, "offensive_awareness": 4}},
    ],
    "LMF": [
        {"id": "crossing", "name": "Crossing", "bonuses": {"lofted_pass": 4, "curl": 4, "speed": 4, "stamina": 4}},
        {"id": "breakthrough", "name": "Breakthrough", "bonuses": {"dribbling": 4, "speed": 4, "acceleration": 4, "ball_control": 4}},
    ],
    "RMF": [
        {"id": "crossing", "name": "Crossing", "bonuses": {"lofted_pass": 4, "curl": 4, "speed": 4, "stamina": 4}},
        {"id": "breakthrough", "name": "Breakthrough", "bonuses": {"dribbling": 4, "speed": 4, "acceleration": 4, "ball_control": 4}},
    ],
    "SS": [
        {"id": "finishing", "name": "Finishing", "bonuses": {"finishing": 4, "offensive_awareness": 4, "kicking_power": 4, "heading": 4}},
        {"id": "dribbler", "name": "Dummy Runner", "bonuses": {"dribbling": 4, "acceleration": 4, "ball_control": 4, "offensive_awareness": 4}},
    ],
    "CF": [
        {"id": "finishing", "name": "Goal Poacher", "bonuses": {"finishing": 4, "offensive_awareness": 4, "heading": 4, "kicking_power": 4}},
        {"id": "target", "name": "Target Man", "bonuses": {"heading": 4, "physical_contact": 4, "jumping": 4, "offensive_awareness": 4}},
    ],
}


def boosters_for(position: str) -> list[dict]:
    return BOOSTERS_BY_POS.get((position or "CF").upper(), _DEFAULT_BOOSTERS)


def progression_budget(card_type: str, ovr_gain: int) -> int:
    extra = 8 if _card_key(card_type) in {"epic", "legendary", "big time", "bigtime"} else 5
    return max(extra, min(12, int(ovr_gain * 0.4) or extra))


def _stat_hidden(position: str, key: str) -> bool:
    pos = (position or "CF").upper()
    if pos == "GK":
        return False
    return key.startswith("gk_")


def attach_growth(player: dict) -> dict:
    mode = player.get("mode") or "dream-team"
    card_type = player.get("card_type") or "Standard"
    overall = int(player.get("overall") or 0)
    max_overall = int(player.get("max_overall") or 0) or default_max_overall(mode, card_type, overall)
    level = int(player.get("level") or 0) or default_level()
    max_level = int(player.get("max_level") or 0) or default_max_level(mode, card_type)
    player["overall"] = overall
    player["max_overall"] = max_overall
    player["level"] = level
    player["max_level"] = max_level
    player["ovr_gain"] = max(0, max_overall - overall)
    position = player.get("position") or "CF"
    groups = {"attack": [], "defence": [], "strength": []}
    area = {}
    for key, label, group in ABILITIES:
        value = int(player.get(key) or 0)
        max_value = grown_stat(value, position, key, overall, max_overall)
        gain = max(0, max_value - value)
        hidden = _stat_hidden(position, key)
        groups[group].append(
            {
                "key": key,
                "label": label,
                "value": value,
                "max_value": max_value,
                "gain": gain,
                "now_pct": min(value, STAT_CAP),
                "max_pct": min(max_value, STAT_CAP),
                "hidden": hidden,
            }
        )
    for group, stats in groups.items():
        active = [item for item in stats if item["gain"] > 0 or _weight(position, item["key"]) > 0]
        used = active or stats
        now = round(sum(item["value"] for item in used) / len(used)) if used else 0
        mx = round(sum(item["max_value"] for item in used) / len(used)) if used else 0
        area[group] = {
            "gain": sum(item["gain"] for item in used),
            "now": now,
            "max": mx,
            "now_pct": min(now, STAT_CAP),
            "max_pct": min(mx, STAT_CAP),
        }
    player["ability_groups"] = groups
    player["area_growth"] = area
    player["ovr_now_pct"] = min(100, round(overall / 1.1))
    player["ovr_max_pct"] = min(100, round(max_overall / 1.1))
    player["can_grow"] = player["ovr_gain"] > 0 and max_level > level
    player["secondaries"] = SECONDARY_POSITIONS.get(position, [])
    player["boosters"] = boosters_for(position)
    player["progression_points"] = 0 if mode == "authentic" else progression_budget(card_type, player["ovr_gain"])
    player["pos_grid"] = []
    for row in POS_GRID_LAYOUT:
        line = []
        for slot in row:
            if not slot:
                line.append(None)
                continue
            rating = position_familiarity(position, player["secondaries"], slot)
            line.append(
                {
                    "pos": slot,
                    "rating": rating,
                    "tone": familiarity_tone(rating),
                    "primary": slot == position,
                }
            )
        player["pos_grid"].append(line)
    player["build"] = {
        "level": level,
        "maxLevel": max_level,
        "overall": overall,
        "maxOverall": max_overall,
        "ovrGain": player["ovr_gain"],
        "progressionPoints": player["progression_points"],
        "position": position,
        "boosters": player["boosters"],
        "stats": [
            {
                "key": item["key"],
                "label": item["label"],
                "group": group,
                "base": item["value"],
                "max": item["max_value"],
                "hidden": item["hidden"],
            }
            for group, stats in groups.items()
            for item in stats
        ],
    }
    return player


def growth_fields(mode: str, card_type: str, overall: int, max_overall: int | None = None) -> dict:
    return {
        "level": default_level(),
        "max_level": default_max_level(mode, card_type),
        "max_overall": max_overall if max_overall is not None else default_max_overall(mode, card_type, overall),
    }
