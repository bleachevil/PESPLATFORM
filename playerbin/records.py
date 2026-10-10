"""Fixed-stride player records inside a decoded Player.bin.

Two layouts are known: 400 bytes (base dt200, and some later weekly files)
and 392 bytes (earlier dt870). Names are five 61-byte UTF-8 slots. Abilities
are 6-bit fields; the shown number is the stored value plus 40. Base cards
(pid below 2^32) store that gap scaled by 25/24, so the shown number multiplies
it back by 24/25.
"""

from __future__ import annotations

from dataclasses import dataclass

NAME_SLOTS = 5
NAME_WIDTH = 61

# bit, width, added to the raw value
_PHYSICAL = {
    400: {"height": (248, 8, 100), "weight": (280, 7, 30), "age": (536, 6, 10)},
    392: {"height": (248, 8, 100), "weight": (280, 7, 30), "age": (524, 6, 11)},
}

_POSITION_BIT = {400: 556, 392: 548}
_NAME_AT = {400: 88, 392: 84}

POSITIONS = {
    0: "GK",
    1: "CB",
    2: "LB",
    3: "RB",
    4: "DMF",
    5: "CMF",
    6: "LMF",
    7: "RMF",
    8: "AMF",
    9: "LWF",
    10: "RWF",
    11: "SS",
    12: "CF",
}

# Start bit of each 6-bit ability.
ABILITIES = {
    400: {
        "offensive_awareness": 498,
        "ball_control": 396,
        "dribbling": 492,
        "tight_possession": 550,
        "low_pass": 524,
        "lofted_pass": 448,
        "finishing": 530,
        "heading": 402,
        "set_piece_taking": 368,
        "curl": 428,
        "speed": 434,
        "acceleration": 486,
        "kicking_power": 384,
        "jumping": 408,
        "physical_contact": 518,
        "balance": 504,
        "stamina": 480,
        "defensive_awareness": 390,
        "tackling": 454,
        "aggression": 512,
        "defensive_engagement": 544,
        "gk_awareness": 472,
        "gk_catching": 416,
        "gk_parrying": 466,
        "gk_reflexes": 460,
        "gk_reach": 422,
    },
    392: {
        "offensive_awareness": 480,
        "ball_control": 390,
        "dribbling": 472,
        "tight_possession": 536,
        "low_pass": 504,
        "lofted_pass": 518,
        "finishing": 512,
        "heading": 396,
        "set_piece_taking": 368,
        "curl": 454,
        "speed": 422,
        "acceleration": 466,
        "kicking_power": 374,
        "jumping": 402,
        "physical_contact": 498,
        "balance": 486,
        "stamina": 460,
        "defensive_awareness": 384,
        "tackling": 428,
        "aggression": 492,
        "defensive_engagement": 530,
        "gk_awareness": 448,
        "gk_catching": 408,
        "gk_parrying": 440,
        "gk_reflexes": 434,
        "gk_reach": 416,
    },
}

_OVERALL_KEYS = {
    "GK": ["gk_awareness", "gk_reflexes", "gk_reach", "gk_parrying", "gk_catching"],
    "CB": ["defensive_awareness", "tackling", "physical_contact", "heading", "jumping"],
    "LB": ["speed", "defensive_awareness", "stamina", "lofted_pass", "tackling"],
    "RB": ["speed", "defensive_awareness", "stamina", "lofted_pass", "tackling"],
    "DMF": ["defensive_awareness", "low_pass", "ball_control", "stamina", "aggression"],
    "CMF": ["low_pass", "ball_control", "stamina", "lofted_pass", "defensive_engagement"],
    "LMF": ["speed", "dribbling", "stamina", "lofted_pass", "acceleration"],
    "RMF": ["speed", "dribbling", "stamina", "lofted_pass", "acceleration"],
    "AMF": ["ball_control", "offensive_awareness", "low_pass", "dribbling", "finishing"],
    "LWF": ["dribbling", "speed", "offensive_awareness", "finishing", "acceleration"],
    "RWF": ["dribbling", "speed", "offensive_awareness", "finishing", "acceleration"],
    "SS": ["offensive_awareness", "finishing", "ball_control", "dribbling", "kicking_power"],
    "CF": ["finishing", "offensive_awareness", "kicking_power", "heading", "speed"],
}


@dataclass
class Player:
    pid: int
    names: tuple[str, ...]
    position: str
    height: int
    weight: int
    age: int
    abilities: dict[str, int]
    overall: int

    @property
    def name(self) -> str:
        latin = [part for part in self.names if _latin(part)]
        # Slot order moves between archives. The full name is the one with
        # lowercase letters; the shirt print is uppercase.
        written = [part for part in latin if any(ch.islower() for ch in part)]
        if written:
            return max(written, key=len)
        if latin:
            return max(latin, key=len)
        for part in self.names:
            if part:
                return part
        return ""


def read_bits(record: bytes, start: int, width: int) -> int:
    value = 0
    for step in range(width):
        index = start + step
        if record[index >> 3] & (1 << (index & 7)):
            value |= 1 << step
    return value


def shown_ability(raw: int, pid: int) -> int:
    if pid < 2**32:
        gap = (raw * 24 + 12) // 25
    else:
        gap = raw
    return 40 + gap


def estimate_overall(position: str, abilities: dict[str, int]) -> int:
    keys = _OVERALL_KEYS.get(position, _OVERALL_KEYS["CF"])
    values = [abilities[key] for key in keys]
    return round(sum(values) / len(values))


def _latin(text: str) -> bool:
    letters = [ch for ch in text if ch.isalpha()]
    if len(letters) < 2:
        return False
    return sum(ch.isascii() for ch in letters) >= len(letters) * 0.8


def _text_slots(record: bytes, offset: int) -> tuple[str, ...]:
    slots = []
    for index in range(NAME_SLOTS):
        chunk = record[offset + index * NAME_WIDTH : offset + (index + 1) * NAME_WIDTH]
        raw = chunk.split(b"\x00", 1)[0]
        slots.append(raw.decode("utf-8", errors="replace").strip())
    return tuple(slots)


def _score_layout(table: bytes, stride: int) -> int:
    count = len(table) // stride
    if count < 100 or len(table) % stride:
        return -1
    name_at = _NAME_AT[stride]
    sample = range(0, count, max(1, count // 40))
    latin = 0
    ordered = 0
    previous = -1
    for index in sample:
        record = table[index * stride : (index + 1) * stride]
        pid = int.from_bytes(record[8:16], "little")
        if pid > previous:
            ordered += 1
        previous = pid
        if any(_latin(part) for part in _text_slots(record, name_at)):
            latin += 1
    return latin * 5 + ordered


def choose_stride(table: bytes) -> int:
    scores = {stride: _score_layout(table, stride) for stride in (400, 392)}
    best = max(scores, key=scores.get)
    if scores[best] < 20:
        raise ValueError(f"neither record size looks like players: {scores}")
    return best


def parse_players(table: bytes, stride: int | None = None) -> list[Player]:
    stride = stride or choose_stride(table)
    if len(table) % stride:
        raise ValueError(f"table length {len(table)} is not a multiple of {stride}")
    name_at = _NAME_AT[stride]
    physical = _PHYSICAL[stride]
    ability_bits = ABILITIES[stride]
    position_bit = _POSITION_BIT[stride]
    players: list[Player] = []
    count = len(table) // stride
    for index in range(count):
        record = table[index * stride : (index + 1) * stride]
        pid = int.from_bytes(record[8:16], "little")
        abilities = {
            name: shown_ability(read_bits(record, bit, 6), pid)
            for name, bit in ability_bits.items()
        }
        position = POSITIONS.get(read_bits(record, position_bit, 4), "?")
        players.append(
            Player(
                pid=pid,
                names=_text_slots(record, name_at),
                position=position,
                height=read_bits(record, *physical["height"][:2]) + physical["height"][2],
                weight=read_bits(record, *physical["weight"][:2]) + physical["weight"][2],
                age=read_bits(record, *physical["age"][:2]) + physical["age"][2],
                abilities=abilities,
                overall=estimate_overall(position, abilities),
            )
        )
    return players
