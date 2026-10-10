"""Determine strides, column definitions, and row parsers for all player-related .bin files."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, r"c:\projects\pesdata")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from importer.cpk import CpkArchive
from playerbin.container import ContainerError, open_container
from playerbin.records import POSITIONS, read_bits

CPK = Path(r"C:\ProgramData\KONAMI\eFootball\ST\Download\dt870_console_win.cpk")
archive = CpkArchive(CPK)

PLAYER_BINS = [
    "Player.bin",
    "PlayerVariationDetail.bin",
    "PlayerAppearance.bin",
    "PlayerVariationPrSkill.bin",
    "PlayerWeekly.bin",
    "BootsList.bin",
    "GloveList.bin",
    "PlayerAssignment.bin",
    "PlayerDeleteList.bin",
    "SpecialPlayerAssignment.bin",
    "PlayerBooster.bin",
]

for entry in archive.files:
    name = Path(entry.path.replace("\\", "/")).name
    if name not in PLAYER_BINS:
        continue
    try:
        blob = open_container(archive.read_file(entry))
    except Exception as e:
        print(f"Error opening {name}: {e}")
        continue

    print(f"\n================ {name} (size: {len(blob)} bytes) ================")
    # Find candidate strides
    possible_strides = []
    for s in [8, 12, 16, 24, 32, 48, 64, 128, 168, 200, 392, 400]:
        if len(blob) % s == 0:
            possible_strides.append(s)
    print(f"Possible strides (len % s == 0): {possible_strides}")

    # Inspect first 3 records for candidate strides
    for s in possible_strides:
        count = len(blob) // s
        if count == 0:
            continue
        rec0 = blob[0:s]
        rec1 = blob[s:2*s] if count > 1 else b""
        p0_u64 = int.from_bytes(rec0[:8], "little")
        p0_u32 = int.from_bytes(rec0[:4], "little")
        p0_u64_off8 = int.from_bytes(rec0[8:16], "little") if s >= 16 else 0
        print(f"  stride {s} (count: {count}):")
        print(f"    rec0 hex: {rec0[:32].hex()}")
        print(f"    u64@0: {p0_u64}, u32@0: {p0_u32}, u64@8: {p0_u64_off8}")
