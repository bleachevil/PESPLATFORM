from __future__ import annotations

import csv
import io
import json
import os
import sqlite3
import sys
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Optional
from urllib.parse import quote, urlencode

from fastapi import FastAPI, File, Form, Request, UploadFile
from pydantic import BeforeValidator
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates


def _blank_int(value: object) -> Optional[int]:
    if value is None or value == "":
        return None
    if isinstance(value, int):
        return value
    text = str(value).strip()
    if not text:
        return None
    return int(text)


BlankInt = Annotated[Optional[int], BeforeValidator(_blank_int)]

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from importer.fields import MODES, POSITION_GROUPS, POSITIONS, POSITION_LABELS
from importer.import_csv import DB_PATH, PLAYER_LIST_COLUMNS, import_csv, import_records, init_db, pesdb_player_url
from importer.scrape_pesdb import scrape_pesdb
from importer.locate import find_game_files, is_encrypted_wesys
from importer.cpk import CpkArchive
from importer.card_art import card_svg, find_image_file, official_card_png
from importer.growth import attach_growth
from importer.sample_data import sample_records
from importer.google_auth import (
    exchange_google_code,
    google_authorize_url,
    google_configured,
    pkce_pair,
    save_google_config,
    verify_google_id_token,
)
from importer.league import (
    accept_invite,
    add_fixture,
    apply_season_calendar,
    calendar_view,
    can_manage_league,
    clamp_weeks,
    competition_by_id,
    competition_by_slug,
    competition_teams,
    create_competition,
    create_league,
    create_session,
    decide_join,
    decide_offer,
    enroll_missing_teams,
    enroll_team,
    ensure_default_competitions,
    fixture_by_id,
    generate_fixtures,
    grant_officer,
    invite_manager,
    is_host,
    join_request_for,
    list_competitions,
    list_fixtures,
    list_join_requests,
    list_officers,
    update_window_times,
    attach_market,
    buyout_clause,
    clear_session,
    remove_example_league,
    ensure_practice_league,
    incoming_offers,
    is_new_manager,
    league_by_slug,
    league_teams,
    league_windows,
    list_leagues,
    manager_team,
    next_window,
    offer_transfer,
    open_windows,
    record_result,
    release_to_sea,
    request_join,
    revoke_officer,
    set_release_clause,
    sign_player,
    squad_rows,
    standings,
    unenroll_team,
    upsert_google_user,
    user_from_token,
    window_of,
)

WEB_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(WEB_DIR / "templates"))
app = FastAPI(title="PES Data")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.mount("/static", StaticFiles(directory=str(WEB_DIR / "static")), name="static")

UPLOADS = ROOT / "uploads"
UPLOADS.mkdir(parents=True, exist_ok=True)
MODE_COOKIE = "pesdata_mode"
SESSION_COOKIE = "pesdata_session"
LEAGUE_COOKIE = "pesdata_league"
OAUTH_COOKIE = "pesdata_oauth"


def get_db() -> sqlite3.Connection:
    conn = init_db(DB_PATH)
    remove_example_league(conn)
    ensure_practice_league(conn)
    return conn


def request_session_token(request: Request) -> Optional[str]:
    auth = request.headers.get("authorization") or ""
    if auth.lower().startswith("bearer "):
        return auth.split(" ", 1)[1].strip() or None
    return request.cookies.get(SESSION_COOKIE)


def current_user(request: Request, conn: sqlite3.Connection) -> Optional[dict]:
    return user_from_token(conn, request_session_token(request))


def selected_league(request: Request, conn: sqlite3.Connection) -> Optional[dict]:
    slug = request.cookies.get(LEAGUE_COOKIE) or ""
    if slug:
        league = league_by_slug(conn, slug)
        if league:
            return league
    leagues = list_leagues(conn)
    return leagues[0] if len(leagues) == 1 else None


def can_organize(user: Optional[dict], league: dict, team: Optional[dict]) -> bool:
    if not user:
        return False
    organizer_id = league.get("organizer_id")
    if organizer_id is not None and int(organizer_id) == int(user["id"]):
        return True
    return organizer_id is None and team is not None


def safe_next(url: str) -> str:
    return url if url.startswith("/") else "/"


def login_redirect(next_url: str = "/") -> RedirectResponse:
    return RedirectResponse(f"/login?next={quote(safe_next(next_url))}", status_code=303)


def set_session_cookie(response: Response, token: str) -> Response:
    response.set_cookie(SESSION_COOKIE, token, max_age=30 * 24 * 3600, httponly=True)
    return response


def start_google_session(profile: dict) -> tuple[dict, str]:
    conn = get_db()
    user = upsert_google_user(conn, profile["sub"], profile["email"], profile["name"])
    token = create_session(conn, user["id"])
    conn.close()
    return user, token


def set_league_cookie(response: Response, slug: str) -> Response:
    response.set_cookie(LEAGUE_COOKIE, slug, max_age=365 * 24 * 3600)
    return response


def google_origin(request: Request) -> str:
    return str(request.base_url).rstrip("/")


def google_callback_uri(request: Request) -> str:
    return f"{google_origin(request)}/auth/google/callback"


def meta_map(conn: sqlite3.Connection) -> dict[str, str]:
    return {row["key"]: row["value"] for row in conn.execute("SELECT key, value FROM meta")}


def current_mode(request: Request) -> str:
    query = request.query_params.get("mode")
    if query in MODES:
        return query
    cookie = request.cookies.get(MODE_COOKIE)
    if cookie in MODES:
        return cookie
    return "dream-team"


def player_view(row: sqlite3.Row) -> dict:
    data = dict(row)
    data["skills"] = json.loads(data.get("skills") or "[]")
    data["ai_styles"] = json.loads(data.get("ai_styles") or "[]")
    data["position_label"] = POSITION_LABELS.get(data.get("position") or "", data.get("position") or "")
    data["mode_label"] = MODES.get(data.get("mode") or "dream-team", "Dream Team")
    data["pack_slug"] = _slug(data.get("pack_name") or "")
    data["image_url"] = f"/art/{data.get('pid')}?v=4"
    data["source_url"] = pesdb_player_url(
        data.get("pid") or "",
        data.get("mode") or "dream-team",
        data.get("slug") or "",
        data.get("source_url") or "",
    )
    return attach_growth(data)


def _slug(value: str) -> str:
    import re
    return re.sub(r"[^a-z0-9]+", "-", (value or "").lower()).strip("-")


def ability_bar_color(value: int) -> str:
    if value >= 90:
        return "gold"
    if value >= 80:
        return "green"
    if value >= 70:
        return "blue"
    if value >= 60:
        return "gray"
    return "red"


def render(request: Request, template: str, status_code: int = 200, **context):
    mode = current_mode(request)
    conn = context.pop("_conn", None)
    if conn is None:
        conn = get_db()
    user = current_user(request, conn)
    league = context.get("league")
    if league is None:
        league = selected_league(request, conn)
    my_team = context.get("my_team")
    if my_team is None and league and user:
        my_team = manager_team(conn, league["id"], user["id"])
    opens = context.get("opens")
    if opens is None:
        opens = open_windows(conn, league["id"]) if league else []
    window = context.get("window")
    if window is None:
        window = opens[0] if opens else None
    context.update(
        request=request,
        mode=mode,
        mode_label=MODES[mode],
        modes=MODES,
        positions=POSITIONS,
        q=context.get("q", request.query_params.get("q", "")),
        user=user,
        league=league,
        my_team=my_team,
        opens=opens,
        window=window,
        sea_window=window_of(opens, "buy_sea", "auction"),
        clause_window=window_of(opens, "release_clause"),
        sea_release_window=window_of(opens, "release_sea"),
        transfer_window=window_of(opens, "transfer"),
        new_manager=is_new_manager(conn, my_team) if my_team else False,
        can_sign_free=bool(my_team and (window_of(opens, "buy_sea", "auction") or is_new_manager(conn, my_team))),
        next_sign_window=next_window(conn, league["id"], ["buy_sea", "auction"]) if league else None,
        can_manage=context.get("can_manage", can_manage_league(conn, user, league, my_team) if league else False),
        is_host=context.get("is_host", is_host(user, league) if league else False),
    )
    if conn is not None:
        conn.close()
    return templates.TemplateResponse(template, context, status_code=status_code)


templates.env.globals["bar_color"] = ability_bar_color
templates.env.globals["positions"] = POSITIONS
templates.env.globals["urlencode"] = lambda **kwargs: urlencode({k: v for k, v in kwargs.items() if v not in (None, "")})


@lru_cache(maxsize=1)
def game_status() -> dict:
    files = find_game_files()
    encrypted = None
    if files.live_cpk:
        try:
            archive = CpkArchive(files.live_cpk)
            player = next((f for f in archive.files if f.path.lower().endswith("player.bin")), None)
            if player:
                encrypted = is_encrypted_wesys(archive.read_file(player))
        except Exception as exc:  # noqa: BLE001
            encrypted = f"error: {exc}"
    return {
        "install_dir": str(files.install_dir) if files.install_dir else None,
        "live_cpk": str(files.live_cpk) if files.live_cpk else None,
        "live_cpk_mtime": files.live_cpk_mtime,
        "encrypted": encrypted,
    }


def counts(conn: sqlite3.Connection, mode: str) -> dict:
    total = conn.execute("SELECT COUNT(*) FROM players WHERE mode = ?", (mode,)).fetchone()[0]
    teams = conn.execute(
        "SELECT COUNT(DISTINCT team_slug) FROM players WHERE mode = ? AND team_slug != ''",
        (mode,),
    ).fetchone()[0]
    packs = conn.execute("SELECT COUNT(*) FROM packs").fetchone()[0]
    return {"players": total, "teams": teams, "packs": packs}


def latest_packs(conn: sqlite3.Connection, limit: int = 8) -> list[dict]:
    rows = conn.execute(
        """
        SELECT p.slug, p.name, p.released_on, p.kind,
               COUNT(pp.player_pid) AS player_count,
               MAX(pl.overall) AS top_ovr
        FROM packs p
        LEFT JOIN pack_players pp ON pp.pack_slug = p.slug
        LEFT JOIN players pl ON pl.pid = pp.player_pid
        GROUP BY p.slug
        ORDER BY p.released_on DESC, p.name
        LIMIT ?
        """,
        (limit,),
    )
    packs = []
    for row in rows:
        pack = dict(row)
        previews = conn.execute(
            """
            SELECT pl.*
            FROM pack_players pp
            JOIN players pl ON pl.pid = pp.player_pid
            WHERE pp.pack_slug = ?
            ORDER BY pl.overall DESC, pl.name
            LIMIT 4
            """,
            (pack["slug"],),
        )
        pack["previews"] = [player_view(preview) for preview in previews]
        packs.append(pack)
    return packs


def teams_for_mode(conn: sqlite3.Connection, mode: str) -> list[dict]:
    rows = conn.execute(
        """
        SELECT t.slug, t.name, t.league, t.region,
               COUNT(pl.id) AS player_count,
               ROUND(AVG(pl.overall), 1) AS avg_ovr,
               MAX(pl.overall) AS top_ovr
        FROM teams t
        JOIN players pl ON pl.team_slug = t.slug AND pl.mode = ?
        GROUP BY t.slug
        ORDER BY t.league, t.name
        """,
        (mode,),
    )
    return [dict(row) for row in rows]


@app.get("/mode/{mode}")
def set_mode(mode: str, next: str = "/"):
    if mode not in MODES:
        mode = "dream-team"
    safe_next = next if next.startswith("/") else "/"
    response = RedirectResponse(safe_next, status_code=303)
    response.set_cookie(MODE_COOKIE, mode, max_age=365 * 24 * 3600)
    return response


@app.get("/", response_class=HTMLResponse)
def home(request: Request):
    conn = get_db()
    stats = counts(conn, current_mode(request))
    leagues = list_leagues(conn)
    return render(
        request,
        "index.html",
        _conn=conn,
        stats=stats,
        leagues=leagues,
        league_count=len(leagues),
    )


def query_players(
    conn: sqlite3.Connection,
    mode: str,
    q: str = "",
    position: str = "",
    min_ovr: Optional[int] = None,
    skill: str = "",
    sort: str = "overall",
    limit: Optional[int] = None,
    card_type: str = "",
) -> list[sqlite3.Row]:
    sql = "SELECT * FROM players WHERE 1=1"
    params: list = []
    if mode:
        sql += " AND mode = ?"
        params.append(mode)
    if card_type:
        sql += " AND lower(card_type) = ?"
        params.append(card_type.strip().lower())
    if q:
        sql += (
            " AND (lower(name) LIKE ? OR lower(COALESCE(club, '')) LIKE ? "
            "OR lower(COALESCE(nationality, '')) LIKE ? OR lower(pid) LIKE ? "
            "OR lower(COALESCE(pack_name, '')) LIKE ?)"
        )
        like = f"%{q.strip().lower()}%"
        params.extend([like, like, like, like, like])
    if position:
        sql += " AND position = ?"
        params.append(position.upper())
    if min_ovr is not None:
        sql += " AND overall >= ?"
        params.append(min_ovr)
    if skill:
        sql += " AND lower(COALESCE(skills, '')) LIKE ?"
        params.append(f"%{skill.strip().lower()}%")
    if sort == "name":
        sql += " ORDER BY name COLLATE NOCASE"
    else:
        sql += " ORDER BY overall DESC, name"
    if limit:
        sql += " LIMIT ?"
        params.append(int(limit))
    return list(conn.execute(sql, params))


def card_types_for_mode(conn: sqlite3.Connection, mode: str) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT card_type FROM players WHERE mode = ? AND card_type != '' ORDER BY card_type",
        (mode,),
    )
    return [row[0] for row in rows]


@app.get("/players", response_class=HTMLResponse)
def players(
    request: Request,
    q: str = "",
    position: str = "",
    min_ovr: BlankInt = None,
    skill: str = "",
    sort: str = "overall",
    card_type: str = "",
):
    conn = get_db()
    mode = current_mode(request)
    league = selected_league(request, conn)
    rows = [
        player_view(r)
        for r in query_players(conn, "" if q.strip() else mode, q, position, min_ovr, skill, sort, limit=500, card_type=card_type)
    ]
    attach_market(conn, league, rows)
    meta = meta_map(conn)
    return render(
        request,
        "players.html",
        _conn=conn,
        league=league,
        players=rows,
        q=q,
        position=position,
        min_ovr=min_ovr or "",
        skill=skill,
        sort=sort,
        card_type=card_type,
        card_types=card_types_for_mode(conn, mode),
        meta=meta,
    )


@app.get("/players.csv")
def players_csv(
    request: Request,
    q: str = "",
    position: str = "",
    min_ovr: BlankInt = None,
    skill: str = "",
    sort: str = "overall",
    all_modes: int = 0,
    card_type: str = "",
):
    conn = get_db()
    if all_modes:
        rows = conn.execute(
            "SELECT * FROM players ORDER BY overall DESC, name COLLATE NOCASE"
        ).fetchall()
    else:
        rows = query_players(conn, current_mode(request), q, position, min_ovr, skill, sort, card_type=card_type)
    conn.close()
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow([label for label, _key in PLAYER_LIST_COLUMNS])
    for row in rows:
        data = dict(row)
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
    filename = "pesdata-players-all.csv" if all_modes else "pesdata-players.csv"
    return Response(
        content=buf.getvalue().encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.get("/players/{slug}", response_class=HTMLResponse)
def player_detail(request: Request, slug: str):
    conn = get_db()
    row = conn.execute("SELECT * FROM players WHERE slug = ? OR pid = ?", (slug, slug)).fetchone()
    if not row:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    player = player_view(row)
    league = selected_league(request, conn)
    attach_market(conn, league, [player])
    others = [
        player_view(r)
        for r in conn.execute(
            "SELECT * FROM players WHERE name = ? AND pid != ? ORDER BY mode, overall DESC",
            (player["name"], player["pid"]),
        )
    ]
    return render(request, "player.html", _conn=conn, league=league, player=player, others=others)


@app.get("/packs", response_class=HTMLResponse)
def packs_index(request: Request):
    conn = get_db()
    packs = latest_packs(conn, limit=50)
    conn.close()
    return render(request, "packs.html", packs=packs)


@app.get("/packs/{slug}", response_class=HTMLResponse)
def pack_detail(request: Request, slug: str):
    conn = get_db()
    pack = conn.execute("SELECT * FROM packs WHERE slug = ?", (slug,)).fetchone()
    if not pack:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    players = [
        player_view(r)
        for r in conn.execute(
            """
            SELECT pl.* FROM players pl
            JOIN pack_players pp ON pp.player_pid = pl.pid
            WHERE pp.pack_slug = ?
            ORDER BY pl.overall DESC, pl.name
            """,
            (slug,),
        )
    ]
    conn.close()
    return render(request, "pack.html", pack=dict(pack), players=players)


@app.get("/teams", response_class=HTMLResponse)
def teams_index(request: Request):
    conn = get_db()
    mode = current_mode(request)
    teams = teams_for_mode(conn, mode)
    leagues: dict[str, list[dict]] = {}
    for team in teams:
        leagues.setdefault(team["league"] or "Other", []).append(team)
    conn.close()
    return render(request, "teams.html", teams=teams, leagues=leagues)


@app.get("/teams/{slug}", response_class=HTMLResponse)
def team_detail(request: Request, slug: str):
    conn = get_db()
    mode = current_mode(request)
    team = conn.execute("SELECT * FROM teams WHERE slug = ?", (slug,)).fetchone()
    if not team:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    squad = [
        player_view(r)
        for r in conn.execute(
            "SELECT * FROM players WHERE team_slug = ? AND mode = ? ORDER BY overall DESC, name",
            (slug, mode),
        )
    ]
    grouped = []
    used = set()
    for label, positions in POSITION_GROUPS:
        group_players = [p for p in squad if p["position"] in positions]
        used.update(p["pid"] for p in group_players)
        grouped.append({"label": label, "players": group_players})
    leftover = [p for p in squad if p["pid"] not in used]
    if leftover:
        grouped.append({"label": "Other", "players": leftover})
    other_mode = "authentic" if mode == "dream-team" else "dream-team"
    other_count = conn.execute(
        "SELECT COUNT(*) FROM players WHERE team_slug = ? AND mode = ?",
        (slug, other_mode),
    ).fetchone()[0]
    conn.close()
    return render(
        request,
        "team.html",
        team=dict(team),
        squad=squad,
        grouped=grouped,
        other_mode=other_mode,
        other_mode_label=MODES[other_mode],
        other_count=other_count,
    )


@app.get("/compare", response_class=HTMLResponse)
def compare(request: Request, a: str = "", b: str = ""):
    conn = get_db()
    def load(pid_or_slug: str):
        if not pid_or_slug:
            return None
        row = conn.execute(
            "SELECT * FROM players WHERE slug = ? OR pid = ?",
            (pid_or_slug, pid_or_slug),
        ).fetchone()
        return player_view(row) if row else None

    left, right = load(a), load(b)
    suggestions = [
        player_view(r)
        for r in conn.execute("SELECT * FROM players ORDER BY name, mode, overall DESC LIMIT 400")
    ]
    conn.close()
    return render(
        request,
        "compare.html",
        left=left,
        right=right,
        suggestions=suggestions,
        a=a,
        b=b,
    )


@app.get("/import", response_class=HTMLResponse)
def import_page(request: Request, message: str = "", error: str = ""):
    return render(
        request,
        "import.html",
        message=message,
        error=error,
        game=game_status(),
    )


@app.post("/import")
async def import_upload(file: UploadFile = File(...)):
    if not file.filename or not file.filename.lower().endswith(".csv"):
        return RedirectResponse("/import?error=Please+upload+a+.csv+file", status_code=303)
    dest = UPLOADS / Path(file.filename).name
    dest.write_bytes(await file.read())
    try:
        result = import_csv(dest, source=f"upload:{dest.name}")
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(f"/import?error={quote(str(exc))}", status_code=303)
    return RedirectResponse(f"/import?message=Imported+{result['imported']}+players", status_code=303)


@app.post("/import/sample")
def import_sample():
    result = import_records(sample_records(), source="sample")
    return RedirectResponse(f"/import?message=Loaded+{result['imported']}+sample+players", status_code=303)


@app.post("/import/pesdb")
def import_pesdb(
    mode: str = Form("dream-team"),
    featured: str = Form(""),
    min_ovr: str = Form(""),
    pages: str = Form("15"),
):
    modes = ["dream-team", "authentic"] if mode == "both" else [mode if mode in MODES else "dream-team"]
    try:
        page_limit = int(pages or "15")
    except ValueError:
        page_limit = 15
    page_limit = min(max(page_limit, 1), 40)
    try:
        min_ovr_n = int(min_ovr) if min_ovr.strip() else None
    except ValueError:
        min_ovr_n = None
    try:
        result = scrape_pesdb(
            modes=modes,
            featured=featured in {"1", "on", "true", "yes"},
            min_ovr=min_ovr_n if min_ovr_n and min_ovr_n > 0 else None,
            max_pages=page_limit,
            delay=0.7,
            do_import=True,
            quiet=True,
        )
    except Exception as exc:  # noqa: BLE001
        return RedirectResponse(f"/import?error={quote(str(exc))}", status_code=303)
    message = f"Scraped {result['scraped']} pesdb players and imported {result['imported']}"
    return RedirectResponse(f"/import?message={quote(message)}", status_code=303)


@app.get("/art/{pid}")
def player_art(pid: str):
    import re
    if not re.fullmatch(r"[\w.-]+", pid):
        return Response(status_code=404)
    direct = find_image_file(pid)
    if direct:
        return FileResponse(direct)
    png = official_card_png(pid)
    if png:
        return Response(content=png, media_type="image/png")
    conn = get_db()
    row = conn.execute("SELECT * FROM players WHERE pid = ?", (pid,)).fetchone()
    conn.close()
    player = dict(row) if row else {"pid": pid, "name": pid, "position": "CF", "overall": 0}
    return Response(content=card_svg(player), media_type="image/svg+xml")


@app.get("/login", response_class=HTMLResponse)
def login_page(request: Request, next: str = "/", error: str = "", message: str = ""):
    return render(
        request,
        "login.html",
        next_url=safe_next(next),
        error=error,
        message=message,
        google_ready=google_configured(),
    )


@app.post("/login/google-setup")
def google_setup(
    client_id: str = Form(...),
    client_secret: str = Form(...),
    next: str = Form("/"),
):
    try:
        save_google_config(client_id, client_secret)
    except ValueError as exc:
        return RedirectResponse(f"/login?next={quote(safe_next(next))}&error={quote(str(exc))}", status_code=303)
    return RedirectResponse(
        f"/login?next={quote(safe_next(next))}&message={quote('Google is connected')}",
        status_code=303,
    )


@app.get("/auth/google")
def google_start(request: Request, next: str = "/"):
    state = os.urandom(16).hex()
    verifier, challenge = pkce_pair()
    try:
        url = google_authorize_url(google_callback_uri(request), state, challenge)
    except ValueError as exc:
        return RedirectResponse(f"/login?error={quote(str(exc))}", status_code=303)
    response = RedirectResponse(url, status_code=303)
    response.set_cookie(
        OAUTH_COOKIE,
        f"{state}:{safe_next(next)}:{verifier}",
        max_age=600,
        httponly=True,
        samesite="lax",
    )
    return response


@app.get("/auth/google/callback")
def google_callback(request: Request, code: str = "", state: str = "", error: str = ""):
    if error:
        return RedirectResponse(f"/login?error={quote('Google sign-in was cancelled')}", status_code=303)
    cookie = request.cookies.get(OAUTH_COOKIE) or ""
    parts = cookie.split(":")
    expected = parts[0] if parts else ""
    next_url = parts[1] if len(parts) > 1 else "/"
    verifier = parts[2] if len(parts) > 2 else ""
    if not code or not state or state != expected:
        return RedirectResponse("/login?error=Google+sign-in+expired.+Try+again", status_code=303)
    try:
        profile = exchange_google_code(code, google_callback_uri(request), verifier)
        _user, token = start_google_session(profile)
    except ValueError as exc:
        return RedirectResponse(f"/login?error={quote(str(exc))}", status_code=303)
    response = RedirectResponse(safe_next(next_url), status_code=303)
    response.delete_cookie(OAUTH_COOKIE)
    return set_session_cookie(response, token)


@app.post("/auth/google/token")
async def google_app_token(request: Request):
    try:
        payload = await request.json()
    except Exception:  # noqa: BLE001
        return JSONResponse({"error": "Send a Google ID token or auth code"}, status_code=400)
    try:
        if payload.get("id_token"):
            profile = verify_google_id_token(str(payload["id_token"]))
        elif payload.get("code"):
            profile = exchange_google_code(
                str(payload["code"]),
                str(payload.get("redirect_uri") or google_callback_uri(request)),
                str(payload.get("code_verifier") or ""),
            )
        else:
            return JSONResponse({"error": "Send id_token or code"}, status_code=400)
        user, token = start_google_session(profile)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=401)
    response = JSONResponse({"token": token, "user": user})
    return set_session_cookie(response, token)


@app.get("/register")
def register_page(next: str = "/leagues"):
    return RedirectResponse(f"/login?next={quote(safe_next(next))}", status_code=303)


@app.get("/logout")
def logout(request: Request):
    conn = get_db()
    clear_session(conn, request.cookies.get(SESSION_COOKIE))
    conn.close()
    response = RedirectResponse("/", status_code=303)
    response.delete_cookie(SESSION_COOKIE)
    return response


@app.get("/leagues", response_class=HTMLResponse)
def leagues_page(request: Request, message: str = "", error: str = ""):
    conn = get_db()
    user = current_user(request, conn)
    leagues = list_leagues(conn)
    pending = {}
    if user:
        for lg in leagues:
            req = join_request_for(conn, lg["id"], user["id"])
            if req:
                pending[lg["id"]] = req
    return render(request, "leagues.html", _conn=conn, leagues=leagues, pending=pending, message=message, error=error)


@app.post("/leagues/create")
def leagues_create(
    request: Request,
    name: str = Form(...),
    max_teams: int = Form(16),
    weeks: int = Form(6),
):
    conn = get_db()
    user = current_user(request, conn)
    if not user:
        conn.close()
        return login_redirect("/leagues")
    league = create_league(conn, name, user["id"], max_teams, clamp_weeks(weeks))
    conn.close()
    response = RedirectResponse(f"/league/{league['slug']}", status_code=303)
    return set_league_cookie(response, league["slug"])


def _competition_page_data(conn, league: dict, comp_slug: str = ""):
    ensure_default_competitions(conn, league["id"])
    competitions = list_competitions(conn, league["id"])
    current = competition_by_slug(conn, league["id"], comp_slug) if comp_slug else None
    if not current and competitions:
        current = competitions[0]
    table = standings(conn, current["id"]) if current else []
    results = list_fixtures(conn, current["id"], "played") if current else []
    upcoming = list_fixtures(conn, current["id"], "scheduled") if current else []
    enrolled = competition_teams(conn, current["id"]) if current else []
    return {
        "competitions": competitions,
        "current": current,
        "table": table,
        "results": list(reversed(results)),
        "upcoming": upcoming,
        "enrolled": enrolled,
    }


@app.get("/league/{slug}", response_class=HTMLResponse)
def league_home(request: Request, slug: str, comp: str = "", message: str = "", error: str = ""):
    conn = get_db()
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    user = current_user(request, conn)
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    inbox = incoming_offers(conn, league["id"], my_team["id"]) if my_team else []
    windows = league_windows(conn, league["id"])
    opens = open_windows(conn, league["id"])
    data = _competition_page_data(conn, league, comp)
    my_request = join_request_for(conn, league["id"], user["id"]) if user and not my_team else None
    response = render(
        request,
        "league.html",
        _conn=conn,
        league=league,
        my_team=my_team,
        my_request=my_request,
        teams=league_teams(conn, league["id"]),
        windows=windows,
        opens=opens,
        calendar=calendar_view(windows, {row["id"] for row in opens}),
        inbox=inbox,
        is_organizer=can_organize(user, league, my_team),
        can_manage=can_manage_league(conn, user, league, my_team),
        **data,
        message=message,
        error=error,
    )
    response.set_cookie(LEAGUE_COOKIE, league["slug"], max_age=365 * 24 * 3600)
    return response


@app.post("/league/{slug}/join")
def league_join(request: Request, slug: str, team_name: str = Form(...)):
    conn = get_db()
    user = current_user(request, conn)
    if not user:
        conn.close()
        return login_redirect(f"/league/{slug}")
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    try:
        request_join(conn, league, user, team_name)
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/league/{slug}?error={quote(str(exc))}", status_code=303)
    conn.close()
    response = RedirectResponse(f"/league/{slug}?message={quote('Join request sent. Wait for a host or officer to approve it.')}", status_code=303)
    return set_league_cookie(response, slug)


@app.post("/league/{slug}/invite/accept")
def league_accept_invite(request: Request, slug: str):
    conn = get_db()
    user = current_user(request, conn)
    if not user:
        conn.close()
        return login_redirect(f"/league/{slug}")
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    try:
        accept_invite(conn, league, user)
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/league/{slug}?error={quote(str(exc))}", status_code=303)
    conn.close()
    response = RedirectResponse(f"/market?message={quote('You are in the league. Sign available players here.')}", status_code=303)
    return set_league_cookie(response, slug)


@app.get("/league/{slug}/organize", response_class=HTMLResponse)
def organize_page(request: Request, slug: str, message: str = "", error: str = ""):
    conn = get_db()
    user = current_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    if not can_manage_league(conn, user, league, my_team):
        conn.close()
        return RedirectResponse(f"/league/{slug}?error={quote('Only the host or an officer can manage this league')}", status_code=303)
    windows = league_windows(conn, league["id"])
    ensure_default_competitions(conn, league["id"])
    return render(
        request,
        "organize.html",
        _conn=conn,
        league=league,
        my_team=my_team,
        windows=windows,
        calendar=calendar_view(windows),
        officers=list_officers(conn, league["id"]),
        join_requests=list_join_requests(conn, league["id"]),
        competitions=list_competitions(conn, league["id"]),
        teams=league_teams(conn, league["id"]),
        can_manage=can_manage_league(conn, user, league, my_team),
        is_host=is_host(user, league) or can_organize(user, league, my_team),
        message=message,
        error=error,
    )


@app.post("/league/{slug}/organize")
async def organize_save(request: Request, slug: str):
    conn = get_db()
    user = current_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    if not can_organize(user, league, my_team):
        conn.close()
        return RedirectResponse(f"/league/{slug}?error={quote('Only the organizer can edit this league')}", status_code=303)
    form = await request.form()
    name = str(form.get("name") or league["name"]).strip() or league["name"]
    start_on = str(form.get("start_on") or league["start_on"] or "").strip()
    weeks = clamp_weeks(form.get("weeks") or league.get("weeks") or 6)
    max_teams = int(form.get("max_teams") or league["max_teams"] or 16)
    status = str(form.get("status") or league["status"] or "open")
    conn.execute(
        """
        UPDATE leagues
        SET name = ?, start_on = ?, max_teams = ?, weeks = ?, status = ?
        WHERE id = ?
        """,
        (name, start_on, max_teams, weeks, status, league["id"]),
    )
    conn.commit()
    updated = dict(conn.execute("SELECT * FROM leagues WHERE id = ?", (league["id"],)).fetchone())
    apply_season_calendar(conn, updated)
    conn.close()
    return RedirectResponse(f"/league/{slug}/organize?message={quote('League settings saved')}", status_code=303)


@app.post("/league/{slug}/calendar")
def organize_calendar(request: Request, slug: str):
    conn = get_db()
    user = current_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    if not can_organize(user, league, my_team):
        conn.close()
        return RedirectResponse(f"/league/{slug}?error={quote('Only the organizer can edit this league')}", status_code=303)
    apply_season_calendar(conn, league)
    conn.close()
    return RedirectResponse(f"/league/{slug}/organize?message={quote('Calendar rebuilt from name, weeks, and start date')}", status_code=303)


def _manage_context(request: Request, conn, slug: str):
    user = current_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        return None, render(request, "not_found.html", status_code=404)
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    if not can_manage_league(conn, user, league, my_team):
        return None, RedirectResponse(f"/league/{slug}?error={quote('Only the host or an officer can do that')}", status_code=303)
    return {"user": user, "league": league, "my_team": my_team}, None


@app.post("/league/{slug}/officers")
def add_officer(request: Request, slug: str, email: str = Form(...)):
    conn = get_db()
    ctx, err = _manage_context(request, conn, slug)
    if err:
        conn.close()
        return err
    if not (is_host(ctx["user"], ctx["league"]) or can_organize(ctx["user"], ctx["league"], ctx["my_team"])):
        conn.close()
        return RedirectResponse(f"/league/{slug}?error={quote('Only the host can grant officers')}", status_code=303)
    try:
        grant_officer(conn, ctx["league"], email)
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/league/{slug}/organize?error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse(f"/league/{slug}/organize?message={quote('Officer added')}", status_code=303)


@app.post("/league/{slug}/officers/{user_id}/revoke")
def remove_officer(request: Request, slug: str, user_id: int):
    conn = get_db()
    ctx, err = _manage_context(request, conn, slug)
    if err:
        conn.close()
        return err
    if not (is_host(ctx["user"], ctx["league"]) or can_organize(ctx["user"], ctx["league"], ctx["my_team"])):
        conn.close()
        return RedirectResponse(f"/league/{slug}?error={quote('Only the host can remove officers')}", status_code=303)
    revoke_officer(conn, ctx["league"]["id"], user_id)
    conn.close()
    return RedirectResponse(f"/league/{slug}/organize?message={quote('Officer removed')}", status_code=303)


@app.post("/league/{slug}/invite")
def send_invite(request: Request, slug: str, email: str = Form(...), team_name: str = Form("")):
    conn = get_db()
    ctx, err = _manage_context(request, conn, slug)
    if err:
        conn.close()
        return err
    try:
        invite_manager(conn, ctx["league"], email, team_name)
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/league/{slug}/organize?error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse(f"/league/{slug}/organize?message={quote('Invitation sent')}", status_code=303)


@app.post("/league/{slug}/requests/{request_id}/decide")
def decide_request(request: Request, slug: str, request_id: int, accept: str = Form(...)):
    conn = get_db()
    ctx, err = _manage_context(request, conn, slug)
    if err:
        conn.close()
        return err
    try:
        decide_join(conn, ctx["league"], request_id, accept == "1", ctx["user"])
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/league/{slug}/organize?error={quote(str(exc))}", status_code=303)
    conn.close()
    note = "Join approved" if accept == "1" else "Join rejected"
    return RedirectResponse(f"/league/{slug}/organize?message={quote(note)}", status_code=303)


@app.post("/league/{slug}/competitions")
def add_competition(request: Request, slug: str, kind: str = Form(...), name: str = Form("")):
    conn = get_db()
    ctx, err = _manage_context(request, conn, slug)
    if err:
        conn.close()
        return err
    try:
        created = create_competition(conn, ctx["league"]["id"], kind, name)
        if created["kind"] == "division":
            enroll_missing_teams(conn, ctx["league"]["id"], created["id"])
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/league/{slug}/organize?error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse(f"/league/{slug}/organize?message={quote('Competition added')}", status_code=303)


@app.post("/league/{slug}/competitions/{comp_id}/enroll")
def enroll_club(request: Request, slug: str, comp_id: int, team_id: int = Form(...)):
    conn = get_db()
    ctx, err = _manage_context(request, conn, slug)
    if err:
        conn.close()
        return err
    competition = competition_by_id(conn, comp_id)
    if not competition or competition["league_id"] != ctx["league"]["id"]:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    enroll_team(conn, comp_id, team_id)
    conn.close()
    return RedirectResponse(f"/league/{slug}?comp={quote(competition['slug'])}&message={quote('Club added to this competition')}", status_code=303)


@app.post("/league/{slug}/competitions/{comp_id}/unenroll")
def drop_club(request: Request, slug: str, comp_id: int, team_id: int = Form(...)):
    conn = get_db()
    ctx, err = _manage_context(request, conn, slug)
    if err:
        conn.close()
        return err
    competition = competition_by_id(conn, comp_id)
    if not competition or competition["league_id"] != ctx["league"]["id"]:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    unenroll_team(conn, comp_id, team_id)
    conn.close()
    return RedirectResponse(f"/league/{slug}?comp={quote(competition['slug'])}&message={quote('Club removed from this competition')}", status_code=303)


@app.post("/league/{slug}/competitions/{comp_id}/fixtures")
def build_fixtures(request: Request, slug: str, comp_id: int):
    conn = get_db()
    ctx, err = _manage_context(request, conn, slug)
    if err:
        conn.close()
        return err
    competition = competition_by_id(conn, comp_id)
    if not competition or competition["league_id"] != ctx["league"]["id"]:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    try:
        count = generate_fixtures(conn, competition, ctx["league"].get("start_on"))
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/league/{slug}?comp={quote(competition['slug'])}&error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse(f"/league/{slug}?comp={quote(competition['slug'])}&message={quote(f'{count} fixtures built')}", status_code=303)


@app.post("/league/{slug}/competitions/{comp_id}/match")
def create_match(
    request: Request,
    slug: str,
    comp_id: int,
    home_team_id: int = Form(...),
    away_team_id: int = Form(...),
    kickoff: str = Form(...),
):
    conn = get_db()
    ctx, err = _manage_context(request, conn, slug)
    if err:
        conn.close()
        return err
    competition = competition_by_id(conn, comp_id)
    if not competition or competition["league_id"] != ctx["league"]["id"]:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    try:
        enroll_team(conn, comp_id, home_team_id)
        enroll_team(conn, comp_id, away_team_id)
        add_fixture(conn, comp_id, home_team_id, away_team_id, kickoff)
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/league/{slug}?comp={quote(competition['slug'])}&error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse(f"/league/{slug}?comp={quote(competition['slug'])}&message={quote('Match added')}", status_code=303)


@app.post("/league/{slug}/fixtures/{fixture_id}/result")
def save_result(request: Request, slug: str, fixture_id: int, home_goals: int = Form(...), away_goals: int = Form(...)):
    conn = get_db()
    ctx, err = _manage_context(request, conn, slug)
    if err:
        conn.close()
        return err
    fixture = fixture_by_id(conn, fixture_id)
    if not fixture or fixture["league_id"] != ctx["league"]["id"]:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    try:
        record_result(conn, fixture_id, home_goals, away_goals, ctx["user"]["id"])
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/league/{slug}?comp={quote(fixture['competition_slug'])}&error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse(f"/league/{slug}?comp={quote(fixture['competition_slug'])}&message={quote('Result saved')}", status_code=303)


@app.post("/league/{slug}/windows")
async def save_window_times(request: Request, slug: str):
    conn = get_db()
    user = current_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        return render(request, "not_found.html", status_code=404)
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    if not can_organize(user, league, my_team):
        conn.close()
        return RedirectResponse(f"/league/{slug}?error={quote('Only the organizer can edit window times')}", status_code=303)
    form = await request.form()
    ids = form.getlist("w_id")
    starts = form.getlist("w_start")
    ends = form.getlist("w_end")
    updates = []
    for index, raw_id in enumerate(ids):
        try:
            window_id = int(raw_id)
        except ValueError:
            continue
        start = str(starts[index] if index < len(starts) else "").replace("T", " ").strip()
        end = str(ends[index] if index < len(ends) else "").replace("T", " ").strip()
        if start and end:
            updates.append({"id": window_id, "starts_at": start, "ends_at": end})
    update_window_times(conn, league["id"], updates)
    conn.close()
    return RedirectResponse(f"/league/{slug}?message={quote('Window times saved')}", status_code=303)


@app.get("/market", response_class=HTMLResponse)
def market_page(
    request: Request,
    q: str = "",
    position: str = "",
    min_ovr: BlankInt = None,
    status: str = "",
    card_type: str = "",
    message: str = "",
    error: str = "",
):
    conn = get_db()
    league = selected_league(request, conn)
    user = current_user(request, conn)
    my_team = manager_team(conn, league["id"], user["id"]) if user and league else None
    if not my_team:
        conn.close()
        return RedirectResponse(
            f"/leagues?message={quote('Join a league first. After you are in a club, the market opens.')}",
            status_code=303,
        )
    mode = current_mode(request)
    rows = [
        player_view(r)
        for r in query_players(conn, "" if q.strip() else mode, q, position, min_ovr, limit=500, card_type=card_type)
    ]
    attach_market(conn, league, rows)
    if status:
        rows = [row for row in rows if row.get("market_status", {}).get("code") == status]
    return render(
        request,
        "market.html",
        _conn=conn,
        league=league,
        players=rows,
        q=q,
        position=position,
        min_ovr=min_ovr or "",
        status=status,
        card_type=card_type,
        card_types=card_types_for_mode(conn, mode),
        message=message,
        error=error,
    )


@app.post("/market/sign")
def market_sign(request: Request, pid: str = Form(...)):
    conn = get_db()
    user = current_user(request, conn)
    if not user:
        conn.close()
        return login_redirect("/market")
    league = selected_league(request, conn)
    if not league:
        conn.close()
        return RedirectResponse("/leagues?error=Pick+a+league+first", status_code=303)
    team = manager_team(conn, league["id"], user["id"])
    if not team:
        conn.close()
        return RedirectResponse(f"/league/{league['slug']}?error=Register+a+club+first", status_code=303)
    row = conn.execute("SELECT * FROM players WHERE pid = ?", (pid,)).fetchone()
    if not row:
        conn.close()
        return RedirectResponse("/market?error=Player+not+found", status_code=303)
    player = player_view(row)
    try:
        sign_player(conn, league, team, player, window_of(open_windows(conn, league["id"]), "buy_sea", "auction"))
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/market?error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse(f"/squad?message={quote('Signed ' + player['name'])}", status_code=303)


@app.post("/market/buyout")
def market_buyout(request: Request, pid: str = Form(...)):
    conn = get_db()
    user = current_user(request, conn)
    if not user:
        conn.close()
        return login_redirect("/market")
    league = selected_league(request, conn)
    team = manager_team(conn, league["id"], user["id"]) if league else None
    if not league or not team:
        conn.close()
        return RedirectResponse("/leagues", status_code=303)
    try:
        buyout_clause(conn, league, team, pid, window_of(open_windows(conn, league["id"]), "release_clause"))
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/market?error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse("/squad?message=Buyout+complete", status_code=303)


@app.get("/squad", response_class=HTMLResponse)
def squad_page(request: Request, message: str = "", error: str = ""):
    conn = get_db()
    user = current_user(request, conn)
    if not user:
        conn.close()
        return login_redirect("/squad")
    league = selected_league(request, conn)
    if not league:
        conn.close()
        return RedirectResponse("/leagues?error=Pick+a+league+first", status_code=303)
    team = manager_team(conn, league["id"], user["id"])
    if not team:
        conn.close()
        return RedirectResponse(f"/league/{league['slug']}?error=Register+a+club+first", status_code=303)
    players = [player_view(row) for row in squad_rows(conn, league["id"], team["id"])]
    others = [row for row in league_teams(conn, league["id"]) if row["id"] != team["id"]]
    return render(
        request,
        "squad.html",
        _conn=conn,
        league=league,
        my_team=team,
        players=players,
        other_teams=others,
        message=message,
        error=error,
    )


@app.post("/squad/release")
def squad_release(request: Request, pid: str = Form(...)):
    conn = get_db()
    user = current_user(request, conn)
    league = selected_league(request, conn)
    team = manager_team(conn, league["id"], user["id"]) if user and league else None
    if not team:
        conn.close()
        return login_redirect("/squad")
    try:
        release_to_sea(conn, league, team, pid, window_of(open_windows(conn, league["id"]), "release_sea"))
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/squad?error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse("/squad?message=Released+to+the+sea", status_code=303)


@app.post("/squad/clause")
def squad_clause(request: Request, pid: str = Form(...), clause: int = Form(...)):
    conn = get_db()
    user = current_user(request, conn)
    league = selected_league(request, conn)
    team = manager_team(conn, league["id"], user["id"]) if user and league else None
    if not team:
        conn.close()
        return login_redirect("/squad")
    try:
        set_release_clause(conn, league, team, pid, clause, window_of(open_windows(conn, league["id"]), "release_clause"))
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/squad?error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse("/squad?message=Release+clause+set", status_code=303)


@app.post("/squad/offer")
def squad_offer(
    request: Request,
    pid: str = Form(...),
    to_team_id: int = Form(...),
    fee: int = Form(...),
    kind: str = Form("transfer"),
):
    conn = get_db()
    user = current_user(request, conn)
    league = selected_league(request, conn)
    team = manager_team(conn, league["id"], user["id"]) if user and league else None
    if not team:
        conn.close()
        return login_redirect("/squad")
    try:
        offer_transfer(
            conn,
            league,
            team,
            to_team_id,
            pid,
            fee,
            kind if kind == "loan" else "transfer",
            window_of(open_windows(conn, league["id"]), "transfer"),
        )
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/squad?error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse("/squad?message=Offer+sent", status_code=303)


@app.post("/offers/{offer_id}/decide")
def offer_decide(request: Request, offer_id: int, accept: str = Form("0")):
    conn = get_db()
    user = current_user(request, conn)
    league = selected_league(request, conn)
    team = manager_team(conn, league["id"], user["id"]) if user and league else None
    if not team:
        conn.close()
        return login_redirect("/leagues")
    try:
        decide_offer(conn, league, team, offer_id, accept in {"1", "true", "on"})
    except ValueError as exc:
        conn.close()
        return RedirectResponse(f"/league/{league['slug']}?error={quote(str(exc))}", status_code=303)
    conn.close()
    return RedirectResponse(f"/league/{league['slug']}?message=Offer+updated", status_code=303)


@app.get("/health")
def health():
    return {"ok": True}


from web.api import router as api_router

app.include_router(api_router)
