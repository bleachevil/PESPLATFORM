"""Shared eFootball ability / style definitions."""

from __future__ import annotations

ABILITIES = [
    ("offensive_awareness", "Offensive Awareness", "attack"),
    ("ball_control", "Ball Control", "attack"),
    ("dribbling", "Dribbling", "attack"),
    ("tight_possession", "Tight Possession", "attack"),
    ("low_pass", "Low Pass", "attack"),
    ("lofted_pass", "Lofted Pass", "attack"),
    ("finishing", "Finishing", "attack"),
    ("heading", "Heading", "attack"),
    ("set_piece_taking", "Set Piece Taking", "attack"),
    ("curl", "Curl", "attack"),
    ("defensive_awareness", "Defensive Awareness", "defence"),
    ("tackling", "Tackling", "defence"),
    ("aggression", "Aggression", "defence"),
    ("defensive_engagement", "Defensive Engagement", "defence"),
    ("gk_awareness", "GK Awareness", "defence"),
    ("gk_catching", "GK Catching", "defence"),
    ("gk_parrying", "GK Parrying", "defence"),
    ("gk_reflexes", "GK Reflexes", "defence"),
    ("gk_reach", "GK Reach", "defence"),
    ("speed", "Speed", "strength"),
    ("acceleration", "Acceleration", "strength"),
    ("kicking_power", "Kicking Power", "strength"),
    ("jumping", "Jumping", "strength"),
    ("physical_contact", "Physical Contact", "strength"),
    ("balance", "Balance", "strength"),
    ("stamina", "Stamina", "strength"),
]

ABILITY_KEYS = [key for key, _label, _group in ABILITIES]

POSITIONS = ["GK", "CB", "LB", "RB", "DMF", "CMF", "LMF", "RMF", "AMF", "LWF", "RWF", "SS", "CF"]

POSITION_GROUPS = [
    ("Goalkeepers", ["GK"]),
    ("Defenders", ["CB", "LB", "RB"]),
    ("Midfielders", ["DMF", "CMF", "LMF", "RMF", "AMF"]),
    ("Forwards", ["LWF", "RWF", "SS", "CF"]),
]

MODES = {
    "dream-team": "Dream Team",
    "authentic": "Authentic",
}

POSITION_LABELS = {
    "GK": "Goalkeeper",
    "CB": "Centre Back",
    "LB": "Left Back",
    "RB": "Right Back",
    "DMF": "Defensive Midfielder",
    "CMF": "Centre Midfielder",
    "LMF": "Left Midfielder",
    "RMF": "Right Midfielder",
    "AMF": "Attacking Midfielder",
    "LWF": "Left Wing Forward",
    "RWF": "Right Wing Forward",
    "SS": "Second Striker",
    "CF": "Centre Forward",
}

CSV_ALIASES = {
    "pid": ("pid", "id", "playerid", "player_id"),
    "name": ("name", "playername", "player_name"),
    "position": ("position", "pos", "registeredposition", "registered_position"),
    "height": ("height",),
    "weight": ("weight",),
    "age": ("age",),
    "foot": ("foot", "strongerfoot", "stronger_foot", "preferredfoot"),
    "weak_foot_usage": ("weakfootusage", "weak_foot_usage"),
    "weak_foot_accuracy": ("weakfootaccuracy", "weak_foot_accuracy"),
    "form": ("form",),
    "injury_resistance": ("injuryresistance", "injury_resistance"),
    "nationality": ("nationality", "nation"),
    "region": ("region", "continent"),
    "club": ("club", "team", "teamname", "team_name"),
    "league": ("league",),
    "card_type": ("cardtype", "card_type", "playertype"),
    "mode": ("mode", "database", "db", "gamemode", "game_mode"),
    "pack_name": ("pack", "packname", "pack_name", "featuredpack"),
    "pack_date": ("packdate", "pack_date", "released", "releasedon", "released_on"),
    "squad_number": ("squadnumber", "squad_number", "number", "shirt", "shirtnumber"),
    "image": ("image", "photo", "picture", "img", "imagepath", "image_path"),
    "overall": ("overall", "ovr", "overallrating", "overall_rating"),
    "max_overall": ("maxoverall", "max_overall", "maxovr"),
    "level": ("level", "lv", "playerlevel"),
    "max_level": ("maxlevel", "max_level", "maxlv"),
    "att_style": ("attstyle", "att_style", "playingstyle", "playing_style"),
    "def_style": ("defstyle", "def_style", "defensiveplayingstyle"),
    "skills": ("skills", "playerskills", "player_skills"),
    "ai_styles": ("aistyles", "ai_styles", "aiplayingstyles"),
    "source_url": ("source_url", "link", "url", "pesdb", "pesdburl", "pesdb_url"),
}

for key, label, _group in ABILITIES:
    CSV_ALIASES[key] = (key, label.lower().replace(" ", ""), label.lower().replace(" ", "_"))
