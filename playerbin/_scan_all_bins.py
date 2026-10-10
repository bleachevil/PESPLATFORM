"""Find all .bin files in weekly CPK that contain player IDs and inspect their record structures."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, r"c:\projects\pesdata")
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from importer.cpk import CpkArchive
from playerbin.container import ContainerError, open_container

CPK = Path(r"C:\ProgramData\KONAMI\eFootball\ST\Download\dt870_console_win.cpk")
archive = CpkArchive(CPK)

# Collect all pids from Player.bin first
player_bin_data = None
for entry in archive.files:
    if entry.path.replace("\\", "/").endswith("pesdb/Player.bin"):
        player_bin_data = open_container(archive.read_file(entry))
        break

pids_64 = set()
pids_32_low = set()
pids_32_high = set()

if player_bin_data:
    stride = 400
    count = len(player_bin_data) // stride
    for i in range(count):
        rec = player_bin_data[i * stride : (i + 1) * stride]
        pid = int.from_bytes(rec[8:16], "little")
        pids_64.add(pid)
        pids_32_low.add(pid & 0xFFFFFFFF)
        if pid >= 2**32:
            pids_32_high.add(pid >> 32)

print(f"Total players in Player.bin: {len(pids_64)}")

bin_summary = []

for entry in archive.files:
    if not entry.path.lower().endswith(".bin"):
        continue
    name = Path(entry.path.replace("\\", "/")).name
    try:
        blob = open_container(archive.read_file(entry))
    except Exception as e:
        continue
    if not blob:
        continue

    # Search for u64 pid matches and u32 low matches
    u64_matches = 0
    u32_low_matches = 0
    sample_matches = []

    # Check stride if fixed length
    blob_len = len(blob)

    # Search u64 pids
    for pid in list(pids_64)[:500]: # test sample of 500 pids
        needle = pid.to_bytes(8, "little")
        pos = blob.find(needle)
        if pos >= 0:
            u64_matches += 1
            if len(sample_matches) < 3:
                sample_matches.append((pid, pos))

    if u64_matches > 0:
        bin_summary.append((name, "u64", blob_len, u64_matches, sample_matches))
    else:
        # Check u32 low matches (person IDs)
        for low_id in list(pids_32_low)[:500]:
            if low_id == 0:
                continue
            needle = low_id.to_bytes(4, "little")
            pos = blob.find(needle)
            if pos >= 0:
                u32_low_matches += 1
                if len(sample_matches) < 3:
                    sample_matches.append((low_id, pos))
        if u32_low_matches > 5: # threshold to avoid random noise
            bin_summary.append((name, "u32_low", blob_len, u32_low_matches, sample_matches))

print("\n--- Summary of .bin files containing Player IDs ---")
for name, match_type, size, count_matches, samples in bin_summary:
    print(f"File: {name} (size: {size} bytes, match_type: {match_type}, sample matches count in 500: {count_matches})")
    for pid, pos in samples:
        print(f"  sample pid: {pid} at offset: {pos}")
