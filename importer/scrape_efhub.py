"""Personal-use pull of the public eFHUB player list.

The players page loads these endpoints itself:

  GET /api/auth/token
  GET /api/public/players?playerType=1&page=N
  GET /api/public/players/{id}

Standard cards are player type 1 ("normal" on eFHUB). The public player
record includes level cap and country id, but not a pack name or a trained
max overall. Pack stays blank. MaxOverall uses the trained rating already
stored for that player id, or the same Max-button calculation eFHUB uses
when that id was never stored. Level cap 1 keeps the base overall.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
import threading
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from importer.efhub_overall import trained_max_overall
from importer.import_csv import DB_PATH, EXPORT_PATH, import_records, write_player_list_csv

BASE = "https://efhub.com"
STANDARD_TYPE = 1
STANDARD_EXPORT = ROOT / "data" / "exports" / "players-standard.csv"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
)
KNOWN_MAX: dict[str, int] = {}
CARD_TYPES = {
    1: "Standard",
    2: "Featured",
    3: "Trending",
    4: "Legendary",
    5: "Epic",
    6: "Highlight",
    7: "Big Time",
    8: "Show Time",
}


class RateLimiter:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            delay = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + self.min_interval
        if delay:
            time.sleep(delay)

    def pause(self, seconds: float) -> None:
        with self._lock:
            self._next_at = max(self._next_at, time.monotonic() + seconds)


class HubClient:
    def __init__(self, min_interval: float = 0.28) -> None:
        self._cookie = ""
        self._lock = threading.Lock()
        self._limiter = RateLimiter(min_interval)

    def _headers(self) -> dict[str, str]:
        headers = {
            "User-Agent": UA,
            "Accept": "application/json,text/html",
            "Referer": f"{BASE}/players",
        }
        if self._cookie:
            headers["Cookie"] = self._cookie
        return headers

    def refresh(self) -> None:
        request = urllib.request.Request(f"{BASE}/api/auth/token", headers=self._headers())
        with urllib.request.urlopen(request, timeout=30) as response:
            cookie = response.headers.get("Set-Cookie", "")
        token = cookie.split(";", 1)[0].strip()
        if token:
            with self._lock:
                self._cookie = token

    def get(self, url: str, accept: str = "application/json", timeout: int = 20, attempts: int = 6) -> bytes:
        last_error: Exception | None = None
        for attempt in range(attempts):
            self._limiter.wait()
            if not self._cookie:
                self.refresh()
            headers = self._headers()
            headers["Accept"] = accept
            request = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(request, timeout=timeout) as response:
                    return response.read()
            except urllib.error.HTTPError as exc:
                last_error = exc
                if exc.code == 429:
                    pause = 3 if attempts <= 2 else 4 * (attempt + 1)
                    self._limiter.pause(pause)
                    time.sleep(pause)
                    continue
                if exc.code in {401, 403, 500, 502, 503}:
                    with self._lock:
                        self._cookie = ""
                    time.sleep(1.2 * (attempt + 1))
                    continue
                raise
            except urllib.error.URLError as exc:
                last_error = exc
                time.sleep(1.2 * (attempt + 1))
        if last_error:
            raise last_error
        raise RuntimeError(f"Failed to fetch {url}")

    def get_json(self, url: str, timeout: int = 20, attempts: int = 6) -> dict:
        return json.loads(self.get(url, timeout=timeout, attempts=attempts).decode("utf-8", "replace"))

    def get_text(self, url: str) -> str:
        return self.get(url, accept="text/html").decode("utf-8", "replace")


def load_countries(client: HubClient) -> dict[int, str]:
    html = client.get_text(f"{BASE}/players")
    marker = '\\"countries\\":'
    start = html.find(marker)
    if start < 0:
        marker = '"countries":'
        start = html.find(marker)
    if start < 0:
        return {}
    raw = html[start + len(marker) :]
    if marker.startswith("\\"):
        raw = raw.replace('\\"', '"')
    payload, _end = json.JSONDecoder().raw_decode(raw)
    countries: dict[int, str] = {}
    if isinstance(payload, list):
        for item in payload:
            if isinstance(item, dict) and item.get("id") is not None:
                countries[int(item["id"])] = str(item.get("name") or "")
    return countries


def load_known_max_overall() -> dict[str, int]:
    """Trained max rating already stored for the same player id.

    eFHUB's public player record has no max overall. Its Max button matches
    this value (Mbappé base 85, level cap 22, max 95).
    """
    if not DB_PATH.exists():
        return {}
    conn = sqlite3.connect(DB_PATH)
    try:
        rows = conn.execute(
            "SELECT pid, max_overall FROM players WHERE max_overall IS NOT NULL AND max_overall > 0"
        )
        return {str(pid): int(value) for pid, value in rows if pid}
    finally:
        conn.close()


def apply_known_max(row: dict) -> dict:
    if row.get("max_overall"):
        return row
    level_cap = row.get("max_level")
    overall = row.get("overall")
    if level_cap == 1 and overall not in (None, ""):
        row["max_overall"] = overall
        return row
    known = KNOWN_MAX.get(str(row.get("pid") or ""))
    if known:
        row["max_overall"] = known
    return row


def load_cache(path: Path) -> dict[str, dict]:
    cached: dict[str, dict] = {}
    if not path.exists():
        return cached
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        row = json.loads(line)
        pid = str(row.get("pid") or "")
        if pid:
            cached[pid] = apply_known_max(row)
    return cached


def append_cache(path: Path, row: dict, lock: threading.Lock) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with lock:
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def to_record(summary: dict, detail: dict | None, countries: dict[int, str]) -> dict:
    detail = detail or {}
    pid = str(summary.get("id") or detail.get("id") or "")
    overall = summary.get("overallRating")
    if overall is None:
        overall = detail.get("overallRating")
    level_cap = detail.get("levelCap")
    nation = str(detail.get("nationality") or summary.get("nationality") or "").strip()
    if not nation:
        country_id = detail.get("countryId")
        if country_id:
            nation = countries.get(int(country_id), "")
    card_type = CARD_TYPES.get(int(summary.get("playerType") or detail.get("playerType") or 0), "Standard")
    if level_cap == 1:
        max_overall = overall
    else:
        max_overall = KNOWN_MAX.get(pid) or trained_max_overall(detail)
    club = str(summary.get("team") or detail.get("team") or "").strip()
    if club in {"-", "—", "–"}:
        club = ""
    return {
        "pid": pid,
        "name": summary.get("name") or detail.get("name") or "",
        "position": str(summary.get("position") or detail.get("position") or "").upper(),
        "club": club,
        "pack_name": "",
        "nationality": nation,
        "overall": overall,
        "max_level": level_cap,
        "max_overall": max_overall,
        "mode": "dream-team",
        "card_type": card_type,
        "slug": summary.get("slug") or detail.get("slug") or "",
        "source_url": f"{BASE}/players/{pid}" if pid else "",
    }


def write_snapshots(collected: dict[str, dict], partial: Path, standard_only: bool) -> None:
    records = sorted(collected.values(), key=lambda row: (-int(row.get("overall") or 0), row.get("name") or ""))
    write_player_list_csv(records, partial)
    if not standard_only:
        standard_rows = [row for row in records if row.get("card_type") == "Standard"]
        write_player_list_csv(standard_rows, STANDARD_EXPORT.with_name(STANDARD_EXPORT.stem + ".partial.csv"))


def list_url(page: int, standard_only: bool) -> str:
    query = f"page={page}"
    if standard_only:
        query = f"playerType={STANDARD_TYPE}&{query}"
    return f"{BASE}/api/public/players?{query}"


def fetch_detail(client: HubClient, summary: dict, countries: dict[int, str]) -> dict:
    pid = str(summary.get("id") or "")
    detail = client.get_json(f"{BASE}/api/public/players/{pid}") if pid else {}
    if not isinstance(detail, dict):
        detail = {}
    return to_record(summary, detail, countries)


def scrape_efhub(
    standard_only: bool = True,
    max_pages: int | None = None,
    delay: float = 0.35,
    workers: int = 3,
    dest: Path | None = None,
    do_import: bool = False,
    with_details: bool = True,
    quiet: bool = False,
) -> dict:
    started = datetime.now()
    global KNOWN_MAX
    KNOWN_MAX = load_known_max_overall()
    client = HubClient(min_interval=0.28)
    client.refresh()
    countries = load_countries(client) if with_details else {}
    if dest is None:
        dest = STANDARD_EXPORT if standard_only else EXPORT_PATH
    cache_path = ROOT / "data" / "tmp" / ("efhub-standard.jsonl" if standard_only else "efhub-all.jsonl")
    partial = dest.with_name(dest.stem + ".partial.csv")
    cache: dict[str, dict] = {}
    if with_details:
        if not standard_only:
            cache.update(load_cache(ROOT / "data" / "tmp" / "efhub-standard.jsonl"))
        cache.update(load_cache(cache_path))
    cache_lock = threading.Lock()
    collected: dict[str, dict] = {}

    first = client.get_json(list_url(1, standard_only))
    total_pages = int(first.get("totalPages") or 1)
    total_listed = int(first.get("total") or 0)
    if max_pages:
        total_pages = min(total_pages, max_pages)

    def take_page(page: int, payload: dict) -> None:
        summaries = payload.get("players") or []
        pending = []
        for summary in summaries:
            if standard_only and int(summary.get("playerType") or 0) != STANDARD_TYPE:
                continue
            pid = str(summary.get("id") or "")
            if not pid:
                continue
            if with_details and pid in cache:
                collected[pid] = apply_known_max(cache[pid])
            else:
                pending.append(summary)
        if with_details and pending:
            pool = ThreadPoolExecutor(max_workers=max(1, workers))
            future_map = {pool.submit(fetch_detail, client, summary, countries): summary for summary in pending}
            failed: list[dict] = []
            for future in as_completed(future_map):
                summary = future_map[future]
                try:
                    row = future.result()
                except Exception as exc:
                    print(f"detail retry {summary.get('id')}: {exc}", flush=True)
                    failed.append(summary)
                    continue
                pid = row.get("pid") or ""
                if not pid:
                    continue
                collected[pid] = row
                cache[pid] = row
                append_cache(cache_path, row, cache_lock)
            pool.shutdown(wait=True)
            if failed:
                time.sleep(8)
            for summary in failed:
                try:
                    row = fetch_detail(client, summary, countries)
                except Exception as exc:
                    print(f"detail skipped {summary.get('id')}: {exc}", flush=True)
                    row = to_record(summary, None, countries)
                pid = row.get("pid") or ""
                if not pid:
                    continue
                collected[pid] = row
                cache[pid] = row
                append_cache(cache_path, row, cache_lock)
        elif not with_details:
            for summary in pending:
                row = to_record(summary, None, countries)
                if row.get("pid"):
                    collected[row["pid"]] = row
        if not quiet:
            print(
                f"efhub page {page}/{total_pages} "
                f"({len(collected)} collected, {total_listed} listed)",
                flush=True,
            )
        if page == 1 or page % 25 == 0:
            write_snapshots(collected, partial, standard_only)

    take_page(1, first)
    for page in range(2, total_pages + 1):
        time.sleep(max(0.2, delay))
        payload = client.get_json(list_url(page, standard_only))
        players = payload.get("players") or []
        if not players:
            break
        take_page(page, payload)

    records = sorted(collected.values(), key=lambda row: (-int(row.get("overall") or 0), row.get("name") or ""))
    dest = write_player_list_csv(records, dest)
    if not standard_only:
        standard_rows = [row for row in records if row.get("card_type") == "Standard"]
        write_player_list_csv(standard_rows, STANDARD_EXPORT)
    imported = 0
    if do_import and records:
        imported = import_records(records, source="efhub.com")["imported"]
    elapsed = round((datetime.now() - started).total_seconds(), 1)
    if not quiet:
        print(f"Wrote {len(records)} players to {dest}")
        if imported:
            print(f"Imported {imported} players into the local database")
    return {
        "scraped": len(records),
        "listed": total_listed,
        "csv": str(dest),
        "imported": imported,
        "seconds": elapsed,
        "standard_only": standard_only,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Pull the public eFHUB player list for personal use.")
    parser.add_argument("--all", action="store_true", help="All card types, not only standard")
    parser.add_argument("--pages", type=int, default=None, help="Stop after N list pages")
    parser.add_argument("--delay", type=float, default=0.35, help="Seconds to wait between list pages")
    parser.add_argument("--workers", type=int, default=3, help="Parallel player-detail requests")
    parser.add_argument("--list-only", action="store_true", help="Skip per-player detail lookups")
    parser.add_argument("--out", type=Path, default=None, help="CSV output path")
    parser.add_argument("--import", dest="do_import", action="store_true", help="Load the list into the local app")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    scrape_efhub(
        standard_only=not args.all,
        max_pages=args.pages,
        delay=args.delay,
        workers=args.workers,
        dest=args.out,
        do_import=args.do_import,
        with_details=not args.list_only,
    )


if __name__ == "__main__":
    main()
