"""Locate the installed eFootball live-update database."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

STEAM_EFOOTBALL = Path(r"C:\Program Files (x86)\Steam\steamapps\common\eFootball")
LIVE_DOWNLOAD = Path(r"C:\ProgramData\KONAMI\eFootball\ST\Download")

ENCRYPTED_WESYS = b"WESYS"


@dataclass
class GameFiles:
    install_dir: Path | None
    live_cpk: Path | None
    base_cpk: Path | None
    live_cpk_mtime: str | None


def find_game_files() -> GameFiles:
    install = STEAM_EFOOTBALL if STEAM_EFOOTBALL.exists() else None
    live = LIVE_DOWNLOAD / "dt870_console_win.cpk"
    base = STEAM_EFOOTBALL / "cpk" / "dt870_console_win.cpk"
    live_path = live if live.exists() else None
    base_path = base if base.exists() else None
    mtime = None
    if live_path:
        mtime = live_path.stat().st_mtime
        from datetime import datetime

        mtime = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    return GameFiles(
        install_dir=install,
        live_cpk=live_path,
        base_cpk=base_path,
        live_cpk_mtime=mtime,
    )


def is_encrypted_wesys(data: bytes) -> bool:
    """eFootball 2027 v6 wraps pesdb files in an encrypted WESYS container."""
    if data.startswith(b"WESYS"):
        return False
    return ENCRYPTED_WESYS in data[:12] and data[:1] == b"\xff"
