"""Open Player.bin from a local eFootball CPK and print a few players."""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from importer.cpk import CpkArchive

from playerbin.container import ContainerError, open_container
from playerbin.records import choose_stride, parse_players

DEFAULTS = [
    Path(r"C:\ProgramData\KONAMI\eFootball\ST\Download\dt870_console_win.cpk"),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\eFootball\cpk\dt200_console_all.cpk"),
    Path(r"C:\Program Files (x86)\Steam\steamapps\common\eFootball\cpk\dt870_console_win.cpk"),
]

PROBES = ("Messi", "Haaland", "Salah", "Mbapp")


def _player_blob(path: Path) -> bytes:
    if path.suffix.lower() == ".bin":
        return path.read_bytes()
    archive = CpkArchive(path)
    for entry in archive.files:
        if entry.path.replace("\\", "/").endswith("common/etc/pesdb/Player.bin"):
            return archive.read_file(entry)
    raise FileNotFoundError(f"no Player.bin inside {path}")


def _show(path: Path) -> None:
    print("=" * 72)
    print(path)
    blob = _player_blob(path)
    print(f"wrapped {len(blob):,} bytes  head={blob[:16].hex()}")
    try:
        table = open_container(blob)
    except ContainerError as exc:
        print(f"FAILED  {exc}")
        return
    stride = choose_stride(table)
    players = parse_players(table, stride)
    named = sum(1 for player in players if player.name)
    print(f"opened  {len(table):,} bytes  stride={stride}  players={len(players):,}  named={named:,}")
    ascending = all(players[i].pid <= players[i + 1].pid for i in range(len(players) - 1))
    print(f"pids ascending={ascending}  first={players[0].pid} {players[0].name!r} {players[0].position}")
    for needle in PROBES:
        found = next((player for player in players if needle.lower() in player.name.lower()), None)
        if found is None:
            print(f"  {needle}: not in the latin name")
            continue
        finish = found.abilities["finishing"]
        speed = found.abilities["speed"]
        print(
            f"  {found.name}  pid={found.pid}  {found.position}  "
            f"age={found.age}  {found.height}cm  ovr~{found.overall}  "
            f"fin={finish} spd={speed}"
        )
        print("    names=" + " | ".join(found.names))
        ordered = ", ".join(f"{key}={value}" for key, value in found.abilities.items())
        print(f"    {ordered}")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    paths = [Path(arg) for arg in sys.argv[1:]] or DEFAULTS
    for path in paths:
        if not path.exists():
            print(f"missing {path}")
            continue
        _show(path)


if __name__ == "__main__":
    main()
