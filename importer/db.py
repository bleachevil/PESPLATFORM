"""SQLite locally, Postgres (Cloud SQL) when DATABASE_URL is set."""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SQLITE = ROOT / "data" / "pesdata.sqlite"
SCHEMA_SQLITE = Path(__file__).with_name("schema.sql")
SCHEMA_PG = Path(__file__).with_name("schema_pg.sql")
LEAGUE_SQLITE = Path(__file__).with_name("league_schema.sql")
LEAGUE_PG = Path(__file__).with_name("league_schema_pg.sql")

UPSERT_KEYS = {
    "teams": "slug",
    "packs": "slug",
    "meta": "key",
}


class Row(dict):
    def __init__(self, mapping: dict[str, Any], values: Sequence[Any] | None = None):
        super().__init__(mapping)
        self._values = list(values) if values is not None else list(mapping.values())

    def __getitem__(self, key: Any) -> Any:
        if isinstance(key, int):
            return self._values[key]
        return super().__getitem__(key)


class Result:
    def __init__(self, rows: list[Row]):
        self._rows = rows

    def fetchone(self) -> Row | None:
        return self._rows[0] if self._rows else None

    def fetchall(self) -> list[Row]:
        return list(self._rows)

    def __iter__(self) -> Iterator[Row]:
        return iter(self._rows)


def _load_env_file() -> None:
    path = ROOT / ".env"
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_env_file()


def database_url() -> str:
    return (
        os.environ.get("DATABASE_URL")
        or os.environ.get("POSTGRES_URL")
        or ""
    ).strip()


def is_postgres() -> bool:
    url = database_url()
    if url.startswith("postgres"):
        return True
    if os.environ.get("CLOUD_SQL_CONNECTION_NAME"):
        return True
    return False


def postgres_url() -> str:
    url = database_url()
    if url:
        if url.startswith("postgres://"):
            url = "postgresql://" + url[len("postgres://") :]
        return url
    instance = os.environ.get("CLOUD_SQL_CONNECTION_NAME", "").strip()
    user = os.environ.get("DB_USER", "").strip()
    password = os.environ.get("DB_PASSWORD", "").strip()
    name = os.environ.get("DB_NAME", "pesdata").strip() or "pesdata"
    if not instance or not user:
        raise ValueError("Set DATABASE_URL or CLOUD_SQL_CONNECTION_NAME + DB_USER + DB_PASSWORD + DB_NAME")
    return f"postgresql://{user}:{password}@/{name}?host=/cloudsql/{instance}"


def _rewrite_pg(sql: str) -> str:
    text = sql.strip()
    pragma = re.match(r"PRAGMA table_info\((\w+)\)", text, re.I)
    if pragma:
        table = pragma.group(1)
        return (
            "SELECT ordinal_position - 1 AS cid, column_name AS name, data_type AS type, "
            "0 AS notnull, NULL AS dflt_value, 0 AS pk "
            "FROM information_schema.columns "
            f"WHERE table_schema = 'public' AND table_name = '{table}' "
            "ORDER BY ordinal_position"
        )
    if re.search(r"last_insert_rowid\s*\(\s*\)", text, re.I):
        return "SELECT lastval()"
    text = re.sub(r"\s+COLLATE\s+NOCASE", "", text, flags=re.I)
    ignore = re.match(r"INSERT\s+OR\s+IGNORE\s+INTO\s+", text, re.I)
    replace = re.match(r"INSERT\s+OR\s+REPLACE\s+INTO\s+(\w+)\s*\(([^)]+)\)\s*VALUES\s*\((.+)\)\s*$", text, re.I | re.S)
    if ignore:
        text = re.sub(r"INSERT\s+OR\s+IGNORE\s+INTO", "INSERT INTO", text, count=1, flags=re.I)
        if "ON CONFLICT" not in text.upper():
            text = text.rstrip().rstrip(";") + " ON CONFLICT DO NOTHING"
        return _qmarks(text)
    if replace:
        table = replace.group(1)
        cols = [c.strip() for c in replace.group(2).split(",")]
        values = replace.group(3)
        key = UPSERT_KEYS.get(table, cols[0])
        assignments = ", ".join(f"{c} = EXCLUDED.{c}" for c in cols if c != key)
        text = f"INSERT INTO {table} ({', '.join(cols)}) VALUES ({values}) ON CONFLICT ({key}) DO UPDATE SET {assignments}"
        return _qmarks(text)
    return _qmarks(text)


def _qmarks(sql: str) -> str:
    # psycopg treats % as placeholders. LIKE 'foo%' must be 'foo%%'.
    sql = sql.replace("%", "%%")
    sql = re.sub(r"(?<!:):([a-zA-Z_][a-zA-Z0-9_]*)", r"%(\1)s", sql)
    return sql.replace("?", "%s")


class Connection:
    def __init__(self, dialect: str, raw: Any):
        self.dialect = dialect
        self._raw = raw

    def execute(self, sql: str, params: Any = ()) -> Result:
        rewritten = _rewrite_pg(sql) if self.dialect == "postgres" else sql
        if self.dialect == "postgres":
            with self._raw.cursor() as cur:
                cur.execute(rewritten, params or None)
                rows = _pg_rows(cur)
            return Result(rows)
        cur = self._raw.execute(rewritten, params)
        return Result(_sqlite_rows(cur))

    def executemany(self, sql: str, seq: Iterable[Any]) -> Result:
        rewritten = _rewrite_pg(sql) if self.dialect == "postgres" else sql
        rows_list = list(seq)
        if self.dialect == "postgres":
            with self._raw.cursor() as cur:
                cur.executemany(rewritten, rows_list)
            return Result([])
        self._raw.executemany(rewritten, rows_list)
        return Result([])

    def executescript(self, script: str) -> None:
        if self.dialect == "sqlite":
            self._raw.executescript(script)
            return
        statement = []
        for line in script.splitlines():
            stripped = line.strip()
            if stripped.startswith("--"):
                continue
            statement.append(line)
            if stripped.endswith(";"):
                sql = "\n".join(statement).strip()
                statement = []
                if sql:
                    self.execute(sql)

    def commit(self) -> None:
        self._raw.commit()

    def close(self) -> None:
        self._raw.close()

    def __enter__(self) -> Connection:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self._raw.commit()
        else:
            self._raw.rollback()


def _sqlite_rows(cur: sqlite3.Cursor) -> list[Row]:
    desc = cur.description
    if not desc:
        return []
    names = [col[0] for col in desc]
    out: list[Row] = []
    for raw in cur.fetchall():
        mapping = {name: raw[i] for i, name in enumerate(names)}
        out.append(Row(mapping, list(raw)))
    return out


def _pg_rows(cur: Any) -> list[Row]:
    desc = cur.description
    if not desc:
        return []
    names = [col.name for col in desc]
    out: list[Row] = []
    for raw in cur.fetchall():
        mapping = {name: raw[i] for i, name in enumerate(names)}
        out.append(Row(mapping, list(raw)))
    return out


def connect(db_path: Path | None = None) -> Connection:
    if is_postgres():
        import psycopg

        raw = psycopg.connect(postgres_url())
        return Connection("postgres", raw)
    path = Path(db_path) if db_path else DEFAULT_SQLITE
    path.parent.mkdir(parents=True, exist_ok=True)
    raw = sqlite3.connect(path)
    raw.row_factory = sqlite3.Row
    return Connection("sqlite", raw)


def schema_sql(conn: Connection) -> str:
    path = SCHEMA_PG if conn.dialect == "postgres" else SCHEMA_SQLITE
    return path.read_text(encoding="utf-8")


def league_schema_sql(conn: Connection) -> str:
    path = LEAGUE_PG if conn.dialect == "postgres" else LEAGUE_SQLITE
    return path.read_text(encoding="utf-8")
