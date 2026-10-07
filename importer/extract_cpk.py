from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from importer.cpk import CpkArchive
from importer.locate import find_game_files, is_encrypted_wesys
from importer.wesys import decompress_wesys, is_wesys

OUT = ROOT / "data" / "extracted"


def main() -> None:
    files = find_game_files()
    cpk_path = files.live_cpk or files.base_cpk
    if not cpk_path:
        print("No dt870_console_win.cpk found.")
        sys.exit(1)
    print(f"Using {cpk_path} (live update {files.live_cpk_mtime or 'n/a'})")
    cpk = CpkArchive(cpk_path)
    print(f"files={len(cpk.files)} toc={cpk.toc_offset} content={cpk.content_offset}")
    OUT.mkdir(parents=True, exist_ok=True)
    encrypted = 0
    for entry in cpk.files:
        raw = cpk.read_file(entry)
        if is_encrypted_wesys(raw):
            kind = "enc"
            payload = raw
            encrypted += 1
        elif is_wesys(raw):
            kind = "wesys"
            payload = decompress_wesys(raw)
        else:
            kind = "raw"
            payload = raw
        dest = OUT / entry.path.replace("\\", "/")
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(payload)
        print(f"{entry.path:50} {kind:5} {entry.size:8} -> {len(payload):8}")
    print(f"\nExtracted {len(cpk.files)} files, {encrypted} still encrypted WESYS.")
    if encrypted:
        print("Import a CSV from a Player.bin editor instead of parsing these bins.")


if __name__ == "__main__":
    main()
