"""Personal-use scraper for publicly listed pesdb.net player cards.

Respects the site: identifies itself, waits between pages, and writes a local
CSV only. Do not republish the dump.
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from importer.efhub_overall import trained_max_overall
from importer.fields import ABILITIES
from importer.growth import default_max_level, default_max_overall
from importer.import_csv import EXPORT_PATH, import_records, pesdb_player_url, write_player_list_csv

UA = "pesdata-personal/1.0 (local offline copy; +https://pesdb.net/efootball/)"
BASE = "https://pesdb.net"
LIST_PATHS = {
    "dream-team": "/efootball/players/",
    "authentic": "/efootball/authentic/players/",
}
TABLE_COLUMNS = [
    "pos",
    "name",
    "team_name",
    "nationality",
    "featured",
    "overall_rating",
    "overall_at_max_level",
    "max_level",
]
HEADING_KEYS = {
    "primary position": "position",
    "player name": "name",
    "club": "club",
    "nationality": "nationality",
    "max level": "max_level",
    "featured pack": "pack_name",
    "overall rating": "overall",
    "max overall": "max_overall",
    "height (cm)": "height",
    "weak foot accuracy": "weak_foot_accuracy",
}
HEADING_KEYS.update({label.lower(): key for key, label, _group in ABILITIES})
STAT_COLUMNS = [
    "height",
    "weak_foot_accuracy",
    *[key for key, _label, _group in ABILITIES],
]
STANDARD_COLUMNS = TABLE_COLUMNS + STAT_COLUMNS
STANDARD_EXPORT = ROOT / "data" / "exports" / "players-standard.csv"
EPIC_EXPORT = ROOT / "data" / "exports" / "players-epic.csv"
SHOWTIME_EXPORT = ROOT / "data" / "exports" / "players-showtime.csv"
WEAK_FOOT_LABELS = {"low": 0, "medium": 1, "high": 2, "very high": 3}
STAT_TO_FORMULA = {
    "offensive_awareness": "offensiveAwareness",
    "ball_control": "ballControl",
    "dribbling": "dribbling",
    "tight_possession": "tightPossession",
    "low_pass": "lowPass",
    "lofted_pass": "loftedPass",
    "finishing": "finishing",
    "heading": "heading",
    "set_piece_taking": "setPieceTaking",
    "curl": "curl",
    "defensive_awareness": "defensiveAwareness",
    "tackling": "ballWinning",
    "aggression": "aggression",
    "defensive_engagement": "defensiveEngagement",
    "gk_awareness": "gkAwareness",
    "gk_catching": "gkCatching",
    "gk_parrying": "gkClearing",
    "gk_reflexes": "gkReflexes",
    "gk_reach": "gkReach",
    "speed": "speed",
    "acceleration": "acceleration",
    "kicking_power": "kickingPower",
    "jumping": "jump",
    "physical_contact": "physicalContact",
    "balance": "balance",
    "stamina": "stamina",
}
PACK_DATE_RE = re.compile(
    r"(\d{1,2})\s+(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+'?(\d{2,4})$",
    re.I,
)
MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
PLAYER_HREF_RE = re.compile(
    r"/efootball/(?:authentic/)?players/([A-Za-z0-9\-]+)-(\d+)"
)
TABLE_RE = re.compile(r'<table class="player-results-table".*?</table>', re.S | re.I)
ROW_RE = re.compile(r"<tr\b[^>]*>(.*?)</tr>", re.S | re.I)
HEADING_RE = re.compile(r'data-copy-heading="([^"]*)"')
VALUE_RE = re.compile(r'data-copy-value="([^"]*)"')
PAGE_RE = re.compile(r"Page\s+(\d+)\s+of\s+([\d,]+)", re.I)
RESULTS_RE = re.compile(r"([\d,]+)\s+results", re.I)


def preference_cookie(columns: list[str] | None = None) -> str:
    payload = {
        "view": "table",
        "columns": columns or TABLE_COLUMNS,
        "sort": "overall_rating",
        "order": "desc",
    }
    return "pesdb_efootball_search=" + urllib.parse.quote(json.dumps(payload, separators=(",", ":")))


def calculated_max_overall(record: dict) -> int | None:
    """Trained max from the same progression math eFHUB uses for its Max button."""
    stats = {}
    for source, target in STAT_TO_FORMULA.items():
        value = parse_int(record.get(source))
        if value is None:
            return None
        stats[target] = value
    weak = record.get("weak_foot_accuracy")
    if isinstance(weak, str) and not weak.strip().isdigit():
        weak = WEAK_FOOT_LABELS.get(weak.strip().lower())
    weak_n = parse_int(weak)
    height = parse_int(record.get("height"))
    level_cap = record.get("max_level")
    if weak_n is None or height is None or not level_cap:
        return None
    return trained_max_overall(
        {
            "position": record.get("position") or "",
            "height": height,
            "weakFootAccuracy": weak_n,
            "levelCap": level_cap,
            "overallRating": record.get("overall"),
            "stats": stats,
        }
    )


def pack_date(pack_name: str) -> str:
    match = PACK_DATE_RE.search((pack_name or "").strip())
    if not match:
        return ""
    day, month, year = match.groups()
    year_n = int(year)
    if year_n < 100:
        year_n += 2000
    return f"{year_n:04d}-{MONTHS[month.lower()]:02d}-{int(day):02d}"


def infer_card_type(pack_name: str, max_level: int | None) -> str:
    text = (pack_name or "").lower()
    if "show time" in text:
        return "Show Time"
    if "big time" in text:
        return "Big Time"
    if "highlight" in text:
        return "Highlight"
    if "legendary" in text:
        return "Legendary"
    if "epic" in text:
        return "Epic"
    if "trending" in text or text.startswith("potw") or text.startswith("pots") or text.startswith("potm"):
        return "Trending"
    if pack_name:
        return "Featured"
    if max_level and max_level >= 35:
        return "Epic"
    return "Standard"


def parse_int(value: str | None) -> int | None:
    if value is None or str(value).strip() == "":
        return None
    try:
        return int(float(str(value).strip()))
    except ValueError:
        return None


def parse_list_page(html_text: str, mode: str) -> tuple[list[dict], dict]:
    meta = {"page": 1, "pages": 1, "results": 0}
    page_m = PAGE_RE.search(html_text)
    if page_m:
        meta["page"] = int(page_m.group(1))
        meta["pages"] = int(page_m.group(2).replace(",", ""))
    results_m = RESULTS_RE.search(html_text)
    if results_m:
        meta["results"] = int(results_m.group(1).replace(",", ""))

    table_m = TABLE_RE.search(html_text)
    if not table_m:
        return [], meta
    table = table_m.group(0)
    headings = [html.unescape(item).strip() for item in HEADING_RE.findall(table)]
    keys = [HEADING_KEYS.get(heading.lower()) for heading in headings]
    tbody_m = re.search(r"<tbody>(.*)</tbody>", table, re.S | re.I)
    if not tbody_m:
        return [], meta

    rows: list[dict] = []
    for row_html in ROW_RE.findall(tbody_m.group(1)):
        values = [html.unescape(item).strip() for item in VALUE_RE.findall(row_html)]
        if not values:
            continue
        record = {"mode": mode}
        for key, value in zip(keys, values):
            if key:
                record[key] = value
        href = PLAYER_HREF_RE.search(row_html)
        if href:
            record["slug"] = f"{href.group(1)}-{href.group(2)}"
            record["pid"] = href.group(2)
        name = record.get("name") or ""
        if not name or not record.get("pid"):
            continue
        record["source_url"] = pesdb_player_url(record["pid"], mode, record.get("slug") or "")
        record["position"] = (record.get("position") or "CF").upper()
        record["club"] = record.get("club") or ""
        record["nationality"] = record.get("nationality") or ""
        record["pack_name"] = record.get("pack_name") or ""
        record["pack_date"] = pack_date(record["pack_name"])
        record["overall"] = parse_int(record.get("overall"))
        record["max_overall"] = parse_int(record.get("max_overall"))
        record["max_level"] = parse_int(record.get("max_level"))
        record["card_type"] = infer_card_type(record["pack_name"], record["max_level"])
        if record["overall"] is None:
            continue
        if record["max_overall"] is None:
            record["max_overall"] = default_max_overall(mode, record["card_type"], record["overall"])
        if record["max_level"] is None:
            record["max_level"] = default_max_level(mode, record["card_type"])
        record["level"] = 1
        rows.append(record)
    return rows, meta


def list_url(
    mode: str,
    page: int,
    featured: bool,
    min_ovr: int | None,
    standard: bool = False,
    player_type: str = "",
) -> str:
    path = LIST_PATHS[mode]
    query: dict[str, str] = {
        "sort": "overall_rating",
        "order": "desc",
        "page": str(page),
    }
    card = player_type or ("standard" if standard else "")
    if card:
        query["type"] = card
    if featured:
        query["availability"] = "featured"
    if min_ovr:
        query["overall_rating[min]"] = str(min_ovr)
    return f"{BASE}{path}?{urllib.parse.urlencode(query)}"


def fetch(url: str, timeout: int = 30, columns: list[str] | None = None) -> str:
    last_error: Exception | None = None
    for attempt in range(5):
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": UA,
                "Accept": "text/html,application/xhtml+xml",
                "Cookie": preference_cookie(columns),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                return response.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            last_error = exc
            if exc.code in {429, 500, 502, 503}:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except urllib.error.URLError as exc:
            last_error = exc
            time.sleep(1.5 * (attempt + 1))
    if last_error:
        raise last_error
    raise RuntimeError(f"Failed to fetch {url}")


class _Gate:
    def __init__(self, min_interval: float) -> None:
        self.min_interval = min_interval
        self._lock = threading.Lock()
        self._next_at = 0.0

    def wait(self) -> None:
        with self._lock:
            now = time.monotonic()
            pause = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + self.min_interval
        if pause:
            time.sleep(pause)


def apply_calculated_max(rows: list[dict]) -> int:
    changed = 0
    for row in rows:
        calculated = calculated_max_overall(row)
        if calculated is None:
            continue
        if calculated != row.get("max_overall"):
            changed += 1
        row["max_overall"] = calculated
    return changed


def scrape_mode(
    mode: str,
    featured: bool = False,
    min_ovr: int | None = None,
    max_pages: int | None = None,
    delay: float = 0.7,
    on_page=None,
    standard: bool = False,
    recalc_max: bool = False,
    checkpoint: Path | None = None,
    player_type: str = "",
) -> tuple[list[dict], int]:
    columns = STANDARD_COLUMNS if recalc_max else None
    collected: dict[str, dict] = {}
    changed = 0
    lock = threading.Lock()

    def take(page: int, html_text: str, page_count: int) -> int:
        nonlocal changed
        rows, meta = parse_list_page(html_text, mode)
        delta = apply_calculated_max(rows) if recalc_max else 0
        snapshot = None
        with lock:
            changed += delta
            for row in rows:
                collected[row["pid"]] = row
            count = len(collected)
            if checkpoint and (page == 1 or page % 25 == 0):
                snapshot = list(collected.values())
        if on_page:
            on_page(mode, page, page_count, count, meta.get("results") or 0)
        if snapshot is not None:
            snapshot.sort(key=lambda row: (-int(row.get("overall") or 0), row.get("name") or ""))
            write_player_list_csv(snapshot, checkpoint)
        return len(rows)

    first = fetch(list_url(mode, 1, featured, min_ovr, standard, player_type), columns=columns)
    _rows, meta = parse_list_page(first, mode)
    pages = int(meta.get("pages") or 1)
    if max_pages:
        pages = min(pages, max_pages)
    if not take(1, first, pages):
        return [], 0
    if pages == 1:
        return list(collected.values()), changed

    limiter = _Gate(max(0.2, delay / 3))

    def load_page(page: int) -> tuple[int, str]:
        limiter.wait()
        url = list_url(mode, page, featured, min_ovr, standard, player_type)
        return page, fetch(url, columns=columns)

    workers = 3 if recalc_max else 1
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(load_page, page) for page in range(2, pages + 1)]
        for future in as_completed(futures):
            page, html_text = future.result()
            take(page, html_text, pages)
    if checkpoint:
        snapshot = sorted(collected.values(), key=lambda row: (-int(row.get("overall") or 0), row.get("name") or ""))
        write_player_list_csv(snapshot, checkpoint)
    return list(collected.values()), changed


def scrape_pesdb(
    modes: list[str] | None = None,
    featured: bool = False,
    min_ovr: int | None = None,
    max_pages: int | None = None,
    delay: float = 0.7,
    dest: Path | None = None,
    do_import: bool = False,
    quiet: bool = False,
    standard: bool = False,
    recalc_max: bool = False,
    player_type: str = "",
) -> dict:
    modes = modes or ["dream-team"]
    records: list[dict] = []
    started = datetime.now()
    if dest is None:
        dest = {
            "epic": EPIC_EXPORT,
            "show_time": SHOWTIME_EXPORT,
        }.get(player_type, STANDARD_EXPORT if standard else EXPORT_PATH)

    def progress(mode: str, page: int, pages: int, count: int, total: int) -> None:
        if quiet:
            return
        print(f"{mode} page {page}/{pages} ({count} collected, {total} listed)", flush=True)

    changed = 0
    checkpoint = None
    if recalc_max and dest:
        checkpoint = dest.with_name(dest.stem + ".recalc.partial.csv")
    for mode in modes:
        if mode not in LIST_PATHS:
            raise ValueError(f"Unknown mode: {mode}")
        rows, mode_changed = scrape_mode(
            mode,
            featured=featured,
            min_ovr=min_ovr,
            max_pages=max_pages,
            delay=delay,
            on_page=progress,
            standard=standard,
            recalc_max=recalc_max,
            checkpoint=checkpoint,
            player_type=player_type,
        )
        records.extend(rows)
        changed += mode_changed
    records.sort(key=lambda row: (-int(row.get("overall") or 0), row.get("name") or ""))
    write_player_list_csv(records, dest)
    imported = 0
    if do_import and records:
        imported = import_records(records, source="pesdb.net")["imported"]
    elapsed = (datetime.now() - started).total_seconds()
    result = {
        "scraped": len(records),
        "csv": str(dest),
        "imported": imported,
        "seconds": round(elapsed, 1),
        "modes": modes,
        "max_overall_updated": changed,
    }
    if not quiet:
        print(f"Wrote {len(records)} players to {dest}", flush=True)
        if changed:
            print(f"Updated {changed} max overall ratings that did not match the trained calculation", flush=True)
        if imported:
            print(f"Imported {imported} players into the local database")
    return result


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape public pesdb.net player lists for personal use.")
    parser.add_argument("--mode", choices=["dream-team", "authentic", "both"], default="dream-team")
    parser.add_argument("--featured", action="store_true", help="Featured / pack cards only")
    parser.add_argument("--min-ovr", type=int, default=None, help="Minimum overall rating")
    parser.add_argument("--pages", type=int, default=None, help="Stop after N list pages per mode")
    parser.add_argument("--delay", type=float, default=0.7, help="Seconds to wait between pages")
    parser.add_argument("--out", type=Path, default=EXPORT_PATH, help="CSV output path")
    parser.add_argument("--import", dest="do_import", action="store_true", help="Load the list into the local app")
    parser.add_argument(
        "--standard",
        action="store_true",
        help="Standard cards only, with max overall corrected from the trained calculation",
    )
    parser.add_argument(
        "--epic",
        action="store_true",
        help="Epic cards only, with max overall corrected from the trained calculation",
    )
    parser.add_argument(
        "--showtime",
        action="store_true",
        help="Show Time cards only, with max overall corrected from the trained calculation",
    )
    return parser


def main() -> None:
    args = build_parser().parse_args()
    modes = ["dream-team", "authentic"] if args.mode == "both" else [args.mode]
    dest = args.out
    player_type = ""
    if args.showtime:
        player_type = "show_time"
    elif args.epic:
        player_type = "epic"
    if player_type == "show_time" and dest == EXPORT_PATH:
        dest = SHOWTIME_EXPORT
    elif player_type == "epic" and dest == EXPORT_PATH:
        dest = EPIC_EXPORT
    elif args.standard and dest == EXPORT_PATH:
        dest = STANDARD_EXPORT
    scrape_pesdb(
        modes=modes,
        featured=args.featured,
        min_ovr=args.min_ovr,
        max_pages=args.pages,
        delay=args.delay,
        dest=dest,
        do_import=args.do_import,
        standard=args.standard,
        recalc_max=args.standard or bool(player_type),
        player_type=player_type,
    )


if __name__ == "__main__":
    main()
