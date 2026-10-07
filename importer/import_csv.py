"""Import an eFootball player CSV (RBsGameLab editor export or compatible)."""

from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from importer.fields import ABILITY_KEYS, CSV_ALIASES, POSITIONS
from importer.card_art import store_imported_image
from importer.growth import default_max_level, default_max_overall, default_level
from importer.league import init_league_db

DB_PATH = ROOT / "data" / "pesdata.sqlite"
SCHEMA_PATH = Path(__file__).with_name("schema.sql")
EXPORT_PATH = ROOT / "data" / "exports" / "players.csv"
PLAYER_LIST_COLUMNS = [
    ("PlayerID", "pid"),
    ("Name", "name"),
    ("Position", "position"),
    ("Club", "club"),
    ("Pack", "pack_name"),
    ("Nation", "nationality"),
    ("Overall", "overall"),
    ("MaxLevel", "max_level"),
    ("MaxOverall", "max_overall"),
    ("Mode", "mode"),
    ("Link", "source_url"),
]
PLAYER_NEW_COLUMNS = [
    ("mode", "TEXT NOT NULL DEFAULT 'dream-team'"),
    ("pack_name", "TEXT"),
    ("pack_date", "TEXT"),
    ("squad_number", "INTEGER"),
    ("team_slug", "TEXT"),
    ("image", "TEXT"),
    ("level", "INTEGER DEFAULT 1"),
    ("max_level", "INTEGER"),
    ("source_url", "TEXT"),
]
PESDB_BASE = "https://pesdb.net"


def _norm(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", name.strip().lower())


def slugify(value: str, fallback: str = "item") -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return base or fallback


def player_slug(name: str, pid: str) -> str:
    return f"{slugify(name, 'player')}-{pid}"


def pesdb_player_url(pid: str = "", mode: str = "dream-team", slug: str = "", source_url: str = "") -> str:
    if source_url:
        return str(source_url).strip()
    pid = str(pid or "").strip()
    slug = str(slug or "").strip()
    if slug and pid and slug.endswith(pid):
        path = "/efootball/authentic/players/" if (mode or "") == "authentic" else "/efootball/players/"
        return f"{PESDB_BASE}{path}{slug}"
    if pid:
        return f"{PESDB_BASE}/efootball/?id={quote(pid)}"
    return ""


def normalize_mode(value: str | None, card_type: str = "", pack_name: str = "") -> str:
    text = f"{value or ''} {card_type or ''}".strip().lower().replace("_", "-").replace(" ", "-")
    if "authentic" in text or text in {"auth", "offline"}:
        return "authentic"
    if "dream" in text or text in {"dt", "online"}:
        return "dream-team"
    if pack_name:
        return "dream-team"
    return "dream-team"


def _map_header(fieldnames: list[str]) -> dict[str, str]:
    lookup = {_norm(src): src for src in fieldnames}
    mapping: dict[str, str] = {}
    for dest, aliases in CSV_ALIASES.items():
        for alias in aliases:
            if alias in lookup:
                mapping[dest] = lookup[alias]
                break
    return mapping


def _int(value: str | None, default: int | None = None) -> int | None:
    if value is None or str(value).strip() == "":
        return default
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return default


def _text(value: str | None, default: str = "") -> str:
    if value is None:
        return default
    return str(value).strip()


def _split_list(value: str | None) -> list[str]:
    if not value:
        return []
    parts = re.split(r"[|;,/]+", value)
    return [p.strip() for p in parts if p.strip()]


def _estimate_overall(row: dict) -> int:
    pos = (row.get("position") or "CF").upper()
    keys = {
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
    }.get(pos, ["offensive_awareness", "ball_control", "speed"])
    vals = [int(row[k]) for k in keys if row.get(k) is not None]
    return int(round(sum(vals) / len(vals))) if vals else 70


def init_db(db_path: Path = DB_PATH) -> sqlite3.Connection:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    init_league_db(conn)
    existing = {row[1] for row in conn.execute("PRAGMA table_info(players)")}
    for column, spec in PLAYER_NEW_COLUMNS:
        if column not in existing:
            conn.execute(f"ALTER TABLE players ADD COLUMN {column} {spec}")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_players_mode ON players(mode)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_players_team ON players(team_slug)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_players_pack ON players(pack_name)")
    conn.commit()
    return conn


def rebuild_derived(conn: sqlite3.Connection) -> None:
    conn.execute("DELETE FROM teams")
    conn.execute("DELETE FROM packs")
    conn.execute("DELETE FROM pack_players")
    clubs = conn.execute(
        "SELECT DISTINCT club, league, region FROM players WHERE club IS NOT NULL AND club != ''"
    )
    for row in clubs:
        slug = slugify(row["club"])
        conn.execute(
            "INSERT OR REPLACE INTO teams(slug, name, league, region) VALUES (?, ?, ?, ?)",
            (slug, row["club"], row["league"] or "", row["region"] or ""),
        )
        conn.execute("UPDATE players SET team_slug = ? WHERE club = ?", (slug, row["club"]))
    packs = conn.execute(
        """
        SELECT pack_name, MAX(pack_date) AS pack_date
        FROM players
        WHERE pack_name IS NOT NULL AND pack_name != ''
        GROUP BY pack_name
        """
    )
    for row in packs:
        slug = slugify(row["pack_name"])
        conn.execute(
            "INSERT OR REPLACE INTO packs(slug, name, released_on, kind) VALUES (?, ?, ?, ?)",
            (slug, row["pack_name"], row["pack_date"] or "", "Special Player List"),
        )
        members = conn.execute(
            "SELECT pid FROM players WHERE pack_name = ?",
            (row["pack_name"],),
        )
        conn.executemany(
            "INSERT OR IGNORE INTO pack_players(pack_slug, player_pid) VALUES (?, ?)",
            [(slug, member["pid"]) for member in members],
        )


def import_records(records: list[dict], db_path: Path = DB_PATH, source: str = "records") -> dict:
    conn = init_db(db_path)
    imported = 0
    with conn:
        conn.execute("DELETE FROM pack_players")
        conn.execute("DELETE FROM packs")
        conn.execute("DELETE FROM teams")
        conn.execute("DELETE FROM players")
        for record in records:
            name = record.get("name") or ""
            if not name:
                continue
            pid = str(record.get("pid") or imported + 1)
            abilities = {key: int(record.get(key) or 40) for key in ABILITY_KEYS}
            overall = record.get("overall")
            pack_name = record.get("pack_name") or ""
            card_type = record.get("card_type") or ("Standard" if not pack_name else "Featured")
            skills = record.get("skills") or []
            ai_styles = record.get("ai_styles") or []
            if isinstance(skills, str):
                skills = _split_list(skills)
            if isinstance(ai_styles, str):
                ai_styles = _split_list(ai_styles)
            image_val = record.get("image") or ""
            stored_image = ""
            if image_val:
                stored_image = store_imported_image(pid, image_val) or image_val
            payload = {
                "pid": pid,
                "name": name,
                "slug": player_slug(name, pid),
                "position": (record.get("position") or "CF").upper(),
                "card_type": card_type,
                "mode": normalize_mode(record.get("mode"), card_type, pack_name),
                "pack_name": pack_name,
                "pack_date": record.get("pack_date") or "",
                "squad_number": record.get("squad_number"),
                "team_slug": slugify(record.get("club") or "") if record.get("club") else "",
                "overall": overall,
                "max_overall": record.get("max_overall"),
                "height": record.get("height"),
                "weight": record.get("weight"),
                "age": record.get("age"),
                "foot": record.get("foot") or "",
                "weak_foot_usage": record.get("weak_foot_usage") or "",
                "weak_foot_accuracy": record.get("weak_foot_accuracy") or "",
                "form": record.get("form") or "",
                "injury_resistance": record.get("injury_resistance") or "",
                "nationality": record.get("nationality") or "",
                "region": record.get("region") or "",
                "club": record.get("club") or "",
                "league": record.get("league") or "",
                "source_url": pesdb_player_url(
                    pid,
                    normalize_mode(record.get("mode"), card_type, pack_name),
                    record.get("slug") or player_slug(name, pid),
                    record.get("source_url") or "",
                ),
                "image": stored_image,
                "att_style": record.get("att_style") or "",
                "def_style": record.get("def_style") or "",
                "skills": json.dumps(skills),
                "ai_styles": json.dumps(ai_styles),
                **abilities,
            }
            if payload["overall"] is None:
                payload["overall"] = _estimate_overall(payload)
            payload["max_overall"] = payload["max_overall"] or default_max_overall(
                payload["mode"], payload["card_type"], payload["overall"]
            )
            payload["level"] = int(record.get("level") or default_level())
            payload["max_level"] = int(record.get("max_level") or default_max_level(payload["mode"], payload["card_type"]))
            if payload["position"] not in POSITIONS:
                payload["position"] = "CF"
            cols = ", ".join(payload.keys())
            placeholders = ", ".join(f":{k}" for k in payload)
            conn.execute(f"INSERT INTO players ({cols}) VALUES ({placeholders})", payload)
            imported += 1
        rebuild_derived(conn)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        extra = [
            ("imported_at", now),
            ("source", source),
            ("row_count", str(imported)),
        ]
        conn.executemany("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", extra)
    conn.close()
    return {"imported": imported}


def import_csv(csv_path: Path, db_path: Path = DB_PATH, source: str = "csv") -> dict:
    with csv_path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if not reader.fieldnames:
            raise ValueError("CSV has no header row")
        mapping = _map_header(list(reader.fieldnames))
        if "name" not in mapping:
            raise ValueError("CSV needs a Name column")
        records = []
        for raw in reader:
            record = {dest: _text(raw.get(src)) for dest, src in mapping.items()}
            for key in ABILITY_KEYS + ["overall", "max_overall", "height", "weight", "age", "squad_number", "level", "max_level"]:
                if key in record:
                    record[key] = _int(record.get(key))
            record["skills"] = _split_list(record.get("skills"))
            record["ai_styles"] = _split_list(record.get("ai_styles"))
            records.append(record)
    result = import_records(records, db_path=db_path, source=source)
    result["columns"] = sorted(mapping.keys())
    result["csv_name"] = csv_path.name
    conn = sqlite3.connect(db_path)
    conn.execute("INSERT OR REPLACE INTO meta(key, value) VALUES (?, ?)", ("csv_name", csv_path.name))
    conn.commit()
    conn.close()
    return result


def _player_list_rows(conn: sqlite3.Connection, mode: str | None = None) -> list[sqlite3.Row]:
    sql = "SELECT name, position, club, pack_name, nationality, overall, max_level, max_overall, mode, source_url, pid, slug FROM players"
    params: list = []
    if mode:
        sql += " WHERE mode = ?"
        params.append(mode)
    sql += " ORDER BY overall DESC, name COLLATE NOCASE"
    return list(conn.execute(sql, params))


def write_player_list_csv(rows, dest: Path | None = None) -> Path:
    dest = dest or EXPORT_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    with dest.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow([label for label, _key in PLAYER_LIST_COLUMNS])
        for row in rows:
            data = dict(row) if not isinstance(row, dict) else row
            writer.writerow(
                [
                    pesdb_player_url(
                        data.get("pid") or "",
                        data.get("mode") or "dream-team",
                        data.get("slug") or "",
                        data.get("source_url") or "",
                    )
                    if key == "source_url"
                    else (data.get(key) or "")
                    for _label, key in PLAYER_LIST_COLUMNS
                ]
            )
    return dest


def export_player_list(db_path: Path = DB_PATH, dest: Path | None = None, mode: str | None = None) -> Path:
    conn = init_db(db_path)
    rows = _player_list_rows(conn, mode=mode)
    dest = write_player_list_csv(rows, dest)
    conn.close()
    return dest


def main() -> None:
    if len(sys.argv) < 2:
        print("Usage: py -3.9 importer/import_csv.py <players.csv>")
        print("       py -3.9 importer/import_csv.py --export [out.csv]")
        sys.exit(1)
    if sys.argv[1] in {"--export", "-e"}:
        dest = Path(sys.argv[2]) if len(sys.argv) > 2 else EXPORT_PATH
        path = export_player_list(dest=dest)
        print(f"Wrote player list to {path}")
        return
    path = Path(sys.argv[1])
    result = import_csv(path, source=f"csv:{path.name}")
    print(f"Imported {result['imported']} players from {path}")
    print("Mapped columns:", ", ".join(result["columns"]))


if __name__ == "__main__":
    main()
