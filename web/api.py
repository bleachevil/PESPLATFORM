"""JSON API for the Manager Desk Android app."""

from __future__ import annotations

from typing import Annotated, Optional

from fastapi import APIRouter, Header, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, BeforeValidator, Field


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

from importer.fields import ABILITIES, MODES, POSITIONS
from importer.google_auth import (
    exchange_google_code,
    google_configured,
    load_google_config,
    verify_google_id_token,
)
from importer.league import (
    accept_invite,
    add_fixture,
    apply_season_calendar,
    attach_market,
    buyout_clause,
    calendar_view,
    can_manage_league,
    clamp_weeks,
    clear_session,
    competition_by_id,
    competition_teams,
    create_competition,
    create_league,
    decide_join,
    decide_offer,
    enroll_missing_teams,
    enroll_team,
    ensure_default_competitions,
    fixture_by_id,
    generate_fixtures,
    grant_officer,
    incoming_offers,
    invite_manager,
    is_host,
    is_new_manager,
    join_request_for,
    league_by_slug,
    league_teams,
    league_windows,
    list_competitions,
    list_fixtures,
    list_join_requests,
    list_leagues,
    list_officers,
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
    update_window_times,
    window_of,
)

router = APIRouter(prefix="/api")

PLAYER_LIST_KEYS = (
    "pid",
    "slug",
    "name",
    "position",
    "position_label",
    "overall",
    "max_overall",
    "level",
    "max_level",
    "card_type",
    "pack_name",
    "pack_slug",
    "club",
    "nationality",
    "mode",
    "mode_label",
    "image_url",
    "market_price",
    "market_status",
    "fee",
    "release_clause",
    "skills",
    "ai_styles",
)


def _web():
    from web import app as webapp

    return webapp


def _json_error(message: str, status: int = 400) -> JSONResponse:
    return JSONResponse({"error": message}, status_code=status)


def _player_card(player: dict) -> dict:
    return {key: player.get(key) for key in PLAYER_LIST_KEYS}


def _league_slug(request: Request, league_header: str | None = None) -> str:
    return (league_header or request.headers.get("x-league-slug") or request.query_params.get("league") or "").strip()


def _selected_league(request: Request, conn, league_header: str | None = None):
    web = _web()
    slug = _league_slug(request, league_header)
    if slug:
        league = league_by_slug(conn, slug)
        if league:
            return league
    return web.selected_league(request, conn)


def _desk_flags(conn, user, league, my_team, opens):
    sea = window_of(opens, "buy_sea", "auction")
    new_manager = is_new_manager(conn, my_team) if my_team else False
    return {
        "opens": opens,
        "window": opens[0] if opens else None,
        "sea_window": sea,
        "clause_window": window_of(opens, "release_clause"),
        "sea_release_window": window_of(opens, "release_sea"),
        "transfer_window": window_of(opens, "transfer"),
        "new_manager": new_manager,
        "can_sign_free": bool(my_team and (sea or new_manager)),
        "next_sign_window": next_window(conn, league["id"], ["buy_sea", "auction"]) if league else None,
        "can_manage": can_manage_league(conn, user, league, my_team) if league else False,
        "is_host": is_host(user, league) if league else False,
        "is_organizer": _web().can_organize(user, league, my_team) if league and user else False,
    }


def _me_payload(request: Request, conn, league_header: str | None = None) -> dict:
    web = _web()
    user = web.current_user(request, conn)
    league = _selected_league(request, conn, league_header)
    my_team = manager_team(conn, league["id"], user["id"]) if league and user else None
    opens = open_windows(conn, league["id"]) if league else []
    stats = web.counts(conn, web.current_mode(request))
    payload = {
        "user": user,
        "league": league,
        "my_team": my_team,
        "league_count": len(list_leagues(conn)),
        "stats": stats,
        "google_ready": google_configured(),
        **_desk_flags(conn, user, league, my_team, opens),
    }
    return payload


def _require_user(request: Request, conn):
    user = _web().current_user(request, conn)
    if not user:
        raise HTTPException(status_code=401, detail="Sign in required")
    return user


def _require_league(request: Request, conn, league_header: str | None = None):
    league = _selected_league(request, conn, league_header)
    if not league:
        raise HTTPException(status_code=400, detail="Pick a league first")
    return league


def _manage(request: Request, conn, slug: str):
    web = _web()
    user = web.current_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        raise HTTPException(status_code=404, detail="League not found")
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    if not can_manage_league(conn, user, league, my_team):
        raise HTTPException(status_code=403, detail="Only the host or an officer can do that")
    return user, league, my_team


def _competition_payload(conn, league: dict, comp_slug: str = "") -> dict:
    ensure_default_competitions(conn, league["id"])
    competitions = list_competitions(conn, league["id"])
    current = None
    if comp_slug:
        current = next((row for row in competitions if row["slug"] == comp_slug), None)
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


class GoogleAuthIn(BaseModel):
    id_token: Optional[str] = None
    code: Optional[str] = None
    redirect_uri: Optional[str] = None
    code_verifier: Optional[str] = None


class LeagueSlugIn(BaseModel):
    slug: str


class CreateLeagueIn(BaseModel):
    name: str
    max_teams: int = 16
    weeks: int = 6


class JoinIn(BaseModel):
    team_name: str


class PidIn(BaseModel):
    pid: str


class ClauseIn(BaseModel):
    pid: str
    clause: int


class OfferIn(BaseModel):
    pid: str
    to_team_id: int
    fee: int
    kind: str = "transfer"


class DecideIn(BaseModel):
    accept: bool = False


class OrganizeIn(BaseModel):
    name: Optional[str] = None
    start_on: Optional[str] = None
    weeks: Optional[int] = None
    max_teams: Optional[int] = None
    status: Optional[str] = None


class WindowTimeIn(BaseModel):
    id: int
    starts_at: str
    ends_at: str


class WindowsIn(BaseModel):
    windows: list[WindowTimeIn]


class EmailIn(BaseModel):
    email: str
    team_name: str = ""


class CompetitionIn(BaseModel):
    kind: str
    name: str = ""


class EnrollIn(BaseModel):
    team_id: int


class MatchIn(BaseModel):
    home_team_id: int
    away_team_id: int
    kickoff: str


class ResultIn(BaseModel):
    home_goals: int = Field(ge=0)
    away_goals: int = Field(ge=0)


@router.get("/config")
def api_config():
    config = load_google_config()
    return {
        "google_ready": google_configured(),
        "google_client_id": config["client_id"],
        "modes": MODES,
        "positions": POSITIONS,
        "abilities": [{"key": key, "label": label, "group": group} for key, label, group in ABILITIES],
    }


@router.post("/auth/google")
async def api_google_auth(body: GoogleAuthIn, request: Request):
    web = _web()
    try:
        if body.id_token:
            profile = verify_google_id_token(body.id_token)
        elif body.code:
            profile = exchange_google_code(
                body.code,
                body.redirect_uri or web.google_callback_uri(request),
                body.code_verifier or "",
            )
        else:
            return _json_error("Send id_token or code")
        user, token = web.start_google_session(profile)
    except ValueError as exc:
        return _json_error(str(exc), 401)
    response = JSONResponse({"token": token, "user": user})
    web.set_session_cookie(response, token)
    return response


@router.post("/auth/logout")
def api_logout(request: Request):
    web = _web()
    conn = web.get_db()
    clear_session(conn, web.request_session_token(request))
    conn.close()
    response = JSONResponse({"ok": True})
    response.delete_cookie(web.SESSION_COOKIE)
    return response


@router.get("/me")
def api_me(request: Request, x_league_slug: Optional[str] = Header(default=None)):
    web = _web()
    conn = web.get_db()
    payload = _me_payload(request, conn, x_league_slug)
    conn.close()
    return payload


@router.post("/me/league")
def api_select_league(body: LeagueSlugIn, request: Request):
    web = _web()
    conn = web.get_db()
    league = league_by_slug(conn, body.slug)
    if not league:
        conn.close()
        raise HTTPException(status_code=404, detail="League not found")
    payload = _me_payload(request, conn, body.slug)
    conn.close()
    response = JSONResponse(payload)
    web.set_league_cookie(response, league["slug"])
    return response


@router.get("/home")
def api_home(request: Request, x_league_slug: Optional[str] = Header(default=None)):
    web = _web()
    conn = web.get_db()
    payload = _me_payload(request, conn, x_league_slug)
    payload["leagues"] = list_leagues(conn)
    conn.close()
    return payload


@router.get("/leagues")
def api_leagues(request: Request):
    web = _web()
    conn = web.get_db()
    user = web.current_user(request, conn)
    leagues = list_leagues(conn)
    pending = {}
    if user:
        for lg in leagues:
            req = join_request_for(conn, lg["id"], user["id"])
            if req:
                pending[str(lg["id"])] = req
    conn.close()
    return {"leagues": leagues, "pending": pending, "user": user}


@router.post("/leagues")
def api_create_league(body: CreateLeagueIn, request: Request):
    web = _web()
    conn = web.get_db()
    user = _require_user(request, conn)
    league = create_league(conn, body.name, user["id"], body.max_teams, clamp_weeks(body.weeks))
    conn.close()
    return {"league": league}


@router.get("/league/{slug}")
def api_league(slug: str, request: Request, comp: str = ""):
    web = _web()
    conn = web.get_db()
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        raise HTTPException(status_code=404, detail="League not found")
    user = web.current_user(request, conn)
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    inbox = incoming_offers(conn, league["id"], my_team["id"]) if my_team else []
    windows = league_windows(conn, league["id"])
    opens = open_windows(conn, league["id"])
    data = _competition_payload(conn, league, comp)
    my_request = join_request_for(conn, league["id"], user["id"]) if user and not my_team else None
    payload = {
        "league": league,
        "user": user,
        "my_team": my_team,
        "my_request": my_request,
        "teams": league_teams(conn, league["id"]),
        "windows": windows,
        "calendar": calendar_view(windows, {row["id"] for row in opens}),
        "inbox": inbox,
        **_desk_flags(conn, user, league, my_team, opens),
        **data,
    }
    conn.close()
    response = JSONResponse(payload)
    web.set_league_cookie(response, league["slug"])
    return response


@router.post("/league/{slug}/join")
def api_join(slug: str, body: JoinIn, request: Request):
    web = _web()
    conn = web.get_db()
    user = _require_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        raise HTTPException(status_code=404, detail="League not found")
    try:
        req = request_join(conn, league, user, body.team_name)
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "request": req, "message": "Join request sent. Wait for a host or officer to approve it."}


@router.post("/league/{slug}/invite/accept")
def api_accept_invite(slug: str, request: Request):
    web = _web()
    conn = web.get_db()
    user = _require_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        raise HTTPException(status_code=404, detail="League not found")
    try:
        team = accept_invite(conn, league, user)
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "team": team, "message": "You are in the league. Open the market to sign available players."}


@router.get("/league/{slug}/organize")
def api_organize(slug: str, request: Request):
    web = _web()
    conn = web.get_db()
    user, league, my_team = _manage(request, conn, slug)
    windows = league_windows(conn, league["id"])
    ensure_default_competitions(conn, league["id"])
    payload = {
        "league": league,
        "my_team": my_team,
        "windows": windows,
        "calendar": calendar_view(windows),
        "officers": list_officers(conn, league["id"]),
        "join_requests": list_join_requests(conn, league["id"]),
        "competitions": list_competitions(conn, league["id"]),
        "teams": league_teams(conn, league["id"]),
        "can_manage": True,
        "is_host": is_host(user, league) or web.can_organize(user, league, my_team),
        **_desk_flags(conn, user, league, my_team, open_windows(conn, league["id"])),
    }
    conn.close()
    return payload


@router.post("/league/{slug}/organize")
def api_organize_save(slug: str, body: OrganizeIn, request: Request):
    web = _web()
    conn = web.get_db()
    user = web.current_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        raise HTTPException(status_code=404, detail="League not found")
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    if not web.can_organize(user, league, my_team):
        conn.close()
        raise HTTPException(status_code=403, detail="Only the organizer can edit this league")
    name = (body.name or league["name"]).strip() or league["name"]
    start_on = (body.start_on or league["start_on"] or "").strip()
    weeks = clamp_weeks(body.weeks if body.weeks is not None else league.get("weeks") or 6)
    max_teams = int(body.max_teams if body.max_teams is not None else league["max_teams"] or 16)
    status = body.status or league["status"] or "open"
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
    return {"ok": True, "league": updated, "message": "League settings saved"}


@router.post("/league/{slug}/calendar")
def api_rebuild_calendar(slug: str, request: Request):
    web = _web()
    conn = web.get_db()
    user = web.current_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        raise HTTPException(status_code=404, detail="League not found")
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    if not web.can_organize(user, league, my_team):
        conn.close()
        raise HTTPException(status_code=403, detail="Only the organizer can edit this league")
    apply_season_calendar(conn, league)
    conn.close()
    return {"ok": True, "message": "Calendar rebuilt from name, weeks, and start date"}


@router.post("/league/{slug}/officers")
def api_add_officer(slug: str, body: EmailIn, request: Request):
    web = _web()
    conn = web.get_db()
    user, league, my_team = _manage(request, conn, slug)
    if not (is_host(user, league) or web.can_organize(user, league, my_team)):
        conn.close()
        raise HTTPException(status_code=403, detail="Only the host can grant officers")
    try:
        grant_officer(conn, league, body.email)
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "message": "Officer added"}


@router.post("/league/{slug}/officers/{user_id}/revoke")
def api_revoke_officer(slug: str, user_id: int, request: Request):
    web = _web()
    conn = web.get_db()
    user, league, my_team = _manage(request, conn, slug)
    if not (is_host(user, league) or web.can_organize(user, league, my_team)):
        conn.close()
        raise HTTPException(status_code=403, detail="Only the host can remove officers")
    revoke_officer(conn, league["id"], user_id)
    conn.close()
    return {"ok": True, "message": "Officer removed"}


@router.post("/league/{slug}/invite")
def api_invite(slug: str, body: EmailIn, request: Request):
    conn = _web().get_db()
    _user, league, _team = _manage(request, conn, slug)
    try:
        invite = invite_manager(conn, league, body.email, body.team_name)
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "invite": invite, "message": "Invitation sent"}


@router.post("/league/{slug}/requests/{request_id}/decide")
def api_decide_join(slug: str, request_id: int, body: DecideIn, request: Request):
    conn = _web().get_db()
    user, league, _team = _manage(request, conn, slug)
    try:
        result = decide_join(conn, league, request_id, body.accept, user)
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "result": result, "message": "Join approved" if body.accept else "Join rejected"}


@router.post("/league/{slug}/competitions")
def api_add_competition(slug: str, body: CompetitionIn, request: Request):
    conn = _web().get_db()
    _user, league, _team = _manage(request, conn, slug)
    try:
        created = create_competition(conn, league["id"], body.kind, body.name)
        if created["kind"] == "division":
            enroll_missing_teams(conn, league["id"], created["id"])
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "competition": created, "message": "Competition added"}


@router.post("/league/{slug}/competitions/{comp_id}/enroll")
def api_enroll(slug: str, comp_id: int, body: EnrollIn, request: Request):
    conn = _web().get_db()
    _user, league, _team = _manage(request, conn, slug)
    competition = competition_by_id(conn, comp_id)
    if not competition or competition["league_id"] != league["id"]:
        conn.close()
        raise HTTPException(status_code=404, detail="Competition not found")
    enroll_team(conn, comp_id, body.team_id)
    conn.close()
    return {"ok": True, "message": "Club added to this competition"}


@router.post("/league/{slug}/competitions/{comp_id}/unenroll")
def api_unenroll(slug: str, comp_id: int, body: EnrollIn, request: Request):
    conn = _web().get_db()
    _user, league, _team = _manage(request, conn, slug)
    competition = competition_by_id(conn, comp_id)
    if not competition or competition["league_id"] != league["id"]:
        conn.close()
        raise HTTPException(status_code=404, detail="Competition not found")
    unenroll_team(conn, comp_id, body.team_id)
    conn.close()
    return {"ok": True, "message": "Club removed from this competition"}


@router.post("/league/{slug}/competitions/{comp_id}/fixtures")
def api_build_fixtures(slug: str, comp_id: int, request: Request):
    conn = _web().get_db()
    _user, league, _team = _manage(request, conn, slug)
    competition = competition_by_id(conn, comp_id)
    if not competition or competition["league_id"] != league["id"]:
        conn.close()
        raise HTTPException(status_code=404, detail="Competition not found")
    try:
        count = generate_fixtures(conn, competition, league.get("start_on"))
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "count": count, "message": f"{count} fixtures built"}


@router.post("/league/{slug}/competitions/{comp_id}/match")
def api_add_match(slug: str, comp_id: int, body: MatchIn, request: Request):
    conn = _web().get_db()
    _user, league, _team = _manage(request, conn, slug)
    competition = competition_by_id(conn, comp_id)
    if not competition or competition["league_id"] != league["id"]:
        conn.close()
        raise HTTPException(status_code=404, detail="Competition not found")
    try:
        enroll_team(conn, comp_id, body.home_team_id)
        enroll_team(conn, comp_id, body.away_team_id)
        add_fixture(conn, comp_id, body.home_team_id, body.away_team_id, body.kickoff)
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "message": "Match added"}


@router.post("/league/{slug}/fixtures/{fixture_id}/result")
def api_save_result(slug: str, fixture_id: int, body: ResultIn, request: Request):
    conn = _web().get_db()
    user, league, _team = _manage(request, conn, slug)
    fixture = fixture_by_id(conn, fixture_id)
    if not fixture or fixture["league_id"] != league["id"]:
        conn.close()
        raise HTTPException(status_code=404, detail="Fixture not found")
    try:
        record_result(conn, fixture_id, body.home_goals, body.away_goals, user["id"])
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "message": "Result saved"}


@router.post("/league/{slug}/windows")
def api_save_windows(slug: str, body: WindowsIn, request: Request):
    web = _web()
    conn = web.get_db()
    user = web.current_user(request, conn)
    league = league_by_slug(conn, slug)
    if not league:
        conn.close()
        raise HTTPException(status_code=404, detail="League not found")
    my_team = manager_team(conn, league["id"], user["id"]) if user else None
    if not web.can_organize(user, league, my_team):
        conn.close()
        raise HTTPException(status_code=403, detail="Only the organizer can edit window times")
    updates = [{"id": row.id, "starts_at": row.starts_at.replace("T", " ").strip(), "ends_at": row.ends_at.replace("T", " ").strip()} for row in body.windows]
    update_window_times(conn, league["id"], updates)
    conn.close()
    return {"ok": True, "message": "Window times saved"}


@router.get("/market")
def api_market(
    request: Request,
    q: str = "",
    position: str = "",
    min_ovr: BlankInt = None,
    status: str = "",
    card_type: str = "",
    mode: str = "",
    x_league_slug: Optional[str] = Header(default=None),
):
    web = _web()
    conn = web.get_db()
    league = _selected_league(request, conn, x_league_slug)
    user = web.current_user(request, conn)
    my_team = manager_team(conn, league["id"], user["id"]) if league and user else None
    current_mode = mode if mode in MODES else web.current_mode(request)
    rows = [web.player_view(r) for r in web.query_players(conn, "" if (q or "").strip() else current_mode, q, position, min_ovr, limit=500, card_type=card_type)]
    attach_market(conn, league, rows)
    if status:
        rows = [row for row in rows if (row.get("market_status") or {}).get("code") == status]
    opens = open_windows(conn, league["id"]) if league else []
    payload = {
        "league": league,
        "my_team": my_team,
        "players": [_player_card(row) for row in rows],
        "q": q,
        "position": position,
        "min_ovr": min_ovr,
        "status": status,
        "card_type": card_type,
        "card_types": web.card_types_for_mode(conn, current_mode),
        "positions": POSITIONS,
        **_desk_flags(conn, user, league, my_team, opens),
    }
    conn.close()
    return payload


@router.post("/market/sign")
def api_sign(body: PidIn, request: Request, x_league_slug: Optional[str] = Header(default=None)):
    web = _web()
    conn = web.get_db()
    user = _require_user(request, conn)
    league = _require_league(request, conn, x_league_slug)
    team = manager_team(conn, league["id"], user["id"])
    if not team:
        conn.close()
        raise HTTPException(status_code=400, detail="Register a club first")
    row = conn.execute("SELECT * FROM players WHERE pid = ?", (body.pid,)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Player not found")
    player = web.player_view(row)
    try:
        sign_player(conn, league, team, player, window_of(open_windows(conn, league["id"]), "buy_sea", "auction"))
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "message": f"Signed {player['name']}"}


@router.post("/market/buyout")
def api_buyout(body: PidIn, request: Request, x_league_slug: Optional[str] = Header(default=None)):
    web = _web()
    conn = web.get_db()
    user = _require_user(request, conn)
    league = _require_league(request, conn, x_league_slug)
    team = manager_team(conn, league["id"], user["id"])
    if not team:
        conn.close()
        raise HTTPException(status_code=400, detail="Register a club first")
    try:
        buyout_clause(conn, league, team, body.pid, window_of(open_windows(conn, league["id"]), "release_clause"))
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "message": "Buyout complete"}


@router.get("/squad")
def api_squad(request: Request, x_league_slug: Optional[str] = Header(default=None)):
    web = _web()
    conn = web.get_db()
    user = _require_user(request, conn)
    league = _require_league(request, conn, x_league_slug)
    team = manager_team(conn, league["id"], user["id"])
    if not team:
        conn.close()
        raise HTTPException(status_code=400, detail="Register a club first")
    players = [web.player_view(row) for row in squad_rows(conn, league["id"], team["id"])]
    others = [row for row in league_teams(conn, league["id"]) if row["id"] != team["id"]]
    opens = open_windows(conn, league["id"])
    payload = {
        "league": league,
        "my_team": team,
        "players": [_player_card(row) for row in players],
        "other_teams": others,
        **_desk_flags(conn, user, league, team, opens),
    }
    conn.close()
    return payload


@router.post("/squad/release")
def api_release(body: PidIn, request: Request, x_league_slug: Optional[str] = Header(default=None)):
    web = _web()
    conn = web.get_db()
    user = _require_user(request, conn)
    league = _require_league(request, conn, x_league_slug)
    team = manager_team(conn, league["id"], user["id"])
    if not team:
        conn.close()
        raise HTTPException(status_code=400, detail="Register a club first")
    try:
        release_to_sea(conn, league, team, body.pid, window_of(open_windows(conn, league["id"]), "release_sea"))
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "message": "Released to the sea"}


@router.post("/squad/clause")
def api_clause(body: ClauseIn, request: Request, x_league_slug: Optional[str] = Header(default=None)):
    web = _web()
    conn = web.get_db()
    user = _require_user(request, conn)
    league = _require_league(request, conn, x_league_slug)
    team = manager_team(conn, league["id"], user["id"])
    if not team:
        conn.close()
        raise HTTPException(status_code=400, detail="Register a club first")
    try:
        set_release_clause(conn, league, team, body.pid, body.clause, window_of(open_windows(conn, league["id"]), "release_clause"))
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "message": "Release clause set"}


@router.post("/squad/offer")
def api_offer(body: OfferIn, request: Request, x_league_slug: Optional[str] = Header(default=None)):
    web = _web()
    conn = web.get_db()
    user = _require_user(request, conn)
    league = _require_league(request, conn, x_league_slug)
    team = manager_team(conn, league["id"], user["id"])
    if not team:
        conn.close()
        raise HTTPException(status_code=400, detail="Register a club first")
    try:
        offer_transfer(
            conn,
            league,
            team,
            body.to_team_id,
            body.pid,
            body.fee,
            body.kind if body.kind == "loan" else "transfer",
            window_of(open_windows(conn, league["id"]), "transfer"),
        )
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "message": "Offer sent"}


@router.post("/offers/{offer_id}/decide")
def api_decide_offer(offer_id: int, body: DecideIn, request: Request, x_league_slug: Optional[str] = Header(default=None)):
    web = _web()
    conn = web.get_db()
    user = _require_user(request, conn)
    league = _require_league(request, conn, x_league_slug)
    team = manager_team(conn, league["id"], user["id"])
    if not team:
        conn.close()
        raise HTTPException(status_code=400, detail="Register a club first")
    try:
        decide_offer(conn, league, team, offer_id, body.accept)
    except ValueError as exc:
        conn.close()
        return _json_error(str(exc))
    conn.close()
    return {"ok": True, "message": "Offer updated"}


@router.get("/players")
def api_players(
    request: Request,
    q: str = "",
    position: str = "",
    min_ovr: BlankInt = None,
    skill: str = "",
    sort: str = "overall",
    card_type: str = "",
    mode: str = "",
    x_league_slug: Optional[str] = Header(default=None),
):
    web = _web()
    conn = web.get_db()
    current_mode = mode if mode in MODES else web.current_mode(request)
    league = _selected_league(request, conn, x_league_slug)
    rows = [
        web.player_view(r)
        for r in web.query_players(conn, "" if (q or "").strip() else current_mode, q, position, min_ovr, skill, sort, limit=500, card_type=card_type)
    ]
    attach_market(conn, league, rows)
    payload = {
        "players": [_player_card(row) for row in rows],
        "q": q,
        "position": position,
        "min_ovr": min_ovr,
        "skill": skill,
        "sort": sort,
        "card_type": card_type,
        "card_types": web.card_types_for_mode(conn, current_mode),
        "positions": POSITIONS,
        "modes": MODES,
        "mode": current_mode,
        "league": league,
    }
    conn.close()
    return payload


@router.get("/players/{slug}")
def api_player(slug: str, request: Request, x_league_slug: Optional[str] = Header(default=None)):
    web = _web()
    conn = web.get_db()
    row = conn.execute("SELECT * FROM players WHERE slug = ? OR pid = ?", (slug, slug)).fetchone()
    if not row:
        conn.close()
        raise HTTPException(status_code=404, detail="Player not found")
    player = web.player_view(row)
    league = _selected_league(request, conn, x_league_slug)
    user = web.current_user(request, conn)
    my_team = manager_team(conn, league["id"], user["id"]) if league and user else None
    attach_market(conn, league, [player])
    others = [
        _player_card(web.player_view(r))
        for r in conn.execute(
            "SELECT * FROM players WHERE name = ? AND pid != ? ORDER BY mode, overall DESC",
            (player["name"], player["pid"]),
        )
    ]
    opens = open_windows(conn, league["id"]) if league else []
    payload = {
        "player": player,
        "others": others,
        "league": league,
        "my_team": my_team,
        **_desk_flags(conn, user, league, my_team, opens),
    }
    conn.close()
    return payload
