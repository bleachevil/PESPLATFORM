"""League-manager rules: status, price, contracts, transfer windows."""

from __future__ import annotations

import os
import re
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from importer.db import league_schema_sql  # noqa: E402

SCHEMA_PATH = Path(__file__).with_name("league_schema.sql")
SESSION_DAYS = 30
WINDOW_KINDS = {
    "play": "Match week",
    "release_clause": "Release clauses",
    "release_sea": "Release to the sea",
    "transfer": "Transfers and loans",
    "buy_sea": "Buy from the sea",
    "squad_check": "Squad check",
    "auction": "Auction",
}
INITIAL_SQUAD_LIMIT = 16
MAX_DIVISIONS = 3
COMPETITION_KINDS = {
    "division": "League",
    "cup": "Cup",
    "ucl": "Champions League",
    "event": "One-off",
}


def init_league_db(conn: sqlite3.Connection) -> None:
    conn.executescript(league_schema_sql(conn))
    columns = {row[1] for row in conn.execute("PRAGMA table_info(users)")}
    if "google_sub" not in columns:
        conn.execute("ALTER TABLE users ADD COLUMN google_sub TEXT")
        conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_google_sub ON users(google_sub)")
    league_cols = {row[1] for row in conn.execute("PRAGMA table_info(leagues)")}
    if "weeks" not in league_cols:
        conn.execute("ALTER TABLE leagues ADD COLUMN weeks INTEGER DEFAULT 6")
    conn.commit()


def now_iso() -> str:
    return datetime.now().replace(microsecond=0).isoformat(sep=" ")


def slugify(value: str, fallback: str = "item") -> str:
    base = re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")
    return base or fallback


def upsert_google_user(conn: sqlite3.Connection, google_sub: str, email: str, name: str) -> dict:
    google_sub = (google_sub or "").strip()
    email = (email or "").strip().lower()
    name = (name or "").strip() or email.split("@")[0] or "Manager"
    if not google_sub or not email:
        raise ValueError("Google did not return an email for this account")
    row = conn.execute("SELECT * FROM users WHERE google_sub = ?", (google_sub,)).fetchone()
    if not row:
        row = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if row:
        conn.execute(
            "UPDATE users SET email = ?, name = ?, google_sub = ? WHERE id = ?",
            (email, name, google_sub, row["id"]),
        )
    else:
        conn.execute(
            "INSERT INTO users(email, name, password_hash, google_sub, created_at) VALUES (?, ?, '', ?, ?)",
            (email, name, google_sub, now_iso()),
        )
    conn.commit()
    saved = conn.execute(
        "SELECT id, email, name FROM users WHERE google_sub = ?",
        (google_sub,),
    ).fetchone()
    if not saved:
        raise ValueError("Could not create a manager from this Google account")
    return dict(saved)


def clear_session(conn: sqlite3.Connection, token: str | None) -> None:
    if token:
        conn.execute("DELETE FROM sessions WHERE token = ?", (token,))
        conn.commit()


def list_leagues(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        """
        SELECT l.*,
               (SELECT COUNT(*) FROM manager_teams t WHERE t.league_id = l.id) AS team_count
        FROM leagues l
        ORDER BY l.start_on DESC, l.name
        """
    )
    return [dict(row) for row in rows]


def league_teams(conn: sqlite3.Connection, league_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.*, u.name AS manager_name,
               (SELECT COUNT(*) FROM contracts c WHERE c.team_id = t.id AND c.status = 'active') AS squad_count
        FROM manager_teams t
        JOIN users u ON u.id = t.user_id
        WHERE t.league_id = ?
        ORDER BY t.name
        """,
        (league_id,),
    )
    return [dict(row) for row in rows]


def league_windows(conn: sqlite3.Connection, league_id: int) -> list[dict]:
    return [dict(row) for row in conn.execute(
        "SELECT * FROM league_windows WHERE league_id = ? ORDER BY sort_order, id",
        (league_id,),
    )]


def incoming_offers(conn: sqlite3.Connection, league_id: int, team_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT o.*,
               (SELECT name FROM players WHERE pid = o.player_pid ORDER BY mode LIMIT 1) AS player_name,
               ft.name AS from_name
        FROM transfer_offers o
        JOIN manager_teams ft ON ft.id = o.from_team_id
        WHERE o.league_id = ? AND o.to_team_id = ? AND o.status = 'pending'
        ORDER BY o.created_at DESC
        """,
        (league_id, team_id),
    )
    return [dict(row) for row in rows]


def create_session(conn: sqlite3.Connection, user_id: int) -> str:
    token = os.urandom(24).hex()
    expires = (datetime.now() + timedelta(days=SESSION_DAYS)).replace(microsecond=0).isoformat(sep=" ")
    conn.execute("INSERT INTO sessions(token, user_id, expires_at) VALUES (?, ?, ?)", (token, user_id, expires))
    conn.commit()
    return token


def user_from_token(conn: sqlite3.Connection, token: str | None) -> dict | None:
    if not token:
        return None
    row = conn.execute(
        """
        SELECT u.id, u.email, u.name
        FROM sessions s
        JOIN users u ON u.id = s.user_id
        WHERE s.token = ? AND s.expires_at >= ?
        """,
        (token, now_iso()),
    ).fetchone()
    return dict(row) if row else None


def base_price(overall: int | None, card_type: str = "") -> int:
    ovr = int(overall or 0)
    if ovr <= 0:
        return 10
    price = max(10, int(round((ovr * ovr) / 38)))
    kind = (card_type or "").strip().lower()
    if kind and kind not in {"standard", "sample"}:
        price = int(round(price * 1.15))
    return price


def open_windows(conn: sqlite3.Connection, league_id: int, when: str | None = None) -> list[dict]:
    when = when or now_iso()
    rows = conn.execute(
        """
        SELECT * FROM league_windows
        WHERE league_id = ? AND starts_at <= ? AND ends_at >= ?
        ORDER BY sort_order, id
        """,
        (league_id, when, when),
    )
    return [dict(row) for row in rows]


def current_window(conn: sqlite3.Connection, league_id: int, when: str | None = None) -> dict | None:
    windows = open_windows(conn, league_id, when)
    return windows[0] if windows else None


def next_window(conn: sqlite3.Connection, league_id: int, kinds: list[str] | None = None) -> dict | None:
    sql = "SELECT * FROM league_windows WHERE league_id = ? AND starts_at > ?"
    params: list = [league_id, now_iso()]
    if kinds:
        sql += f" AND kind IN ({','.join('?' * len(kinds))})"
        params.extend(kinds)
    sql += " ORDER BY starts_at, sort_order LIMIT 1"
    row = conn.execute(sql, params).fetchone()
    return dict(row) if row else None


def squad_count(conn: sqlite3.Connection, team_id: int) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM contracts WHERE team_id = ? AND status = 'active'",
        (team_id,),
    ).fetchone()[0]


def is_new_manager(conn: sqlite3.Connection, team: dict | None) -> bool:
    if not team:
        return False
    return squad_count(conn, team["id"]) < INITIAL_SQUAD_LIMIT


def window_of(windows: list[dict] | None, *kinds: str) -> dict | None:
    for window in windows or []:
        if window.get("kind") in kinds:
            return window
    return None


def league_by_slug(conn: sqlite3.Connection, slug: str) -> dict | None:
    row = conn.execute("SELECT * FROM leagues WHERE slug = ?", (slug,)).fetchone()
    return dict(row) if row else None


def manager_team(conn: sqlite3.Connection, league_id: int, user_id: int) -> dict | None:
    row = conn.execute(
        "SELECT * FROM manager_teams WHERE league_id = ? AND user_id = ?",
        (league_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def action_count(conn: sqlite3.Connection, window_id: int, team_id: int, action: str) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM window_actions WHERE window_id = ? AND team_id = ? AND action = ?",
        (window_id, team_id, action),
    ).fetchone()[0]


def record_action(conn: sqlite3.Connection, window_id: int, team_id: int, action: str) -> None:
    conn.execute(
        "INSERT INTO window_actions(window_id, team_id, action, created_at) VALUES (?, ?, ?, ?)",
        (window_id, team_id, action, now_iso()),
    )


def player_status(conn: sqlite3.Connection, league_id: int, pid: str) -> dict:
    contract = conn.execute(
        """
        SELECT c.*, t.name AS team_name, t.slug AS team_slug
        FROM contracts c
        JOIN manager_teams t ON t.id = c.team_id
        WHERE c.league_id = ? AND c.player_pid = ? AND c.status IN ('active', 'sea')
        """,
        (league_id, pid),
    ).fetchone()
    listing = conn.execute(
        "SELECT * FROM sea_listings WHERE league_id = ? AND player_pid = ?",
        (league_id, pid),
    ).fetchone()
    if listing:
        return {
            "code": "sea",
            "label": "In the sea",
            "team_name": None,
            "fee": listing["price"],
            "release_clause": None,
            "contract": dict(contract) if contract else None,
        }
    if contract:
        return {
            "code": "signed",
            "label": f"Signed · {contract['team_name']}",
            "team_name": contract["team_name"],
            "fee": contract["fee"],
            "release_clause": contract["release_clause"],
            "contract": dict(contract),
        }
    return {
        "code": "free",
        "label": "Available",
        "team_name": None,
        "fee": None,
        "release_clause": None,
        "contract": None,
    }


def attach_market(conn: sqlite3.Connection, league: dict | None, players: list[dict]) -> list[dict]:
    if not league:
        for player in players:
            player["market_price"] = base_price(player.get("overall"), player.get("card_type") or "")
            player["market_status"] = {"code": "free", "label": "Available"}
        return players
    for player in players:
        status = player_status(conn, league["id"], player["pid"])
        player["market_status"] = status
        player["market_price"] = status["fee"] or base_price(player.get("overall"), player.get("card_type") or "")
    return players


def create_league(
    conn: sqlite3.Connection,
    name: str,
    organizer_id: int | None,
    max_teams: int,
    weeks: int,
    start_on: str | None = None,
    starting_budget: int = 1000,
) -> dict:
    slug = slugify(name, "league")
    base = slug
    n = 2
    while conn.execute("SELECT 1 FROM leagues WHERE slug = ?", (slug,)).fetchone():
        slug = f"{base}-{n}"
        n += 1
    weeks = clamp_weeks(weeks)
    start_on = (start_on or "").strip() or default_season_start()
    windows = season_windows(start_on, weeks)
    end_on = season_end_on(windows)
    conn.execute(
        """
        INSERT INTO leagues(slug, name, organizer_id, start_on, end_on, max_teams, weeks, starting_budget, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open', ?)
        """,
        (slug, name, organizer_id, start_on, end_on, max_teams, weeks, starting_budget, now_iso()),
    )
    league_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    replace_windows(conn, league_id, windows)
    ensure_default_competitions(conn, league_id)
    row = conn.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone()
    return dict(row)


def join_league(conn: sqlite3.Connection, league: dict, user: dict, team_name: str) -> dict:
    existing = manager_team(conn, league["id"], user["id"])
    if existing:
        return existing
    taken = conn.execute("SELECT COUNT(*) FROM manager_teams WHERE league_id = ?", (league["id"],)).fetchone()[0]
    if taken >= int(league["max_teams"] or 16):
        raise ValueError("This league is full")
    name = (team_name or user["name"]).strip() or user["name"]
    slug = slugify(name, "club")
    conn.execute(
        """
        INSERT INTO manager_teams(league_id, user_id, name, slug, budget, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (league["id"], user["id"], name, slug, int(league["starting_budget"] or 1000), now_iso()),
    )
    conn.commit()
    team = manager_team(conn, league["id"], user["id"])
    if not team:
        raise ValueError("Could not join league")
    division = default_division(conn, league["id"])
    if division:
        enroll_team(conn, division["id"], team["id"])
    return team


def sign_player(conn: sqlite3.Connection, league: dict, team: dict, player: dict, window: dict | None) -> None:
    status = player_status(conn, league["id"], player["pid"])
    listing = conn.execute(
        "SELECT * FROM sea_listings WHERE league_id = ? AND player_pid = ?",
        (league["id"], player["pid"]),
    ).fetchone()
    sea_open = bool(window and window["kind"] in {"buy_sea", "auction"})
    new_club = is_new_manager(conn, team)
    if listing:
        if not sea_open:
            raise ValueError("The sea is closed until the next buy window")
        if window["max_signings"] and action_count(conn, window["id"], team["id"], "sign_sea") >= window["max_signings"]:
            raise ValueError(f"Sea signings used up ({window['max_signings']})")
        price = int(listing["price"])
        if team["budget"] < price:
            raise ValueError("Not enough budget")
        conn.execute("UPDATE manager_teams SET budget = budget - ? WHERE id = ?", (price, team["id"]))
        conn.execute("DELETE FROM sea_listings WHERE id = ?", (listing["id"],))
        conn.execute(
            "UPDATE contracts SET status = 'released' WHERE league_id = ? AND player_pid = ? AND status IN ('active', 'sea')",
            (league["id"], player["pid"]),
        )
        conn.execute(
            """
            INSERT INTO contracts(league_id, team_id, player_pid, fee, release_clause, kind, status, signed_at)
            VALUES (?, ?, ?, ?, NULL, 'signed', 'active', ?)
            """,
            (league["id"], team["id"], player["pid"], price, now_iso()),
        )
        record_action(conn, window["id"], team["id"], "sign_sea")
        conn.commit()
        return
    if status["code"] != "free":
        raise ValueError("This player is already signed")
    if not sea_open and not new_club:
        raise ValueError("Signing is closed until the next sea window")
    if sea_open and window["max_signings"] and action_count(conn, window["id"], team["id"], "sign_sea") >= window["max_signings"]:
        raise ValueError(f"Signings used up ({window['max_signings']})")
    price = base_price(player.get("overall"), player.get("card_type") or "")
    if team["budget"] < price:
        raise ValueError("Not enough budget")
    conn.execute("UPDATE manager_teams SET budget = budget - ? WHERE id = ?", (price, team["id"]))
    conn.execute(
        """
        INSERT INTO contracts(league_id, team_id, player_pid, fee, release_clause, kind, status, signed_at)
        VALUES (?, ?, ?, ?, NULL, 'signed', 'active', ?)
        """,
        (league["id"], team["id"], player["pid"], price, now_iso()),
    )
    if sea_open:
        record_action(conn, window["id"], team["id"], "sign_sea")
    conn.commit()


def set_release_clause(conn: sqlite3.Connection, league: dict, team: dict, player_pid: str, clause: int, window: dict | None) -> None:
    if not window or window["kind"] != "release_clause":
        raise ValueError("Release-clause window is closed")
    contract = conn.execute(
        "SELECT * FROM contracts WHERE league_id = ? AND team_id = ? AND player_pid = ? AND status = 'active'",
        (league["id"], team["id"], player_pid),
    ).fetchone()
    if not contract:
        raise ValueError("That player is not on your books")
    conn.execute("UPDATE contracts SET release_clause = ? WHERE id = ?", (int(clause), contract["id"]))
    record_action(conn, window["id"], team["id"], "clause")
    conn.commit()


def release_to_sea(conn: sqlite3.Connection, league: dict, team: dict, player_pid: str, window: dict | None) -> None:
    if not window or window["kind"] != "release_sea":
        raise ValueError("Release-to-sea window is closed")
    if window["max_releases"] and action_count(conn, window["id"], team["id"], "release") >= window["max_releases"]:
        raise ValueError(f"Releases used up ({window['max_releases']})")
    contract = conn.execute(
        "SELECT * FROM contracts WHERE league_id = ? AND team_id = ? AND player_pid = ? AND status = 'active'",
        (league["id"], team["id"], player_pid),
    ).fetchone()
    if not contract:
        raise ValueError("That player is not on your books")
    refund = int(round(int(contract["fee"]) * (int(window["refund_pct"] or 50) / 100)))
    conn.execute("UPDATE manager_teams SET budget = budget + ? WHERE id = ?", (refund, team["id"]))
    conn.execute("UPDATE contracts SET status = 'sea' WHERE id = ?", (contract["id"],))
    conn.execute(
        """
        INSERT INTO sea_listings(league_id, player_pid, from_team_id, price, listed_at)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(league_id, player_pid) DO UPDATE SET
            from_team_id = excluded.from_team_id,
            price = excluded.price,
            listed_at = excluded.listed_at
        """,
        (league["id"], player_pid, team["id"], max(10, int(contract["fee"]) - refund), now_iso()),
    )
    record_action(conn, window["id"], team["id"], "release")
    conn.commit()


def buyout_clause(conn: sqlite3.Connection, league: dict, team: dict, player_pid: str, window: dict | None) -> None:
    if not window or window["kind"] != "release_clause":
        raise ValueError("Buyout window is closed")
    if window["max_signings"] and action_count(conn, window["id"], team["id"], "buyout") >= window["max_signings"]:
        raise ValueError("Buyout limit reached")
    contract = conn.execute(
        """
        SELECT c.*, t.name AS team_name
        FROM contracts c
        JOIN manager_teams t ON t.id = c.team_id
        WHERE c.league_id = ? AND c.player_pid = ? AND c.status = 'active'
        """,
        (league["id"], player_pid),
    ).fetchone()
    if not contract or not contract["release_clause"]:
        raise ValueError("No release clause on this player")
    if contract["team_id"] == team["id"]:
        raise ValueError("You already hold this player")
    fee = int(contract["release_clause"])
    if team["budget"] < fee:
        raise ValueError("Not enough budget")
    conn.execute("UPDATE manager_teams SET budget = budget - ? WHERE id = ?", (fee, team["id"]))
    conn.execute("UPDATE manager_teams SET budget = budget + ? WHERE id = ?", (fee, contract["team_id"]))
    conn.execute("UPDATE contracts SET status = 'released' WHERE id = ?", (contract["id"],))
    conn.execute(
        """
        INSERT INTO contracts(league_id, team_id, player_pid, fee, release_clause, kind, status, signed_at)
        VALUES (?, ?, ?, ?, NULL, 'signed', 'active', ?)
        """,
        (league["id"], team["id"], player_pid, fee, now_iso()),
    )
    record_action(conn, window["id"], team["id"], "buyout")
    conn.commit()


def offer_transfer(conn: sqlite3.Connection, league: dict, from_team: dict, to_team_id: int, player_pid: str, fee: int, kind: str, window: dict | None) -> None:
    if not window or window["kind"] != "transfer":
        raise ValueError("Transfer window is closed")
    action = "loan" if kind == "loan" else "transfer"
    limit = window["max_loans"] if action == "loan" else window["max_transfers"]
    if limit and action_count(conn, window["id"], from_team["id"], action) >= limit:
        raise ValueError(f"{action.title()} limit reached")
    contract = conn.execute(
        "SELECT * FROM contracts WHERE league_id = ? AND team_id = ? AND player_pid = ? AND status = 'active'",
        (league["id"], from_team["id"], player_pid),
    ).fetchone()
    if not contract:
        raise ValueError("That player is not on your books")
    if to_team_id == from_team["id"]:
        raise ValueError("Pick another club")
    conn.execute(
        """
        INSERT INTO transfer_offers(league_id, player_pid, from_team_id, to_team_id, fee, kind, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?)
        """,
        (league["id"], player_pid, from_team["id"], to_team_id, int(fee), kind, now_iso()),
    )
    record_action(conn, window["id"], from_team["id"], action)
    conn.commit()


def decide_offer(conn: sqlite3.Connection, league: dict, team: dict, offer_id: int, accept: bool) -> None:
    offer = conn.execute(
        "SELECT * FROM transfer_offers WHERE id = ? AND league_id = ? AND to_team_id = ? AND status = 'pending'",
        (offer_id, league["id"], team["id"]),
    ).fetchone()
    if not offer:
        raise ValueError("Offer not found")
    if not accept:
        conn.execute("UPDATE transfer_offers SET status = 'rejected' WHERE id = ?", (offer_id,))
        conn.commit()
        return
    if team["budget"] < int(offer["fee"]):
        raise ValueError("Not enough budget")
    contract = conn.execute(
        "SELECT * FROM contracts WHERE league_id = ? AND player_pid = ? AND status = 'active'",
        (league["id"], offer["player_pid"]),
    ).fetchone()
    if not contract:
        raise ValueError("Player is no longer available")
    conn.execute("UPDATE manager_teams SET budget = budget - ? WHERE id = ?", (offer["fee"], team["id"]))
    conn.execute("UPDATE manager_teams SET budget = budget + ? WHERE id = ?", (offer["fee"], offer["from_team_id"]))
    conn.execute("UPDATE contracts SET status = 'released' WHERE id = ?", (contract["id"],))
    conn.execute(
        """
        INSERT INTO contracts(league_id, team_id, player_pid, fee, release_clause, kind, status, signed_at)
        VALUES (?, ?, ?, ?, NULL, ?, 'active', ?)
        """,
        (league["id"], team["id"], offer["player_pid"], offer["fee"], offer["kind"], now_iso()),
    )
    conn.execute("UPDATE transfer_offers SET status = 'accepted' WHERE id = ?", (offer_id,))
    conn.commit()


def squad_rows(conn: sqlite3.Connection, league_id: int, team_id: int) -> list[sqlite3.Row]:
    return list(
        conn.execute(
            """
            SELECT pl.*, c.fee, c.release_clause, c.kind AS contract_kind, c.status AS contract_status, c.signed_at
            FROM contracts c
            JOIN players pl ON pl.pid = c.player_pid
            WHERE c.league_id = ? AND c.team_id = ? AND c.status = 'active'
            ORDER BY pl.overall DESC, pl.name
            """,
            (league_id, team_id),
        )
    )


PHASE_LABELS = {
    "first_half": "First half",
    "winter": "Mid-season transfer",
    "second_half": "Second half",
    "summer": "End-of-season transfer",
}


def clamp_weeks(weeks) -> int:
    try:
        value = int(weeks)
    except (TypeError, ValueError):
        value = 6
    return max(2, min(20, value))


def default_season_start() -> str:
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    days_ahead = (4 - today.weekday()) % 7
    return (today + timedelta(days=days_ahead)).strftime("%Y-%m-%d")


def split_season_weeks(weeks: int) -> tuple[int, int]:
    """Match weeks on either side of the mid-season break. A 6-week sheet is 2 + break + 3."""
    weeks = clamp_weeks(weeks)
    match_weeks = max(2, weeks - 1)
    first = max(1, match_weeks // 2)
    first = min(first, match_weeks - 1)
    return first, match_weeks - first


def season_end_on(windows: list[dict]) -> str:
    if not windows:
        return now_iso()[:10]
    return str(windows[-1]["ends_at"])[:10]


def _parse_start(start_on: str) -> datetime:
    text = (start_on or "").strip().replace("/", "-")
    for fmt in ("%Y-%m-%d", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt).replace(hour=0, minute=0, second=0, microsecond=0)
        except ValueError:
            continue
    return datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)


def _stamp(start: datetime, days: int, hour: int = 0, minute: int = 0) -> str:
    point = start + timedelta(days=days)
    return point.replace(hour=hour, minute=minute, second=0, microsecond=0).strftime("%Y-%m-%d %H:%M")


def _parse_stamp(value: str) -> datetime | None:
    text = (value or "").strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _md(point: datetime) -> str:
    return f"{point.month}/{point.day}"


def _ampm(point: datetime) -> str:
    return point.strftime("%I:%M%p").lstrip("0")


def format_window_when(window: dict) -> str:
    start = _parse_stamp(str(window.get("starts_at") or ""))
    end = _parse_stamp(str(window.get("ends_at") or ""))
    if not start or not end:
        return f"{window.get('starts_at') or ''} – {window.get('ends_at') or ''}".strip(" –")
    if window.get("kind") == "play":
        return f"{_md(start)} – {_md(end)}"
    return f"{_md(start)} {_ampm(start)} – {_md(end)} {_ampm(end)}"


def infer_activity(window: dict) -> str:
    if window.get("activity"):
        return str(window["activity"])
    kind = str(window.get("kind") or "")
    title = str(window.get("title") or "")
    if kind == "play":
        lower = title.lower()
        if "playoff" in lower:
            return "Second-half matches + promotion playoff"
        if "first" in lower:
            return "First-half matches"
        if "second" in lower:
            return "Second-half matches"
        return title
    if " — " in title:
        rest = title.split(" — ", 1)[1]
        return rest[:1].upper() + rest[1:] if rest else rest
    return title


def infer_phase(window: dict, seen_winter: bool = False) -> str:
    title = str(window.get("title") or "").lower()
    kind = str(window.get("kind") or "")
    if window.get("phase") in PHASE_LABELS:
        return str(window["phase"])
    if "winter" in title or "mid-season" in title:
        return "winter"
    if "summer" in title or "end-of-season" in title:
        return "summer"
    if kind == "play":
        if "first" in title:
            return "first_half"
        if "second" in title or "playoff" in title:
            return "second_half"
        return "second_half" if seen_winter else "first_half"
    return "summer" if seen_winter else "winter"


def calendar_view(windows: list[dict], open_ids: set | None = None) -> list[dict]:
    open_ids = open_ids or set()
    groups: list[dict] = []
    current = None
    seen_winter = False
    for window in windows:
        phase = infer_phase(window, seen_winter)
        if phase == "winter":
            seen_winter = True
        if current is None or current["phase"] != phase:
            current = {
                "phase": phase,
                "label": PHASE_LABELS.get(phase, phase.replace("_", " ").title()),
                "rows": [],
            }
            groups.append(current)
        period = window.get("period")
        if not period and window.get("kind") == "play":
            period = str(window.get("title") or "").split(" —")[0]
        current["rows"].append(
            {
                **dict(window),
                "phase": phase,
                "period": period or "",
                "activity": infer_activity(window),
                "when_label": format_window_when(window),
                "is_open": window.get("id") in open_ids,
            }
        )
    return groups


def _play_week(start: datetime, week_no: int, phase: str, day: int, last_of_half: bool, playoff: bool = False) -> dict:
    if playoff:
        activity = "Second-half matches + promotion playoff"
        title = f"Week {week_no} — playoffs / promotion"
    elif phase == "first_half":
        activity = "First-half matches"
        title = f"Week {week_no} — first-half matches"
    else:
        activity = "Second-half matches"
        title = f"Week {week_no} — second-half matches"
    end_hour, end_minute = (20, 59) if last_of_half else (23, 59)
    return {
        "kind": "play",
        "title": title,
        "phase": phase,
        "period": f"Week {week_no}",
        "activity": activity,
        "starts_at": _stamp(start, day),
        "ends_at": _stamp(start, day + 6, end_hour, end_minute),
    }


def _transfer_block(start: datetime, day: int, phase: str, label: str, limits: dict) -> list[dict]:
    eve = day - 1
    rows = [
        (
            "release_clause",
            f"{label} — add release clauses" if phase == "winter" else f"{label} — buy out a release clause (max {limits['clause']})",
            "Add a release clause" if phase == "winter" else f"Buy out a release clause (max {limits['clause']})",
            {"max_signings": limits["clause"]},
        ),
        (
            "release_sea",
            f"{label} — release to the sea (max {limits['sea_out']}, 50% refund)",
            f"Release players to the sea (max {limits['sea_out']}, 50% refund)",
            {"max_releases": limits["sea_out"], "refund_pct": 50},
        ),
        (
            "transfer",
            f"{label} — {limits['transfer_title']}",
            limits["transfer_title"],
            {"max_transfers": limits["tr"], "max_loans": limits["loan"]},
        ),
        (
            "buy_sea",
            f"{label} — buy from the sea (max {limits['sea_in']})",
            f"Buy from the sea (max {limits['sea_in']})",
            {"max_signings": limits["sea_in"]},
        ),
        (
            "squad_check",
            f"{label} — squad check / card upgrades",
            "Squad check (card upgrades)",
            {},
        ),
    ]
    windows = []
    for index, (kind, title, activity, extra) in enumerate(rows):
        item = {
            "kind": kind,
            "title": title,
            "phase": phase,
            "period": "",
            "activity": activity,
            "starts_at": _stamp(start, eve + index, 21),
            "ends_at": _stamp(start, eve + index + 1, 21),
        }
        item.update(extra)
        windows.append(item)
    return windows


def season_windows(start_on: str, weeks: int = 6) -> list[dict]:
    """Build first half, mid-season window, second half, then end-of-season window."""
    start = _parse_start(start_on)
    weeks = clamp_weeks(weeks)
    first_n, second_n = split_season_weeks(weeks)
    first_nums = list(range(1, first_n + 1))
    second_nums = list(range(first_n + 2, first_n + 2 + second_n))
    windows: list[dict] = []
    day = 0
    for index, week_no in enumerate(first_nums):
        windows.append(_play_week(start, week_no, "first_half", day, last_of_half=index == first_n - 1))
        day += 7
    windows.extend(
        _transfer_block(
            start,
            day,
            "winter",
            "Winter",
            {
                "clause": 1,
                "sea_out": 1,
                "tr": 1,
                "loan": 1,
                "sea_in": 1,
                "transfer_title": "1 transfer or 1 loan",
            },
        )
    )
    day += 5
    for index, week_no in enumerate(second_nums):
        playoff = index == second_n - 1 and weeks >= 6
        windows.append(
            _play_week(start, week_no, "second_half", day, last_of_half=index == second_n - 1, playoff=playoff)
        )
        day += 7
    windows.extend(
        _transfer_block(
            start,
            day,
            "summer",
            "Summer",
            {
                "clause": 1,
                "sea_out": 2,
                "tr": 2,
                "loan": 2,
                "sea_in": 2,
                "transfer_title": "2 loans + 1 transfer, or 2 transfers + 1 loan",
            },
        )
    )
    return windows


def apply_season_calendar(conn: sqlite3.Connection, league: dict) -> None:
    start_on = league.get("start_on") or default_season_start()
    weeks = clamp_weeks(league.get("weeks") or 6)
    windows = season_windows(start_on, weeks)
    replace_windows(conn, league["id"], windows)
    conn.execute(
        "UPDATE leagues SET start_on = ?, end_on = ?, weeks = ? WHERE id = ?",
        (start_on[:10] if start_on else default_season_start(), season_end_on(windows), weeks, league["id"]),
    )
    conn.commit()


def update_window_times(conn: sqlite3.Connection, league_id: int, updates: list[dict]) -> None:
    for item in updates:
        conn.execute(
            "UPDATE league_windows SET starts_at = ?, ends_at = ? WHERE id = ? AND league_id = ?",
            (item["starts_at"], item["ends_at"], item["id"], league_id),
        )
    conn.commit()


def replace_windows(conn: sqlite3.Connection, league_id: int, windows: list[dict]) -> None:
    conn.execute("DELETE FROM league_windows WHERE league_id = ?", (league_id,))
    for index, window in enumerate(windows):
        conn.execute(
            """
            INSERT INTO league_windows(
                league_id, kind, title, starts_at, ends_at, max_releases, max_signings,
                max_transfers, max_loans, refund_pct, sort_order
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                league_id,
                window["kind"],
                window["title"],
                window["starts_at"],
                window["ends_at"],
                int(window.get("max_releases") or 0),
                int(window.get("max_signings") or 0),
                int(window.get("max_transfers") or 0),
                int(window.get("max_loans") or 0),
                int(window.get("refund_pct") or 50),
                index,
            ),
        )
    conn.commit()


def is_host(user: dict | None, league: dict) -> bool:
    if not user:
        return False
    organizer_id = league.get("organizer_id")
    return organizer_id is not None and int(organizer_id) == int(user["id"])


def is_officer(conn: sqlite3.Connection, league_id: int, user_id: int) -> bool:
    row = conn.execute(
        "SELECT 1 FROM league_officers WHERE league_id = ? AND user_id = ?",
        (league_id, user_id),
    ).fetchone()
    return bool(row)


def can_manage_league(conn: sqlite3.Connection, user: dict | None, league: dict, team: dict | None = None) -> bool:
    if not user:
        return False
    if is_host(user, league):
        return True
    if is_officer(conn, league["id"], user["id"]):
        return True
    organizer_id = league.get("organizer_id")
    return organizer_id is None and team is not None


def list_officers(conn: sqlite3.Connection, league_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT o.user_id, o.role, o.granted_at, u.name, u.email
        FROM league_officers o
        JOIN users u ON u.id = o.user_id
        WHERE o.league_id = ?
        ORDER BY u.name
        """,
        (league_id,),
    )
    return [dict(row) for row in rows]


def grant_officer(conn: sqlite3.Connection, league: dict, email: str) -> dict:
    email = (email or "").strip().lower()
    user = conn.execute("SELECT * FROM users WHERE email = ?", (email,)).fetchone()
    if not user:
        raise ValueError("No manager with that Google email has signed in yet")
    if league.get("organizer_id") and int(user["id"]) == int(league["organizer_id"]):
        raise ValueError("The host already manages this league")
    conn.execute(
        """
        INSERT OR IGNORE INTO league_officers(league_id, user_id, role, granted_at)
        VALUES (?, ?, 'officer', ?)
        """,
        (league["id"], user["id"], now_iso()),
    )
    conn.commit()
    return dict(user)


def revoke_officer(conn: sqlite3.Connection, league_id: int, user_id: int) -> None:
    conn.execute("DELETE FROM league_officers WHERE league_id = ? AND user_id = ?", (league_id, user_id))
    conn.commit()


def user_by_email(conn: sqlite3.Connection, email: str) -> dict | None:
    row = conn.execute("SELECT * FROM users WHERE email = ?", ((email or "").strip().lower(),)).fetchone()
    return dict(row) if row else None


def join_request_for(conn: sqlite3.Connection, league_id: int, user_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM join_requests
        WHERE league_id = ? AND user_id = ? AND status IN ('pending', 'invited')
        ORDER BY id DESC LIMIT 1
        """,
        (league_id, user_id),
    ).fetchone()
    return dict(row) if row else None


def list_join_requests(conn: sqlite3.Connection, league_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT r.*, u.name AS manager_name, u.email
        FROM join_requests r
        JOIN users u ON u.id = r.user_id
        WHERE r.league_id = ? AND r.status IN ('pending', 'invited')
        ORDER BY r.created_at DESC
        """,
        (league_id,),
    )
    return [dict(row) for row in rows]


def request_join(conn: sqlite3.Connection, league: dict, user: dict, team_name: str) -> dict:
    if manager_team(conn, league["id"], user["id"]):
        raise ValueError("You already have a club in this league")
    existing = join_request_for(conn, league["id"], user["id"])
    if existing:
        return existing
    taken = conn.execute("SELECT COUNT(*) FROM manager_teams WHERE league_id = ?", (league["id"],)).fetchone()[0]
    pending = conn.execute(
        "SELECT COUNT(*) FROM join_requests WHERE league_id = ? AND status IN ('pending', 'invited')",
        (league["id"],),
    ).fetchone()[0]
    if taken + pending >= int(league["max_teams"] or 16):
        raise ValueError("This league is full")
    name = (team_name or user["name"]).strip() or user["name"]
    conn.execute(
        """
        INSERT INTO join_requests(league_id, user_id, team_name, kind, status, created_at)
        VALUES (?, ?, ?, 'request', 'pending', ?)
        """,
        (league["id"], user["id"], name, now_iso()),
    )
    conn.commit()
    saved = join_request_for(conn, league["id"], user["id"])
    if not saved:
        raise ValueError("Could not send the join request")
    return saved


def invite_manager(conn: sqlite3.Connection, league: dict, email: str, team_name: str) -> dict:
    user = user_by_email(conn, email)
    if not user:
        raise ValueError("No manager with that Google email has signed in yet")
    if manager_team(conn, league["id"], user["id"]):
        raise ValueError("That manager already has a club here")
    existing = join_request_for(conn, league["id"], user["id"])
    if existing:
        return existing
    name = (team_name or user["name"]).strip() or user["name"]
    conn.execute(
        """
        INSERT INTO join_requests(league_id, user_id, team_name, kind, status, created_at)
        VALUES (?, ?, ?, 'invite', 'invited', ?)
        """,
        (league["id"], user["id"], name, now_iso()),
    )
    conn.commit()
    saved = join_request_for(conn, league["id"], user["id"])
    if not saved:
        raise ValueError("Could not create the invitation")
    return saved


def decide_join(conn: sqlite3.Connection, league: dict, request_id: int, approve: bool, by_user: dict) -> dict | None:
    row = conn.execute(
        "SELECT * FROM join_requests WHERE id = ? AND league_id = ?",
        (request_id, league["id"]),
    ).fetchone()
    if not row:
        raise ValueError("Join request not found")
    request = dict(row)
    if request["status"] not in {"pending", "invited"}:
        raise ValueError("This request was already decided")
    conn.execute(
        "UPDATE join_requests SET status = ?, decided_at = ?, decided_by = ? WHERE id = ?",
        ("approved" if approve else "rejected", now_iso(), by_user["id"], request_id),
    )
    conn.commit()
    if not approve:
        return None
    user = conn.execute("SELECT * FROM users WHERE id = ?", (request["user_id"],)).fetchone()
    if not user:
        raise ValueError("That manager no longer exists")
    return join_league(conn, league, dict(user), request["team_name"])


def accept_invite(conn: sqlite3.Connection, league: dict, user: dict) -> dict:
    request = join_request_for(conn, league["id"], user["id"])
    if not request or request["kind"] != "invite":
        raise ValueError("You do not have an invitation")
    return decide_join(conn, league, request["id"], True, user)


def default_division(conn: sqlite3.Connection, league_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT * FROM competitions
        WHERE league_id = ? AND kind = 'division'
        ORDER BY COALESCE(level, 1), id
        LIMIT 1
        """,
        (league_id,),
    ).fetchone()
    return dict(row) if row else None


def list_competitions(conn: sqlite3.Connection, league_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT c.*,
               (SELECT COUNT(*) FROM competition_teams t WHERE t.competition_id = c.id) AS team_count,
               (SELECT COUNT(*) FROM fixtures f WHERE f.competition_id = c.id) AS fixture_count
        FROM competitions c
        WHERE c.league_id = ?
        ORDER BY CASE c.kind WHEN 'division' THEN 0 WHEN 'cup' THEN 1 WHEN 'ucl' THEN 2 ELSE 3 END,
                 COALESCE(c.level, 99), c.id
        """,
        (league_id,),
    )
    items = []
    for row in rows:
        item = dict(row)
        item["kind_label"] = COMPETITION_KINDS.get(item["kind"], item["kind"])
        items.append(item)
    return items


def competition_by_slug(conn: sqlite3.Connection, league_id: int, slug: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM competitions WHERE league_id = ? AND slug = ?",
        (league_id, slug),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["kind_label"] = COMPETITION_KINDS.get(item["kind"], item["kind"])
    return item


def competition_by_id(conn: sqlite3.Connection, competition_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM competitions WHERE id = ?", (competition_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["kind_label"] = COMPETITION_KINDS.get(item["kind"], item["kind"])
    return item


def ensure_default_competitions(conn: sqlite3.Connection, league_id: int) -> list[dict]:
    existing = list_competitions(conn, league_id)
    if existing:
        return existing
    create_competition(conn, league_id, "division", "Division 1", level=1)
    return list_competitions(conn, league_id)


def create_competition(conn: sqlite3.Connection, league_id: int, kind: str, name: str, level: int | None = None) -> dict:
    kind = (kind or "").strip()
    if kind not in COMPETITION_KINDS:
        raise ValueError("Unknown competition type")
    name = (name or "").strip()
    if kind == "division":
        count = conn.execute(
            "SELECT COUNT(*) FROM competitions WHERE league_id = ? AND kind = 'division'",
            (league_id,),
        ).fetchone()[0]
        if count >= MAX_DIVISIONS:
            raise ValueError("A league can have at most 3 levels")
        level = count + 1
        name = name or f"Division {level}"
    elif kind == "cup":
        if conn.execute("SELECT 1 FROM competitions WHERE league_id = ? AND kind = 'cup'", (league_id,)).fetchone():
            raise ValueError("This league already has a cup")
        name = name or "Cup"
    elif kind == "ucl":
        if conn.execute("SELECT 1 FROM competitions WHERE league_id = ? AND kind = 'ucl'", (league_id,)).fetchone():
            raise ValueError("This league already has a Champions League")
        name = name or "Champions League"
    else:
        if not name:
            raise ValueError("Give the one-off competition a name")
    slug = slugify(name, kind)
    base = slug
    n = 2
    while conn.execute(
        "SELECT 1 FROM competitions WHERE league_id = ? AND slug = ?",
        (league_id, slug),
    ).fetchone():
        slug = f"{base}-{n}"
        n += 1
    conn.execute(
        """
        INSERT INTO competitions(league_id, slug, name, kind, level, status, created_at)
        VALUES (?, ?, ?, ?, ?, 'open', ?)
        """,
        (league_id, slug, name, kind, level, now_iso()),
    )
    conn.commit()
    saved = competition_by_slug(conn, league_id, slug)
    if not saved:
        raise ValueError("Could not create the competition")
    return saved


def enroll_team(conn: sqlite3.Connection, competition_id: int, team_id: int) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO competition_teams(competition_id, team_id) VALUES (?, ?)",
        (competition_id, team_id),
    )
    conn.commit()


def unenroll_team(conn: sqlite3.Connection, competition_id: int, team_id: int) -> None:
    conn.execute(
        "DELETE FROM competition_teams WHERE competition_id = ? AND team_id = ?",
        (competition_id, team_id),
    )
    conn.commit()


def competition_teams(conn: sqlite3.Connection, competition_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.*, u.name AS manager_name
        FROM competition_teams ct
        JOIN manager_teams t ON t.id = ct.team_id
        JOIN users u ON u.id = t.user_id
        WHERE ct.competition_id = ?
        ORDER BY t.name
        """,
        (competition_id,),
    )
    return [dict(row) for row in rows]


def enroll_missing_teams(conn: sqlite3.Connection, league_id: int, competition_id: int) -> None:
    teams = league_teams(conn, league_id)
    for team in teams:
        enroll_team(conn, competition_id, team["id"])


def _round_robin_rounds(team_ids: list[int]) -> list[list[tuple[int, int]]]:
    ids: list[int | None] = list(team_ids)
    if len(ids) < 2:
        return []
    if len(ids) % 2:
        ids.append(None)
    n = len(ids)
    rounds: list[list[tuple[int, int]]] = []
    for round_no in range(n - 1):
        pairs = []
        for i in range(n // 2):
            home, away = ids[i], ids[n - 1 - i]
            if home and away:
                if round_no % 2:
                    home, away = away, home
                pairs.append((home, away))
        rounds.append(pairs)
        ids = [ids[0]] + [ids[-1]] + ids[1:-1]
    return rounds


def generate_fixtures(conn: sqlite3.Connection, competition: dict, start_on: str | None = None) -> int:
    teams = competition_teams(conn, competition["id"])
    ids = [team["id"] for team in teams]
    if len(ids) < 2:
        raise ValueError("Add at least two clubs before building fixtures")
    conn.execute(
        "DELETE FROM fixtures WHERE competition_id = ? AND status = 'scheduled'",
        (competition["id"],),
    )
    start = _parse_start(start_on or now_iso()[:10])
    first_leg = _round_robin_rounds(ids)
    second_leg = [[(away, home) for home, away in round_pairs] for round_pairs in first_leg]
    week_no = 1
    created = 0
    for round_pairs in first_leg + second_leg:
        kickoff = _stamp(start, (week_no - 1) * 7, 18, 15)
        for home_id, away_id in round_pairs:
            conn.execute(
                """
                INSERT INTO fixtures(competition_id, home_team_id, away_team_id, kickoff, week_no, status)
                VALUES (?, ?, ?, ?, ?, 'scheduled')
                """,
                (competition["id"], home_id, away_id, kickoff, week_no),
            )
            created += 1
        week_no += 1
    conn.commit()
    return created


def add_fixture(
    conn: sqlite3.Connection,
    competition_id: int,
    home_team_id: int,
    away_team_id: int,
    kickoff: str,
) -> None:
    if int(home_team_id) == int(away_team_id):
        raise ValueError("A club cannot play itself")
    kickoff = (kickoff or "").replace("T", " ").strip()
    if not kickoff:
        raise ValueError("Set a match date")
    conn.execute(
        """
        INSERT INTO fixtures(competition_id, home_team_id, away_team_id, kickoff, status)
        VALUES (?, ?, ?, ?, 'scheduled')
        """,
        (competition_id, home_team_id, away_team_id, kickoff),
    )
    conn.commit()


def record_result(conn: sqlite3.Connection, fixture_id: int, home_goals: int, away_goals: int, user_id: int) -> None:
    if home_goals < 0 or away_goals < 0:
        raise ValueError("Goals cannot be negative")
    conn.execute(
        """
        UPDATE fixtures
        SET home_goals = ?, away_goals = ?, status = 'played', recorded_by = ?, recorded_at = ?
        WHERE id = ?
        """,
        (home_goals, away_goals, user_id, now_iso(), fixture_id),
    )
    conn.commit()


def _decorate_fixture(row: sqlite3.Row | dict) -> dict:
    item = dict(row)
    item["home_label"] = f"{item.get('home_manager') or ''} - {item.get('home_name') or ''}".strip(" -")
    item["away_label"] = f"{item.get('away_manager') or ''} - {item.get('away_name') or ''}".strip(" -")
    if item.get("status") == "played" and item.get("home_goals") is not None:
        item["score_label"] = f"{item['home_goals']} - {item['away_goals']}"
    else:
        item["score_label"] = "VS"
    return item


def list_fixtures(conn: sqlite3.Connection, competition_id: int, status: str | None = None) -> list[dict]:
    sql = """
        SELECT f.*,
               ht.name AS home_name, hu.name AS home_manager,
               at.name AS away_name, au.name AS away_manager
        FROM fixtures f
        JOIN manager_teams ht ON ht.id = f.home_team_id
        JOIN users hu ON hu.id = ht.user_id
        JOIN manager_teams at ON at.id = f.away_team_id
        JOIN users au ON au.id = at.user_id
        WHERE f.competition_id = ?
    """
    args: list = [competition_id]
    if status:
        sql += " AND f.status = ?"
        args.append(status)
    sql += " ORDER BY COALESCE(f.kickoff, ''), f.id"
    return [_decorate_fixture(row) for row in conn.execute(sql, args)]


def standings(conn: sqlite3.Connection, competition_id: int) -> list[dict]:
    teams = competition_teams(conn, competition_id)
    table = {
        team["id"]: {
            "team_id": team["id"],
            "name": team["name"],
            "manager_name": team["manager_name"],
            "label": f"{team['manager_name']} - {team['name']}",
            "gp": 0,
            "w": 0,
            "t": 0,
            "l": 0,
            "gf": 0,
            "ga": 0,
            "gd": 0,
            "pts": 0,
        }
        for team in teams
    }
    played = conn.execute(
        """
        SELECT home_team_id, away_team_id, home_goals, away_goals
        FROM fixtures
        WHERE competition_id = ? AND status = 'played'
        """,
        (competition_id,),
    )
    for row in played:
        home = table.get(row["home_team_id"])
        away = table.get(row["away_team_id"])
        if not home or not away:
            continue
        hg, ag = int(row["home_goals"]), int(row["away_goals"])
        home["gp"] += 1
        away["gp"] += 1
        home["gf"] += hg
        home["ga"] += ag
        away["gf"] += ag
        away["ga"] += hg
        if hg > ag:
            home["w"] += 1
            away["l"] += 1
            home["pts"] += 3
        elif hg < ag:
            away["w"] += 1
            home["l"] += 1
            away["pts"] += 3
        else:
            home["t"] += 1
            away["t"] += 1
            home["pts"] += 1
            away["pts"] += 1
    rows = list(table.values())
    for row in rows:
        row["gd"] = row["gf"] - row["ga"]
    rows.sort(key=lambda item: (-item["pts"], -item["gd"], -item["gf"], item["name"].lower()))
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def fixture_by_id(conn: sqlite3.Connection, fixture_id: int) -> dict | None:
    row = conn.execute(
        """
        SELECT f.*, c.league_id, c.slug AS competition_slug
        FROM fixtures f
        JOIN competitions c ON c.id = f.competition_id
        WHERE f.id = ?
        """,
        (fixture_id,),
    ).fetchone()
    return dict(row) if row else None


def remove_example_league(conn: sqlite3.Connection) -> None:
    row = conn.execute("SELECT id FROM leagues WHERE slug = 'nepes-s14'").fetchone()
    if not row:
        return
    league_id = row["id"]
    window_ids = [window["id"] for window in conn.execute("SELECT id FROM league_windows WHERE league_id = ?", (league_id,))]
    if window_ids:
        conn.execute(
            f"DELETE FROM window_actions WHERE window_id IN ({','.join('?' * len(window_ids))})",
            window_ids,
        )
    comp_ids = [row["id"] for row in conn.execute("SELECT id FROM competitions WHERE league_id = ?", (league_id,))]
    if comp_ids:
        marks = ",".join("?" * len(comp_ids))
        conn.execute(f"DELETE FROM fixtures WHERE competition_id IN ({marks})", comp_ids)
        conn.execute(f"DELETE FROM competition_teams WHERE competition_id IN ({marks})", comp_ids)
    conn.execute("DELETE FROM competitions WHERE league_id = ?", (league_id,))
    conn.execute("DELETE FROM join_requests WHERE league_id = ?", (league_id,))
    conn.execute("DELETE FROM league_officers WHERE league_id = ?", (league_id,))
    conn.execute("DELETE FROM transfer_offers WHERE league_id = ?", (league_id,))
    conn.execute("DELETE FROM sea_listings WHERE league_id = ?", (league_id,))
    conn.execute("DELETE FROM contracts WHERE league_id = ?", (league_id,))
    conn.execute("DELETE FROM league_windows WHERE league_id = ?", (league_id,))
    conn.execute("DELETE FROM manager_teams WHERE league_id = ?", (league_id,))
    conn.execute("DELETE FROM leagues WHERE id = ?", (league_id,))
    conn.commit()


def ensure_practice_league(conn: sqlite3.Connection) -> dict:
    row = conn.execute("SELECT * FROM leagues WHERE slug = 'manager-desk'").fetchone()
    if row:
        league = dict(row)
        stale = conn.execute(
            """
            SELECT 1 FROM league_windows
            WHERE league_id = ? AND (title LIKE ? OR title LIKE ?)
            """,
            (league["id"], "Open sea%", "%first legs%"),
        ).fetchone()
        if stale or not league.get("weeks"):
            apply_season_calendar(conn, {**league, "weeks": league.get("weeks") or 6})
        ensure_default_competitions(conn, league["id"])
        division = default_division(conn, league["id"])
        if division:
            enroll_missing_teams(conn, league["id"], division["id"])
            if not conn.execute(
                "SELECT 1 FROM fixtures WHERE competition_id = ? LIMIT 1",
                (division["id"],),
            ).fetchone():
                try:
                    generate_fixtures(conn, division, league.get("start_on"))
                except ValueError:
                    pass
        return dict(conn.execute("SELECT * FROM leagues WHERE id = ?", (league["id"],)).fetchone())
    conn.execute(
        """
        INSERT INTO leagues(slug, name, organizer_id, start_on, end_on, timezone, max_teams, weeks, starting_budget, status, notes, created_at)
        VALUES (?, ?, NULL, ?, ?, 'America/New_York', 16, 6, 1000, 'open', ?, ?)
        """,
        (
            "manager-desk",
            "Manager Desk · Practice Season",
            "2026-09-01",
            "2026-10-15",
            "Host sets name, max players, and weeks. The desk builds first half, winter, second half, and summer.",
            now_iso(),
        ),
    )
    league_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    apply_season_calendar(conn, {"id": league_id, "start_on": "2026-09-01", "weeks": 6})
    ensure_default_competitions(conn, league_id)
    return dict(conn.execute("SELECT * FROM leagues WHERE id = ?", (league_id,)).fetchone())
