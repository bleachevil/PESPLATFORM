"""Fictional sample cards covering Authentic squads and Dream Team packs."""

from __future__ import annotations

from importer.fields import ABILITY_KEYS
from importer.growth import default_max_level, default_max_overall, default_level

DT = "dream-team"
AUTH = "authentic"

ATLANTIC = ("Atlantic FC", "European League", "Europe")
NORTH = ("North Gate", "European League", "Europe")
TOKYO = ("Tokyo Blue", "Asian League", "Asia")
PACIFIC = ("Pacific United", "American League", "South America")
MILAN = ("Milan River", "European League", "Europe")
ATLAS = ("Atlas Stars", "African League", "Africa")
SEOUL = ("Seoul Tide", "Asian League", "Asia")
MUMBAI = ("Mumbai FC", "Asian League", "Asia")
NI = ("Northern Ireland", "Other", "Europe")
ITA = ("Italy", "Other", "Europe")
WAL = ("Wales", "Other", "Europe")
NED = ("Netherlands", "Other", "Europe")
ESP = ("Spain", "Other", "Europe")
CZE = ("Czechia", "Other", "Europe")
NAGOYA = ("Nagoya Grampus", "J.LEAGUE", "Asia")
SHONAN = ("Shonan Bellmare", "J.LEAGUE", "Asia")
BARCA = ("FC Barcelona", "Spanish League", "Europe")
JUV = ("Juventus", "Italian League", "Europe")

POS_FOCUS = {
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


def _clamp(value: int) -> int:
    return max(40, min(99, value))


def _abilities(ovr: int, pos: str) -> dict[str, int]:
    stats = {key: 40 for key in ABILITY_KEYS}
    if pos != "GK":
        for key in ("speed", "acceleration", "stamina", "balance", "physical_contact"):
            stats[key] = _clamp(int(ovr * 0.72))
    for key, weight in POS_FOCUS.get(pos, {}).items():
        if key in stats:
            stats[key] = _clamp(int(ovr * weight))
    if pos != "GK":
        for key in ("gk_awareness", "gk_catching", "gk_parrying", "gk_reflexes", "gk_reach"):
            stats[key] = 40
    return stats


def card(
    pid: str,
    name: str,
    position: str,
    overall: int,
    club: tuple[str, str, str],
    nationality: str,
    region: str,
    *,
    mode: str = DT,
    card_type: str = "Standard",
    pack_name: str = "",
    pack_date: str = "",
    squad_number: int | None = None,
    age: int = 26,
    height: int = 180,
    weight: int = 74,
    foot: str = "Right",
    att_style: str = "Basic",
    def_style: str = "Basic",
    skills: str = "",
    ai_styles: str = "",
    max_overall: int | None = None,
    level: int | None = None,
    max_level: int | None = None,
) -> dict:
    abilities = _abilities(overall, position)
    return {
        "pid": pid,
        "name": name,
        "position": position,
        "overall": overall,
        "max_overall": max_overall if max_overall is not None else default_max_overall(mode, card_type, overall),
        "level": level if level is not None else default_level(),
        "max_level": max_level if max_level is not None else default_max_level(mode, card_type),
        "club": club[0],
        "league": club[1],
        "region": region,
        "nationality": nationality,
        "mode": mode,
        "card_type": card_type,
        "pack_name": pack_name,
        "pack_date": pack_date,
        "squad_number": squad_number,
        "age": age,
        "height": height,
        "weight": weight,
        "foot": foot,
        "weak_foot_usage": "Occasionally",
        "weak_foot_accuracy": "High" if overall >= 85 else "Medium",
        "form": "Unwavering" if overall >= 88 else "Standard",
        "injury_resistance": "Medium",
        "att_style": att_style,
        "def_style": def_style,
        "skills": [s for s in skills.split("|") if s],
        "ai_styles": [s for s in ai_styles.split("|") if s],
        **abilities,
    }


ALL_STARS = "National All-Stars"
JLEAGUE = "J.LEAGUE Selection"
WORLDWIDE = "Worldwide 17 Sep '26"
DATE = "2026-09-17"


def sample_records() -> list[dict]:
    records = [
        # Authentic starting XIs
        card("2001", "Samuel Okonkwo", "GK", 80, ATLANTIC, "Nigeria", "Africa", mode=AUTH, card_type="Authentic", squad_number=1, age=31, height=193, weight=88, att_style="Offensive Goalkeeper"),
        card("2002", "Nathan Cole", "RB", 77, ATLANTIC, "England", "Europe", mode=AUTH, card_type="Authentic", squad_number=2, age=24, height=178),
        card("2003", "Theo Walsh", "LB", 76, ATLANTIC, "Ireland", "Europe", mode=AUTH, card_type="Authentic", squad_number=3, age=25, height=181, foot="Left"),
        card("2004", "Luca Moreau", "CB", 79, ATLANTIC, "France", "Europe", mode=AUTH, card_type="Authentic", squad_number=4, age=28, height=188, weight=82, att_style="Build Up", def_style="Destroyer"),
        card("2005", "Henrik Dahl", "CB", 78, ATLANTIC, "Denmark", "Europe", mode=AUTH, card_type="Authentic", squad_number=5, age=29, height=190, weight=84),
        card("2006", "Owen Grant", "DMF", 77, ATLANTIC, "Scotland", "Europe", mode=AUTH, card_type="Authentic", squad_number=6, age=27, att_style="Anchor Man"),
        card("2007", "Mateo Ruiz", "CMF", 78, ATLANTIC, "Spain", "Europe", mode=AUTH, card_type="Authentic", squad_number=8, age=26, att_style="Box-to-Box"),
        card("2008", "Marco Silva", "RWF", 81, ATLANTIC, "Portugal", "Europe", mode=AUTH, card_type="Authentic", squad_number=7, age=27, height=178, weight=72, att_style="Prolific Winger", skills="Double Touch|Pinpoint Crossing"),
        card("2009", "Elena Varga", "CF", 80, ATLANTIC, "Hungary", "Europe", mode=AUTH, card_type="Authentic", squad_number=9, age=24, height=176, weight=68, att_style="Goal Poacher", skills="First-time Shot|Heading"),
        card("2010", "Sofia Klein", "LWF", 79, ATLANTIC, "Germany", "Europe", mode=AUTH, card_type="Authentic", squad_number=11, age=23, height=168, foot="Left", att_style="Roaming Flank"),
        card("2011", "Ibrahim Yilmaz", "AMF", 78, ATLANTIC, "Turkey", "Europe", mode=AUTH, card_type="Authentic", squad_number=10, age=25, att_style="Classic No. 10"),
        card("2012", "Callum Reed", "CF", 74, ATLANTIC, "England", "Europe", mode=AUTH, card_type="Authentic", squad_number=18, age=33, height=188, weight=84, att_style="Target Man"),
        card("2101", "Lars Holm", "GK", 79, NORTH, "Norway", "Europe", mode=AUTH, card_type="Authentic", squad_number=1, age=30, height=192),
        card("2102", "Jonas Berg", "CB", 82, NORTH, "Sweden", "Europe", mode=AUTH, card_type="Authentic", squad_number=4, age=29, height=191, weight=86, att_style="Build Up", def_style="Destroyer", skills="Heading|Interception|Blocker"),
        card("2103", "Erik Nilsen", "CB", 78, NORTH, "Norway", "Europe", mode=AUTH, card_type="Authentic", squad_number=5, age=27, height=187),
        card("2104", "Mikkel Sørensen", "RB", 76, NORTH, "Denmark", "Europe", mode=AUTH, card_type="Authentic", squad_number=2, age=24),
        card("2105", "Johan Lind", "LB", 75, NORTH, "Sweden", "Europe", mode=AUTH, card_type="Authentic", squad_number=3, age=26, foot="Left"),
        card("2106", "Noah Brandt", "DMF", 80, NORTH, "Germany", "Europe", mode=AUTH, card_type="Authentic", squad_number=6, age=30, height=186, att_style="Orchestrator", def_style="Anchor Man"),
        card("2107", "Felix Krüger", "CMF", 77, NORTH, "Germany", "Europe", mode=AUTH, card_type="Authentic", squad_number=8, age=25),
        card("2108", "Anya Petrov", "AMF", 76, NORTH, "Russia", "Europe", mode=AUTH, card_type="Authentic", squad_number=10, age=22, foot="Left"),
        card("2109", "Sven Olafsen", "RWF", 75, NORTH, "Iceland", "Europe", mode=AUTH, card_type="Authentic", squad_number=7, age=28),
        card("2110", "Maja Lindqvist", "LWF", 76, NORTH, "Sweden", "Europe", mode=AUTH, card_type="Authentic", squad_number=11, age=23),
        card("2111", "Viktor Holm", "CF", 79, NORTH, "Finland", "Europe", mode=AUTH, card_type="Authentic", squad_number=9, age=27, att_style="Goal Poacher"),
        card("2201", "Yuki Sato", "GK", 76, TOKYO, "Japan", "Asia", mode=AUTH, card_type="Authentic", squad_number=1, age=28, height=186),
        card("2202", "Kenji Arai", "AMF", 81, TOKYO, "Japan", "Asia", mode=AUTH, card_type="Authentic", squad_number=10, age=26, height=172, weight=66, foot="Left", att_style="Classic No. 10", skills="One-touch Pass|Through Passing"),
        card("2203", "Haruto Mori", "CB", 77, TOKYO, "Japan", "Asia", mode=AUTH, card_type="Authentic", squad_number=4, age=29, height=184),
        card("2204", "Ren Takahashi", "RB", 75, TOKYO, "Japan", "Asia", mode=AUTH, card_type="Authentic", squad_number=2, age=24),
        card("2205", "Sora Inoue", "LB", 74, TOKYO, "Japan", "Asia", mode=AUTH, card_type="Authentic", squad_number=3, age=23, foot="Left"),
        card("2206", "Daichi Fujimoto", "DMF", 76, TOKYO, "Japan", "Asia", mode=AUTH, card_type="Authentic", squad_number=6, age=27),
        card("2207", "Mio Nakamura", "CMF", 75, TOKYO, "Japan", "Asia", mode=AUTH, card_type="Authentic", squad_number=8, age=22),
        card("2208", "Riku Hayashi", "CF", 78, TOKYO, "Japan", "Asia", mode=AUTH, card_type="Authentic", squad_number=9, age=25, att_style="Dummy Runner"),
        card("2301", "Diego Rivas", "LB", 79, PACIFIC, "Argentina", "South America", mode=AUTH, card_type="Authentic", squad_number=3, age=28, height=181, foot="Left", att_style="Full-back Finisher"),
        card("2302", "Matías Soto", "GK", 77, PACIFIC, "Chile", "South America", mode=AUTH, card_type="Authentic", squad_number=1, age=32, height=189),
        card("2303", "Paulo Mendes", "CB", 78, PACIFIC, "Brazil", "South America", mode=AUTH, card_type="Authentic", squad_number=4, age=26, height=186),
        card("2304", "João Ferreira", "RB", 76, PACIFIC, "Brazil", "South America", mode=AUTH, card_type="Authentic", squad_number=2, age=24),
        card("2305", "Camila Torres", "CMF", 77, PACIFIC, "Colombia", "South America", mode=AUTH, card_type="Authentic", squad_number=8, age=25),
        card("2306", "Lucas Benítez", "CF", 80, PACIFIC, "Argentina", "South America", mode=AUTH, card_type="Authentic", squad_number=9, age=27, att_style="Goal Poacher"),
        card("2401", "Lucia Moretti", "CMF", 81, MILAN, "Italy", "Europe", mode=AUTH, card_type="Authentic", squad_number=8, age=23, height=168, att_style="Box-to-Box", def_style="Anchor Man"),
        card("2402", "Giulia Conti", "GK", 76, MILAN, "Italy", "Europe", mode=AUTH, card_type="Authentic", squad_number=1, age=27, height=180),
        card("2403", "Marco Bianchi", "CB", 77, MILAN, "Italy", "Europe", mode=AUTH, card_type="Authentic", squad_number=5, age=30),
        card("2404", "Alessio Greco", "SS", 78, MILAN, "Italy", "Europe", mode=AUTH, card_type="Authentic", squad_number=9, age=26),
        card("2501", "Amira Haddad", "LWF", 82, ATLAS, "Morocco", "Africa", mode=AUTH, card_type="Authentic", squad_number=11, age=22, height=165, att_style="Roaming Flank", skills="Double Touch|Chop Turn"),
        card("2502", "Youssef El Amrani", "CB", 77, ATLAS, "Morocco", "Africa", mode=AUTH, card_type="Authentic", squad_number=4, age=28),
        card("2503", "Amina Diallo", "CMF", 76, ATLAS, "Senegal", "Africa", mode=AUTH, card_type="Authentic", squad_number=8, age=24),
        card("2601", "William Cho", "SS", 80, SEOUL, "Korea Republic", "Asia", mode=AUTH, card_type="Authentic", squad_number=10, age=25, height=183, foot="Left", att_style="Dummy Runner"),
        card("2602", "Min-jun Park", "CB", 76, SEOUL, "Korea Republic", "Asia", mode=AUTH, card_type="Authentic", squad_number=5, age=27),
        card("2701", "Priya Nair", "RB", 77, MUMBAI, "India", "Asia", mode=AUTH, card_type="Authentic", squad_number=2, age=24, height=170, att_style="Offensive Full-back"),
        card("2702", "Arjun Mehta", "CF", 75, MUMBAI, "India", "Asia", mode=AUTH, card_type="Authentic", squad_number=9, age=26),
        # Dream Team standard club cards
        card("1001", "Marco Silva", "RWF", 86, ATLANTIC, "Portugal", "Europe", squad_number=7, age=27, height=178, att_style="Prolific Winger", skills="Double Touch|Pinpoint Crossing", ai_styles="Incisive Run"),
        card("1002", "Elena Varga", "CF", 85, ATLANTIC, "Hungary", "Europe", squad_number=9, age=24, height=176, att_style="Goal Poacher"),
        card("1003", "Jonas Berg", "CB", 84, NORTH, "Sweden", "Europe", squad_number=4, age=29, height=191, att_style="Build Up", def_style="Destroyer"),
        card("1004", "Kenji Arai", "AMF", 84, TOKYO, "Japan", "Asia", squad_number=10, age=26, height=172, foot="Left", att_style="Classic No. 10"),
        card("1005", "Samuel Okonkwo", "GK", 83, ATLANTIC, "Nigeria", "Africa", squad_number=1, age=31, height=193, att_style="Offensive Goalkeeper"),
        card("1006", "Lucia Moretti", "CMF", 84, MILAN, "Italy", "Europe", squad_number=8, age=23, height=168, att_style="Box-to-Box"),
        card("1007", "Diego Rivas", "LB", 82, PACIFIC, "Argentina", "South America", squad_number=3, age=28, foot="Left", att_style="Full-back Finisher"),
        card("1008", "Noah Brandt", "DMF", 83, NORTH, "Germany", "Europe", squad_number=6, age=30, att_style="Orchestrator"),
        card("1009", "Amira Haddad", "LWF", 85, ATLAS, "Morocco", "Africa", squad_number=11, age=22, height=165, att_style="Roaming Flank"),
        card("1010", "William Cho", "SS", 84, SEOUL, "Korea Republic", "Asia", squad_number=10, age=25, foot="Left"),
        card("1011", "Priya Nair", "RB", 81, MUMBAI, "India", "Asia", squad_number=2, age=24, att_style="Offensive Full-back"),
        card("1012", "Lucas Benítez", "CF", 83, PACIFIC, "Argentina", "South America", squad_number=9, age=27),
        card("1013", "Luca Moreau", "CB", 82, ATLANTIC, "France", "Europe", squad_number=4, age=28, height=188, att_style="Build Up", def_style="Destroyer"),
        card("1014", "Theo Walsh", "LB", 80, ATLANTIC, "Ireland", "Europe", squad_number=3, age=25, foot="Left"),
        card("1015", "Nathan Cole", "RB", 80, ATLANTIC, "England", "Europe", squad_number=2, age=24),
        card("1016", "Owen Grant", "DMF", 81, ATLANTIC, "Scotland", "Europe", squad_number=6, age=27, att_style="Anchor Man"),
        # Dream Team pack cards with published eFootball IDs so official art can load
        card("88045755828950", "George Best", "RWF", 89, NI, "Northern Ireland", "Europe", card_type="Epic", pack_name=ALL_STARS, pack_date=DATE, age=24, height=175, weight=64, att_style="Prolific Winger", def_style="Frontline Pressure", skills="Double Touch|Flip Flap|Marseille Turn|Cut Behind & Turn|Sole Control|Long-range Curler", ai_styles="Trickster|Mazing Run|Speeding Bullet", max_overall=104),
        card("89139630444046", "Alessandro Del Piero", "SS", 87, ITA, "Italy", "Europe", card_type="Epic", pack_name=ALL_STARS, pack_date=DATE, age=29, height=174, weight=73, foot="Left", att_style="Goal Poacher", skills="First-time Shot|Long-range Curler|One-touch Pass", ai_styles="Incisive Run"),
        card("88045755861672", "Gareth Bale", "RWF", 87, WAL, "Wales", "Europe", card_type="Epic", pack_name=ALL_STARS, pack_date=DATE, age=27, height=185, weight=82, foot="Left", att_style="Prolific Winger", def_style="Attack Outlet", skills="Scissors Feint|Long-range Shooting|Knuckle Shot|Dipping Shot|Acrobatic Finishing|First-time Shot|Outside Curler|Rabona|Acceleration Burst", ai_styles="Mazing Run|Incisive Run|Long Ball Expert"),
        card("88045755827094", "Edwin van der Sar", "GK", 87, NED, "Netherlands", "Europe", card_type="Epic", pack_name=ALL_STARS, pack_date=DATE, age=34, height=197, weight=83, att_style="Offensive Goalkeeper"),
        card("88045755960761", "Carles Puyol", "CB", 86, ESP, "Spain", "Europe", card_type="Epic", pack_name=ALL_STARS, pack_date=DATE, age=30, height=178, weight=80, att_style="Build Up", def_style="Destroyer", skills="Man Marking|Interception|Blocker|Heading"),
        card("88045755960774", "Tomáš Rosický", "AMF", 86, CZE, "Czechia", "Europe", card_type="Epic", pack_name=ALL_STARS, pack_date=DATE, age=26, height=178, weight=67, att_style="Hole Player", skills="One-touch Pass|Through Passing|Outside Curler"),
        card("88045487393209", "Kawashima Eiji", "GK", 84, NAGOYA, "Japan", "Asia", card_type="Featured", pack_name=JLEAGUE, pack_date=DATE, age=38, height=185, weight=80, att_style="Defensive Goalkeeper"),
        card("52912386636098", "Lamine Yamal", "RWF", 86, BARCA, "Spain", "Europe", card_type="Featured", pack_name=WORLDWIDE, pack_date=DATE, age=18, height=180, weight=72, att_style="Prolific Winger", skills="Double Touch|Sole Control|Pinpoint Crossing"),
        card("106799193770861", "Weston McKennie", "CMF", 85, JUV, "United States", "North America", card_type="Featured", pack_name=WORLDWIDE, pack_date=DATE, age=26, height=183, weight=84, att_style="Box-to-Box"),
        card("88045487406166", "Inui Takashi", "AMF", 85, SHONAN, "Japan", "Asia", card_type="Featured", pack_name=JLEAGUE, pack_date=DATE, age=35, height=169, weight=66, foot="Right", att_style="Hole Player"),
        card("106799193796011", "Francisco Conceição", "RWF", 86, JUV, "Portugal", "Europe", card_type="Featured", pack_name=WORLDWIDE, pack_date=DATE, age=22, height=170, weight=64, att_style="Prolific Winger", skills="Double Touch|Chop Turn"),
        card("88045487454479", "Nagai Kensuke", "CF", 84, NAGOYA, "Japan", "Asia", card_type="Featured", pack_name=JLEAGUE, pack_date=DATE, age=35, height=178, weight=73, att_style="Goal Poacher"),
    ]
    return records
