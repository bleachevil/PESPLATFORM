"""Write every decoded Player.bin field to an Excel file.

The weekly dt870 table is 400 bytes per player. That is the layout these
columns were checked against. The base dt200 archive uses the same length
but not the same ability bits, so this exporter refuses it.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from importer.cpk import CpkArchive

from playerbin.container import open_container
from playerbin.records import (
    ABILITIES,
    POSITIONS,
    _NAME_AT,
    _PHYSICAL,
    choose_stride,
    estimate_overall,
    read_bits,
    shown_ability,
)

WEEKLY = Path(r"C:\ProgramData\KONAMI\eFootball\ST\Download\dt870_console_win.cpk")
OUT = ROOT / "data" / "exports" / "playerbin.xlsx"
STRIDE = 400

ABILITY_LABELS = {
    "offensive_awareness": "进攻意识",
    "ball_control": "控球",
    "dribbling": "盘带",
    "tight_possession": "紧密控球",
    "low_pass": "地面传球",
    "lofted_pass": "空中传球",
    "finishing": "射门",
    "heading": "头球",
    "set_piece_taking": "定位球",
    "curl": "弧线",
    "speed": "速度",
    "acceleration": "加速",
    "kicking_power": "踢力",
    "jumping": "弹跳",
    "physical_contact": "身体接触",
    "balance": "平衡",
    "stamina": "耐力",
    "defensive_awareness": "防守意识",
    "tackling": "铲球",
    "aggression": "侵略性",
    "defensive_engagement": "防守参与",
    "gk_awareness": "门将意识",
    "gk_catching": "门将扑接",
    "gk_parrying": "门将挡球",
    "gk_reflexes": "门将反应",
    "gk_reach": "门将覆盖",
}

_CODES = {
    "foot": (654, 1, {0: "右脚", 1: "左脚"}),
    "weak_foot_usage": (478, 2, {0: "几乎不用", 1: "很少", 2: "偶尔", 3: "经常"}),
    "weak_foot_accuracy": (578, 2, {0: "低", 1: "中", 2: "高", 3: "很高"}),
    "form": (582, 2, {0: "不稳定", 1: "标准", 2: "稳定"}),
    "injury_resistance": (542, 2, {0: "低", 1: "中", 2: "高"}),
}

# Two bits each. A player's own position reads 2.
_APTITUDE = {
    "GK": 414,
    "LB": 318,
    "CMF": 510,
    "RMF": 576,
    "AMF": 580,
    "CB": 584,
    "CF": 586,
    "LMF": 588,
    "LWF": 590,
    "RB": 592,
    "DMF": 594,
    "RWF": 596,
    "SS": 598,
}

_ATT_STYLE = (372, 8)
_DEF_STYLE = (440, 6)
_ATT_NAMES = {
    0: "Basic",
    1: "Goal Poacher",
    2: "Dummy Runner",
    3: "Fox in the Box",
    4: "Prolific Winger",
    5: "Classic No. 10",
    6: "Hole Player",
    7: "Box-to-Box",
    8: "Anchor Man",
    10: "Extra Frontman",
    11: "Attacking Full-back",
    12: "Defensive Full-back",
    13: "Deep-Lying Forward",
    14: "Creative Playmaker",
    15: "Build Up",
    18: "Roaming Flank",
    19: "Cross Specialist",
    20: "Orchestrator",
    21: "Full-back Finisher",
    22: "Target Man",
    34: "Basic",
    35: "Basic",
}
_DEF_NAMES = {
    (0, 0): "Basic",
    (0, 9): "The Destroyer",
    (0, 16): "Attacking GK",
    (0, 17): "Defensive GK",
    (1, 0): "Basic",
    (2, 0): "Basic",
    (3, 0): "Basic",
    (4, 0): "Basic",
    (5, 0): "Basic",
    (6, 0): "Basic",
    (7, 0): "Box-to-Box",
    (8, 0): "Anchor Man",
    (10, 0): "Basic",
    (11, 0): "Basic",
    (12, 0): "Basic",
    (13, 0): "Basic",
    (14, 0): "Basic",
    (15, 0): "Basic",
    (18, 0): "Basic",
    (19, 0): "Basic",
    (20, 0): "Basic",
    (21, 0): "Basic",
    (22, 0): "Basic",
    (34, 0): "Attacking GK",
    (35, 0): "Attacking GK",
}

# One bit each, checked against a full editor export on this 400-byte layout.
_SKILLS = {
    "Acceleration Burst": 632,
    "Acrobatic Clearance": 679,
    "Acrobatic Finishing": 669,
    "Aerial Fort": 609,
    "Aerial Superiority": 606,
    "Attack Trigger": 624,
    "Attacking Surge": 634,
    "Blitz Curler": 659,
    "Blocker": 673,
    "Bullet Header": 604,
    "Captaincy": 620,
    "Chip Shot Control": 641,
    "Chop Turn": 287,
    "Cut Behind & Turn": 677,
    "Dipping Shot": 655,
    "Double Touch": 668,
    "Edged Crossing": 658,
    "Fighting Spirit": 612,
    "First-time Shot": 650,
    "Flip Flap": 611,
    "Fortress": 670,
    "GK Directing Defence": 575,
    "GK High Punt": 223,
    "GK Long Throw": 667,
    "GK Low Punt": 617,
    "GK Penalty Saver": 633,
    "GK Spirit Roar": 631,
    "Game-changing Pass": 642,
    "Gamesmanship": 619,
    "Heading": 625,
    "Heel Trick": 640,
    "Interception": 636,
    "Knuckle Shot": 652,
    "Long Range Shooting": 662,
    "Long Throw": 666,
    "Long-Range Curler": 676,
    "Long-reach Tackle": 351,
    "Low Lofted Pass": 615,
    "Low Screamer": 626,
    "Magnetic Feet": 608,
    "Man Marking": 638,
    "Marseille Turn": 621,
    "Momentum Dribbling": 646,
    "No Look Pass": 651,
    "One-touch Pass": 644,
    "Outside Curler": 623,
    "Penalty Specialist": 665,
    "Phenomenal Finishing": 622,
    "Phenomenal Pass": 637,
    "Pinpoint Crossing": 605,
    "Rabona": 657,
    "Rising Shot": 630,
    "Scissors Feint": 663,
    "Scotch Move": 671,
    "Shadow Hunt": 656,
    "Sliding Tackle": 635,
    "Snap Strike": 639,
    "Sole Control": 675,
    "Sombrero": 603,
    "Super-sub": 660,
    "Tap Trick": 628,
    "Through Passing": 613,
    "Track Back": 661,
    "Visionary Pass": 664,
    "Weighted Pass": 610,
    "Willpower": 627,
}
_AI = {
    "Trickster": 616,
    "Mazing Run": 680,
    "Speeding Bullet": 674,
    "Incisive Run": 649,
    "Early Cross": 614,
    "Long Ranger": 647,
    "Long Ball Expert": 678,
}


def _blank(value: int) -> int | None:
    return value or None


def _date(value: int) -> str | None:
    if not value:
        return None
    year, month, day = value // 10000, (value // 100) % 100, value % 100
    if 1980 <= year <= 2100 and 1 <= month <= 12 and 1 <= day <= 31:
        return f"{year:04d}-{month:02d}-{day:02d}"
    return str(value)


def _flag(record: bytes, bit: int) -> int | None:
    return 1 if read_bits(record, bit, 1) else None


def _headers() -> list[str]:
    headers = [
        "球员ID",
        "姓名",
        "名字1",
        "名字2",
        "名字3",
        "名字4",
        "名字5",
        "位置",
        "年龄",
        "身高",
        "体重",
        "国籍ID",
        "俱乐部ID",
        "青训俱乐部ID",
        "租借母队ID",
        "合同到期",
        "租借到期",
        "惯用脚",
        "逆足频率",
        "逆足精度",
        "状态",
        "抗伤",
        "总评估算",
    ]
    headers.extend(ABILITY_LABELS[key] for key in ABILITIES[STRIDE])
    headers.extend(f"适性{pos}" for pos in POSITIONS.values())
    headers.extend(["进攻风格编号", "进攻风格", "防守风格编号", "防守风格"])
    headers.extend(f"技能 {name}" for name in _SKILLS)
    headers.extend(f"AI {name}" for name in _AI)
    return headers


def _row(record: bytes) -> list:
    pid = int.from_bytes(record[8:16], "little")
    names = []
    name_at = _NAME_AT[STRIDE]
    for index in range(5):
        chunk = record[name_at + index * 61 : name_at + (index + 1) * 61]
        names.append(chunk.split(b"\x00", 1)[0].decode("utf-8", errors="replace").strip())
    physical = _PHYSICAL[STRIDE]
    height = read_bits(record, *physical["height"][:2]) + physical["height"][2]
    weight = read_bits(record, *physical["weight"][:2]) + physical["weight"][2]
    age = read_bits(record, *physical["age"][:2]) + physical["age"][2]
    position = POSITIONS.get(read_bits(record, 556, 4), "?")
    abilities = {
        key: shown_ability(read_bits(record, bit, 6), pid) for key, bit in ABILITIES[STRIDE].items()
    }
    att = read_bits(record, *_ATT_STYLE)
    defence = read_bits(record, *_DEF_STYLE)
    written = [part for part in names if any(ch.isalpha() and ch.islower() for ch in part)]
    display = max(written, key=len) if written else next((part for part in names if part), "")
    row = [
        pid,
        display,
        *names,
        position,
        age,
        height,
        weight,
        _blank(read_bits(record, 329, 9)),
        _blank(int.from_bytes(record[16:20], "little")),
        _blank(int.from_bytes(record[0:4], "little")),
        _blank(int.from_bytes(record[4:8], "little")),
        _date(read_bits(record, 160, 25)),
        _date(read_bits(record, 192, 25)),
    ]
    for key, (_bit, width, labels) in _CODES.items():
        raw = read_bits(record, _bit, width)
        row.append(labels.get(raw, str(raw)))
    row.append(estimate_overall(position, abilities))
    row.extend(abilities[key] for key in ABILITIES[STRIDE])
    row.extend(read_bits(record, _APTITUDE[pos], 2) for pos in POSITIONS.values())
    row.extend([att, _ATT_NAMES.get(att, ""), defence, _DEF_NAMES.get((att, defence), "")])
    row.extend(_flag(record, bit) for bit in _SKILLS.values())
    row.extend(_flag(record, bit) for bit in _AI.values())
    return row


def _notes() -> list[tuple[str, str]]:
    return [
        ("来源", "周更 dt870_console_win.cpk 里的 common/etc/pesdb/Player.bin"),
        ("记录", "400 字节一条。这份表用的就是这个长度。"),
        ("总评估算", "文件里没有总评。这一列是按位置把几项能力取平均，方便排序。"),
        ("名字1-5", "日文、中文、英文全名、球衣名。槽的顺序会随包变化，姓名列取带小写的全名。"),
        ("国籍ID / 俱乐部ID", "只是编号。国名在 Country.bin，队名在 Team.bin。"),
        ("合同到期 / 租借到期", "没有就是空。"),
        ("适性", "0、1、2。注册位置那一列一般是 2。"),
        ("技能 / AI", "1 表示有，空表示没有。"),
        ("没放进来的", "总评、等级上限、评价字母、球衣号码不在 Player.bin。号码在 PlayerAssignment.bin。"),
        ("底包 dt200", "姓名能读，能力位和这份周更表不一致，所以没有导出。"),
    ]


def _player_blob(path: Path) -> bytes:
    archive = CpkArchive(path)
    for entry in archive.files:
        if entry.path.replace("\\", "/").endswith("common/etc/pesdb/Player.bin"):
            return archive.read_file(entry)
    raise FileNotFoundError(path)


def write_excel(cpk: Path = WEEKLY, dest: Path = OUT) -> Path:
    import xlsxwriter

    table = open_container(_player_blob(cpk))
    stride = choose_stride(table)
    if stride != STRIDE:
        raise SystemExit(f"{cpk} uses {stride}-byte records; this sheet is the 400-byte weekly table")
    count = len(table) // STRIDE
    headers = _headers()
    dest.parent.mkdir(parents=True, exist_ok=True)

    book = xlsxwriter.Workbook(dest, {"constant_memory": True, "strings_to_urls": False})
    sheet = book.add_worksheet("球员")
    header_fmt = book.add_format({"bold": True, "bg_color": "#1F4E79", "font_color": "#FFFFFF"})
    sheet.freeze_panes(1, 2)
    sheet.autofilter(0, 0, count, len(headers) - 1)
    sheet.set_column(0, 0, 14)
    sheet.set_column(1, 6, 22)
    for col, title in enumerate(headers):
        sheet.write(0, col, title, header_fmt)
    for index in range(count):
        record = table[index * STRIDE : (index + 1) * STRIDE]
        sheet.write_row(index + 1, 0, _row(record))

    notes = book.add_worksheet("说明")
    notes.set_column(0, 0, 28)
    notes.set_column(1, 1, 88)
    for row, (label, text) in enumerate(_notes()):
        notes.write(row, 0, label, header_fmt)
        notes.write(row, 1, text)
    book.close()
    return dest


def main() -> None:
    path = write_excel()
    print(f"wrote {path}  {path.stat().st_size / 1048576:.1f} MB")


if __name__ == "__main__":
    main()
