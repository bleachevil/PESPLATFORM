"""Generate an Excel workbook with samples from all .bin files containing Player IDs."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import xlsxwriter
from importer.cpk import CpkArchive
from playerbin.container import open_container
from playerbin.records import POSITIONS, read_bits

CPK = Path(r"C:\ProgramData\KONAMI\eFootball\ST\Download\dt870_console_win.cpk")
OUT_EXCEL = ROOT / "data" / "exports" / "player_bins_samples.xlsx"

archive = CpkArchive(CPK)

blobs = {}
for entry in archive.files:
    if not entry.path.lower().endswith(".bin"):
        continue
    name = Path(entry.path.replace("\\", "/")).name
    try:
        blob = open_container(archive.read_file(entry))
        if blob:
            blobs[name] = blob
    except Exception:
        continue

print(f"Loaded {len(blobs)} decoded .bin files.")

# Decode Team Names map
team_names: dict[int, str] = {}
teams_blob = blobs.get("Team.bin", b"")
if teams_blob:
    for at in range(0, len(teams_blob) - 388, 4):
        ident = int.from_bytes(teams_blob[at:at + 4], "little")
        if not ident or ident in team_names or ident > 100000 or teams_blob[at + 383] != 0:
            continue
        raw_name = teams_blob[at + 384:at + 448].split(b"\x00", 1)[0]
        try:
            name_str = raw_name.decode("utf-8").strip()
            if name_str and any(ch.isalpha() for ch in name_str):
                team_names[ident] = name_str
        except Exception:
            pass

# Target specific sample players (including Pavard, Eze, Frattesi, Platini, Ba, Ohashi)
TARGET_PIDS = [
    105874433612080, # Pavard Special
    104752,          # Pavard Base
    105804103532762, # Eze Special
    114906,          # Eze Base
    105874433622163, # Frattesi Special
    114835,          # Frattesi Base
    88040387119839,  # Platini Special
    105630962666838, # Ba Special
    118102,          # Ba Base
    53967606378420,  # Ohashi Special
    126900,          # Ohashi Base
]

def person_name(rec: bytes) -> str:
    parts = []
    for slot in range(5):
        chunk = rec[88 + slot * 61 : 88 + (slot + 1) * 61]
        text = chunk.split(b"\x00", 1)[0].decode("utf-8", "replace").strip()
        if text and any(ch.isascii() and ch.islower() for ch in text):
            parts.append(text)
    return max(parts, key=len) if parts else ""

# Helper to write sheet
workbook = xlsxwriter.Workbook(str(OUT_EXCEL))
header_format = workbook.add_format({
    "bold": True,
    "bg_color": "#1F4E78",
    "font_color": "#FFFFFF",
    "border": 1,
    "align": "center",
    "valign": "vcenter",
})
cell_format = workbook.add_format({"border": 1, "valign": "vcenter"})
num_format = workbook.add_format({"border": 1, "align": "right", "valign": "vcenter"})

# 1. Sheet: Player.bin
player_blob = blobs.get("Player.bin", b"")
if player_blob:
    sheet = workbook.add_worksheet("Player.bin")
    headers = [
        "Player ID (u64)", "Person ID (u32)", "Card Type", "Player Name",
        "Position", "Team Name", "Team ID", "Height (cm)", "Weight (kg)",
        "Age", "Foot", "Weak Foot Usage", "Weak Foot Accuracy", "Form", "Injury Resistance",
        "Contract Date", "Playing Style Code"
    ]
    for col, h in enumerate(headers):
        sheet.write(0, col, h, header_format)

    row_idx = 1
    stride = 400
    total_count = len(player_blob) // stride

    # Write target PIDs first
    written_pids = set()
    for pid in TARGET_PIDS:
        pos = player_blob.find(pid.to_bytes(8, "little"))
        if pos >= 0:
            rec = player_blob[pos - 8 : pos + 392]
            p_id = int.from_bytes(rec[8:16], "little")
            written_pids.add(p_id)
            t_id = int.from_bytes(rec[16:20], "little")
            sheet.write(row_idx, 0, p_id, num_format)
            sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
            sheet.write(row_idx, 2, "Special Card" if p_id >= 2**32 else "Base Card", cell_format)
            sheet.write(row_idx, 3, person_name(rec), cell_format)
            sheet.write(row_idx, 4, POSITIONS.get(read_bits(rec, 556, 4), ""), cell_format)
            sheet.write(row_idx, 5, team_names.get(t_id, ""), cell_format)
            sheet.write(row_idx, 6, t_id, num_format)
            sheet.write(row_idx, 7, read_bits(rec, 248, 8) + 100, num_format)
            sheet.write(row_idx, 8, read_bits(rec, 280, 7) + 30, num_format)
            sheet.write(row_idx, 9, read_bits(rec, 536, 6) + 10, num_format)
            sheet.write(row_idx, 10, "Left" if read_bits(rec, 654, 1) == 1 else "Right", cell_format)
            sheet.write(row_idx, 11, read_bits(rec, 478, 2), num_format)
            sheet.write(row_idx, 12, read_bits(rec, 578, 2), num_format)
            sheet.write(row_idx, 13, read_bits(rec, 582, 2), num_format)
            sheet.write(row_idx, 14, read_bits(rec, 542, 2), num_format)
            sheet.write(row_idx, 15, read_bits(rec, 160, 25) or "", cell_format)
            sheet.write(row_idx, 16, read_bits(rec, 374, 6), num_format)
            row_idx += 1

    # Write additional general sample rows up to 100 rows
    for i in range(min(total_count, 100)):
        rec = player_blob[i * stride : (i + 1) * stride]
        p_id = int.from_bytes(rec[8:16], "little")
        if p_id in written_pids:
            continue
        written_pids.add(p_id)
        t_id = int.from_bytes(rec[16:20], "little")
        sheet.write(row_idx, 0, p_id, num_format)
        sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
        sheet.write(row_idx, 2, "Special Card" if p_id >= 2**32 else "Base Card", cell_format)
        sheet.write(row_idx, 3, person_name(rec), cell_format)
        sheet.write(row_idx, 4, POSITIONS.get(read_bits(rec, 556, 4), ""), cell_format)
        sheet.write(row_idx, 5, team_names.get(t_id, ""), cell_format)
        sheet.write(row_idx, 6, t_id, num_format)
        sheet.write(row_idx, 7, read_bits(rec, 248, 8) + 100, num_format)
        sheet.write(row_idx, 8, read_bits(rec, 280, 7) + 30, num_format)
        sheet.write(row_idx, 9, read_bits(rec, 536, 6) + 10, num_format)
        sheet.write(row_idx, 10, "Left" if read_bits(rec, 654, 1) == 1 else "Right", cell_format)
        sheet.write(row_idx, 11, read_bits(rec, 478, 2), num_format)
        sheet.write(row_idx, 12, read_bits(rec, 578, 2), num_format)
        sheet.write(row_idx, 13, read_bits(rec, 582, 2), num_format)
        sheet.write(row_idx, 14, read_bits(rec, 542, 2), num_format)
        sheet.write(row_idx, 15, read_bits(rec, 160, 25) or "", cell_format)
        sheet.write(row_idx, 16, read_bits(rec, 374, 6), num_format)
        row_idx += 1

    sheet.autofit()

# 2. Sheet: PlayerVariationDetail.bin
var_blob = blobs.get("PlayerVariationDetail.bin", b"")
if var_blob:
    sheet = workbook.add_worksheet("PlayerVariationDetail.bin")
    headers = ["Player ID (u64)", "Person ID (u32)", "Category / Flag", "Card Title / Pack Name"]
    for col, h in enumerate(headers):
        sheet.write(0, col, h, header_format)

    row_idx = 1
    stride = 168
    total_count = len(var_blob) // stride
    written_pids = set()

    for pid in TARGET_PIDS:
        pos = var_blob.find(pid.to_bytes(8, "little"))
        if pos >= 0 and pos % stride == 0:
            rec = var_blob[pos : pos + stride]
            p_id = int.from_bytes(rec[0:8], "little")
            written_pids.add(p_id)
            flag = int.from_bytes(rec[8:12], "little")
            title = rec[12:].split(b"\x00", 1)[0].decode("utf-8", "replace")
            sheet.write(row_idx, 0, p_id, num_format)
            sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
            sheet.write(row_idx, 2, flag, num_format)
            sheet.write(row_idx, 3, title, cell_format)
            row_idx += 1

    for i in range(min(total_count, 100)):
        rec = var_blob[i * stride : (i + 1) * stride]
        p_id = int.from_bytes(rec[0:8], "little")
        if p_id in written_pids:
            continue
        written_pids.add(p_id)
        flag = int.from_bytes(rec[8:12], "little")
        title = rec[12:].split(b"\x00", 1)[0].decode("utf-8", "replace")
        sheet.write(row_idx, 0, p_id, num_format)
        sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
        sheet.write(row_idx, 2, flag, num_format)
        sheet.write(row_idx, 3, title, cell_format)
        row_idx += 1

    sheet.autofit()

# 3. Sheet: PlayerAppearance.bin
app_blob = blobs.get("PlayerAppearance.bin", b"")
if app_blob:
    sheet = workbook.add_worksheet("PlayerAppearance.bin")
    headers = ["Player ID (u64)", "Person ID (u32)", "Appearance Data Hex (64 Bytes)"]
    for col, h in enumerate(headers):
        sheet.write(0, col, h, header_format)

    row_idx = 1
    stride = 64
    total_count = len(app_blob) // stride
    written_pids = set()

    for pid in TARGET_PIDS:
        pos = app_blob.find(pid.to_bytes(8, "little"))
        if pos >= 0 and pos % stride == 0:
            rec = app_blob[pos : pos + stride]
            p_id = int.from_bytes(rec[0:8], "little")
            written_pids.add(p_id)
            sheet.write(row_idx, 0, p_id, num_format)
            sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
            sheet.write(row_idx, 2, rec[8:].hex(), cell_format)
            row_idx += 1

    for i in range(min(total_count, 100)):
        rec = app_blob[i * stride : (i + 1) * stride]
        p_id = int.from_bytes(rec[0:8], "little")
        if p_id in written_pids:
            continue
        written_pids.add(p_id)
        sheet.write(row_idx, 0, p_id, num_format)
        sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
        sheet.write(row_idx, 2, rec[8:].hex(), cell_format)
        row_idx += 1

    sheet.autofit()

# 4. Sheet: BootsList.bin
boots_blob = blobs.get("BootsList.bin", b"")
if boots_blob:
    sheet = workbook.add_worksheet("BootsList.bin")
    headers = ["Player ID (u64)", "Person ID (u32)", "Boot ID (u32)"]
    for col, h in enumerate(headers):
        sheet.write(0, col, h, header_format)

    row_idx = 1
    stride = 16
    total_count = len(boots_blob) // stride
    written_pids = set()

    for pid in TARGET_PIDS:
        pos = boots_blob.find(pid.to_bytes(8, "little"))
        if pos >= 0 and pos % stride == 0:
            rec = boots_blob[pos : pos + stride]
            p_id = int.from_bytes(rec[0:8], "little")
            written_pids.add(p_id)
            boot_id = int.from_bytes(rec[8:12], "little")
            sheet.write(row_idx, 0, p_id, num_format)
            sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
            sheet.write(row_idx, 2, boot_id, num_format)
            row_idx += 1

    for i in range(min(total_count, 100)):
        rec = boots_blob[i * stride : (i + 1) * stride]
        p_id = int.from_bytes(rec[0:8], "little")
        if p_id in written_pids:
            continue
        written_pids.add(p_id)
        boot_id = int.from_bytes(rec[8:12], "little")
        sheet.write(row_idx, 0, p_id, num_format)
        sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
        sheet.write(row_idx, 2, boot_id, num_format)
        row_idx += 1

    sheet.autofit()

# 5. Sheet: PlayerVariationPrSkill.bin
prskill_blob = blobs.get("PlayerVariationPrSkill.bin", b"")
if prskill_blob:
    sheet = workbook.add_worksheet("PlayerVariationPrSkill.bin")
    headers = ["Player ID (u64)", "Person ID (u32)", "Skill Param 1 (u32)", "Skill Param 2 (u32)"]
    for col, h in enumerate(headers):
        sheet.write(0, col, h, header_format)

    row_idx = 1
    stride = 16
    total_count = len(prskill_blob) // stride
    written_pids = set()

    for pid in TARGET_PIDS:
        pos = prskill_blob.find(pid.to_bytes(8, "little"))
        if pos >= 0 and pos % stride == 0:
            rec = prskill_blob[pos : pos + stride]
            p_id = int.from_bytes(rec[0:8], "little")
            written_pids.add(p_id)
            param1 = int.from_bytes(rec[8:12], "little")
            param2 = int.from_bytes(rec[12:16], "little")
            sheet.write(row_idx, 0, p_id, num_format)
            sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
            sheet.write(row_idx, 2, param1, num_format)
            sheet.write(row_idx, 3, param2, num_format)
            row_idx += 1

    for i in range(min(total_count, 100)):
        rec = prskill_blob[i * stride : (i + 1) * stride]
        p_id = int.from_bytes(rec[0:8], "little")
        if p_id in written_pids:
            continue
        written_pids.add(p_id)
        param1 = int.from_bytes(rec[8:12], "little")
        param2 = int.from_bytes(rec[12:16], "little")
        sheet.write(row_idx, 0, p_id, num_format)
        sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
        sheet.write(row_idx, 2, param1, num_format)
        sheet.write(row_idx, 3, param2, num_format)
        row_idx += 1

    sheet.autofit()

# 6. Sheet: PlayerWeekly.bin
weekly_blob = blobs.get("PlayerWeekly.bin", b"")
if weekly_blob:
    sheet = workbook.add_worksheet("PlayerWeekly.bin")
    headers = ["Player ID (u64)", "Person ID (u32)", "Weekly Flag 1 (u32)", "Weekly Flag 2 (u32)"]
    for col, h in enumerate(headers):
        sheet.write(0, col, h, header_format)

    row_idx = 1
    stride = 16
    total_count = len(weekly_blob) // stride
    written_pids = set()

    for pid in TARGET_PIDS:
        pos = weekly_blob.find(pid.to_bytes(8, "little"))
        if pos >= 0 and pos % stride == 0:
            rec = weekly_blob[pos : pos + stride]
            p_id = int.from_bytes(rec[0:8], "little")
            written_pids.add(p_id)
            param1 = int.from_bytes(rec[8:12], "little")
            param2 = int.from_bytes(rec[12:16], "little")
            sheet.write(row_idx, 0, p_id, num_format)
            sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
            sheet.write(row_idx, 2, param1, num_format)
            sheet.write(row_idx, 3, param2, num_format)
            row_idx += 1

    for i in range(min(total_count, 100)):
        rec = weekly_blob[i * stride : (i + 1) * stride]
        p_id = int.from_bytes(rec[0:8], "little")
        if p_id in written_pids:
            continue
        written_pids.add(p_id)
        param1 = int.from_bytes(rec[8:12], "little")
        param2 = int.from_bytes(rec[12:16], "little")
        sheet.write(row_idx, 0, p_id, num_format)
        sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
        sheet.write(row_idx, 2, param1, num_format)
        sheet.write(row_idx, 3, param2, num_format)
        row_idx += 1

    sheet.autofit()

# 7. Sheet: GloveList.bin
glove_blob = blobs.get("GloveList.bin", b"")
if glove_blob:
    sheet = workbook.add_worksheet("GloveList.bin")
    headers = ["Player ID (u64)", "Person ID (u32)", "Glove ID (u32)"]
    for col, h in enumerate(headers):
        sheet.write(0, col, h, header_format)

    row_idx = 1
    stride = 16
    total_count = len(glove_blob) // stride

    for i in range(min(total_count, 100)):
        rec = glove_blob[i * stride : (i + 1) * stride]
        p_id = int.from_bytes(rec[0:8], "little")
        glove_id = int.from_bytes(rec[8:12], "little")
        sheet.write(row_idx, 0, p_id, num_format)
        sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
        sheet.write(row_idx, 2, glove_id, num_format)
        row_idx += 1

    sheet.autofit()

# 8. Sheet: PlayerAssignment.bin
assign_blob = blobs.get("PlayerAssignment.bin", b"")
if assign_blob:
    sheet = workbook.add_worksheet("PlayerAssignment.bin")
    headers = ["Record ID (u64)", "Player ID / Ref (u32)", "Squad / Assignment Data Hex"]
    for col, h in enumerate(headers):
        sheet.write(0, col, h, header_format)

    row_idx = 1
    stride = 24
    total_count = len(assign_blob) // stride

    for i in range(min(total_count, 100)):
        rec = assign_blob[i * stride : (i + 1) * stride]
        rec_id = int.from_bytes(rec[0:8], "little")
        p_id = int.from_bytes(rec[8:12], "little")
        sheet.write(row_idx, 0, rec_id, num_format)
        sheet.write(row_idx, 1, p_id, num_format)
        sheet.write(row_idx, 2, rec[12:].hex(), cell_format)
        row_idx += 1

    sheet.autofit()

# 9. Sheet: PlayerDeleteList.bin
del_blob = blobs.get("PlayerDeleteList.bin", b"")
if del_blob:
    sheet = workbook.add_worksheet("PlayerDeleteList.bin")
    headers = ["Deleted Player ID (u64)", "Person ID (u32)"]
    for col, h in enumerate(headers):
        sheet.write(0, col, h, header_format)

    row_idx = 1
    stride = 16
    total_count = len(del_blob) // stride

    for i in range(min(total_count, 100)):
        rec = del_blob[i * stride : (i + 1) * stride]
        p_id = int.from_bytes(rec[0:8], "little")
        sheet.write(row_idx, 0, p_id, num_format)
        sheet.write(row_idx, 1, p_id & 0xFFFFFFFF, num_format)
        row_idx += 1

    sheet.autofit()

workbook.close()
print(f"Successfully generated Excel workbook at: {OUT_EXCEL}")
