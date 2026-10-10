"""Read-only lookup: find efhub card IDs (u64) in the local variation/player tables."""
from __future__ import annotations

import csv
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from importer.cpk import CpkArchive
from playerbin.container import open_container
from playerbin.records import parse_players

sys.stdout.reconfigure(encoding="utf-8")

CPK = Path(r"C:\ProgramData\KONAMI\eFootball\ST\Download\dt870_console_win.cpk")
OUT = ROOT / "data" / "exports" / "efhub_card_id_lookup.csv"

CARD_IDS = {
    105679281035568: "Benjamin Pavard (efhub ID from user)",
    105874433612080: "Benjamin Pavard (earlier sample)",
    105804103532762: "Eberechi Eze",
    105874433622163: "Davide Frattesi",
    88040387119839: "Michel Platini",
    105630962666838: "Ousseynou Ba",
    53967606378420: "Ohashi Yuki",
}

# file name -> (stride, pid offset)
TABLES = {
    "Player.bin": (400, 8),
    "PlayerVariationDetail.bin": (168, 0),
    "PlayerVariationPrSkill.bin": (16, 0),
    "PlayerAppearance.bin": (64, 0),
    "BootsList.bin": (16, 0),
    "PlayerWeekly.bin": (16, 0),
}

archive = CpkArchive(CPK)
blobs = {}
for entry in archive.files:
    name = Path(entry.path.replace("\\", "/")).name
    if name in TABLES:
        blobs[name] = open_container(archive.read_file(entry))

players = {p.pid: p for p in parse_players(blobs["Player.bin"], stride=400)}

rows = []
for card_id, label in CARD_IDS.items():
    high, low = card_id >> 28, card_id & 0xFFFFFFF
    base = players.get(low)
    card = players.get(card_id)
    row = {
        "card_id": card_id,
        "card_id_hex": hex(card_id),
        "label": label,
        "variant_key_bits28plus": high,
        "base_person_id_low28": low,
        "base_player_name": base.name if base else "",
        "card_player_name": card.name if card else "",
        "card_position": card.position if card else "",
    }
    for fname, (stride, off) in TABLES.items():
        blob = blobs[fname]
        key = card_id.to_bytes(8, "little")
        hits = []
        pos = blob.find(key)
        while pos >= 0:
            if (pos - off) % stride == 0:
                hits.append((pos - off) // stride)
            pos = blob.find(key, pos + 1)
        row[f"{fname}_record_index"] = ";".join(map(str, hits))
        if fname == "PlayerVariationDetail.bin" and hits:
            rec = blob[hits[0] * stride:(hits[0] + 1) * stride]
            row["variation_flag_u32@8"] = int.from_bytes(rec[8:12], "little")
            row["variation_title"] = rec[12:].split(b"\x00", 1)[0].decode("utf-8", "replace")
            row["variation_raw_hex_0_24"] = rec[:24].hex()
        if fname == "PlayerVariationPrSkill.bin" and hits:
            rec = blob[hits[0] * stride:(hits[0] + 1) * stride]
            row["prskill_u32@8"] = int.from_bytes(rec[8:12], "little")
            row["prskill_u32@12"] = int.from_bytes(rec[12:16], "little")
            row["prskill_raw_hex"] = rec.hex()
    rows.append(row)

# Also: how many distinct high32 values exist, and how they relate to variation records
pvd = blobs["PlayerVariationDetail.bin"]
pvd_pids = {int.from_bytes(pvd[i:i + 8], "little") for i in range(0, len(pvd), 168)}
special = [pid for pid in players if pid >= 2**32]
print(f"Player.bin special cards: {len(special)}")
print(f"PlayerVariationDetail PIDs: {len(pvd_pids)}")
print(f"Special cards also in PlayerVariationDetail: {sum(1 for p in special if p in pvd_pids)}")
print(f"PlayerVariationDetail PIDs not in Player.bin: {sum(1 for p in pvd_pids if p not in players)}")
has_base = [p for p in special if (p & 0xFFFFFFF) in players]
same_name = [p for p in has_base if players[p & 0xFFFFFFF].name == players[p].name]
print(f"Special cards whose low-28-bit ID is a base card in Player.bin: {len(has_base)}")
print(f"  ...and the base card has the same player name: {len(same_name)}")

fields = []
for r in rows:
    for k in r:
        if k not in fields:
            fields.append(k)
OUT.parent.mkdir(parents=True, exist_ok=True)
with OUT.open("w", newline="", encoding="utf-8-sig") as fh:
    w = csv.DictWriter(fh, fieldnames=fields)
    w.writeheader()
    w.writerows(rows)

for r in rows:
    print()
    for k, v in r.items():
        print(f"  {k}: {v}")
print(f"\nWrote {OUT}")
