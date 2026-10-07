"""Fill pesdb rows whose max level is missing with eFHUB's overall and level cap.

pesdb lists max level 1 for most standard cards. eFHUB has the real cap.
Max overall is the trained rating from that cap, using the same calculation
as eFHUB's Max button. Name, club, pack, nation, and the pesdb link stay put.
"""

from __future__ import annotations

import csv
import json
import shutil
import sys
import time
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from importer.efhub_overall import trained_max_overall
from importer.scrape_efhub import BASE, HubClient

CSV_PATH = ROOT / "data" / "exports" / "players-standard.csv"
BACKUP_PATH = ROOT / "data" / "exports" / "players-standard.pesdb.csv"
CACHE_PATH = ROOT / "data" / "tmp" / "efhub-levelcap.jsonl"
WORKERS = 5
BATCH = 20


def pid_from_link(link: str) -> str:
    return (link or "").rstrip("/").rsplit("-", 1)[-1]


def load_cache() -> dict[str, dict]:
    cached: dict[str, dict] = {}
    if not CACHE_PATH.exists():
        return cached
    for line in CACHE_PATH.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        row = json.loads(line)
        pid = str(row.get("pid") or "")
        if pid:
            cached[pid] = row
    return cached


def append_cache(row: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with CACHE_PATH.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(row, ensure_ascii=False) + "\n")


def compact(detail: dict, pid: str) -> dict:
    stats = detail.get("stats") or {}
    return {
        "pid": pid,
        "overall": detail.get("overallRating"),
        "levelCap": detail.get("levelCap"),
        "position": detail.get("position"),
        "height": detail.get("height"),
        "weakFootAccuracy": detail.get("weakFootAccuracy"),
        "stats": stats,
    }


def apply_row(row: dict, saved: dict) -> bool:
    if saved.get("missing"):
        return False
    overall = saved.get("overall")
    level_cap = saved.get("levelCap")
    if overall is None or not level_cap:
        return False
    detail = {
        "position": saved.get("position") or row.get("Position") or "",
        "height": saved.get("height") or 0,
        "weakFootAccuracy": saved.get("weakFootAccuracy") or 0,
        "levelCap": level_cap,
        "overallRating": overall,
        "stats": saved.get("stats") or {},
    }
    calculated = trained_max_overall(detail)
    if calculated is None and int(level_cap) == 1:
        calculated = int(overall)
    changed = (
        str(row.get("Overall") or "") != str(overall)
        or str(row.get("MaxLevel") or "") != str(level_cap)
        or str(row.get("MaxOverall") or "") != str(calculated or "")
    )
    row["Overall"] = overall
    row["MaxLevel"] = level_cap
    if calculated is not None:
        row["MaxOverall"] = calculated
    return changed


def write_csv(rows: list[dict], fieldnames: list[str]) -> None:
    tmp = CSV_PATH.with_suffix(".csv.tmp")
    with tmp.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
    for _attempt in range(3):
        try:
            tmp.replace(CSV_PATH)
            return
        except PermissionError:
            time.sleep(1)
    # The spreadsheet is open, so keep a second copy the pull can update.
    fallback = CSV_PATH.with_name(CSV_PATH.stem + ".levels.csv")
    tmp.replace(fallback)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    if CSV_PATH.exists() and not BACKUP_PATH.exists():
        shutil.copyfile(CSV_PATH, BACKUP_PATH)
    with CSV_PATH.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = list(reader.fieldnames or [])
        rows = list(reader)
    by_pid = {pid_from_link(row.get("Link") or ""): row for row in rows}
    targets = [
        pid
        for pid, row in by_pid.items()
        if pid and str(row.get("MaxLevel") or "") in {"", "1"}
    ]
    cached = load_cache()
    changed = 0
    for pid in targets:
        saved = cached.get(pid)
        if saved and apply_row(by_pid[pid], saved):
            changed += 1
    if changed:
        write_csv(rows, fieldnames)
    pending = [pid for pid in targets if pid not in cached]
    print(
        f"level 1 or blank: {len(targets)}; already saved: {len(targets) - len(pending)}; to fetch: {len(pending)}",
        flush=True,
    )
    if not pending:
        print(f"updated {changed} rows", flush=True)
        return

    client = HubClient(min_interval=0.12)
    client.refresh()
    started = time.time()
    done = 0
    fetched_changes = 0
    retry_later: list[str] = []

    def fetch(pid: str) -> tuple[str, dict | None]:
        url = f"{BASE}/api/public/players/{pid}"
        try:
            detail = client.get_json(url, timeout=12, attempts=2)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return pid, {"pid": pid, "missing": True}
            return pid, None
        except Exception:
            return pid, None
        if not isinstance(detail, dict) or not detail.get("id"):
            return pid, {"pid": pid, "missing": True}
        return pid, compact(detail, pid)

    for start in range(0, len(pending), BATCH):
        batch = pending[start : start + BATCH]
        failed = 0
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [pool.submit(fetch, pid) for pid in batch]
            for future in as_completed(futures):
                pid, saved = future.result()
                if saved is None:
                    failed += 1
                    retry_later.append(pid)
                    continue
                cached[pid] = saved
                append_cache(saved)
                row = by_pid.get(pid)
                if row and apply_row(row, saved):
                    fetched_changes += 1
                    if str(saved.get("levelCap") or "") not in {"", "1"}:
                        print(
                            f"{row.get('Name')} {row.get('Position')} overall {saved.get('overall')} "
                            f"level {saved.get('levelCap')} max {row.get('MaxOverall')}",
                            flush=True,
                        )
                done += 1
        write_csv(rows, fieldnames)
        rate = done / max(time.time() - started, 0.1)
        left = (len(pending) - start - len(batch) + len(retry_later)) / max(rate, 0.1)
        print(
            f"{done}/{len(pending)} updated {fetched_changes} about {left / 60:.0f} min left",
            flush=True,
        )
        if failed:
            time.sleep(5)
    if retry_later:
        print(f"{len(retry_later)} players still need a retry", flush=True)
    print(f"finished {done} fetched, {fetched_changes} rows changed", flush=True)


if __name__ == "__main__":
    main()
