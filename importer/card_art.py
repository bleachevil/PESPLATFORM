"""Card art: local PNG, public pesdb.net official cards, or an SVG stand-in."""

from __future__ import annotations

import html
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES_DIR = ROOT / "data" / "images"
PESDB_CARD = "https://pesdb.net/assets/img/card/f{pid}.png"
_OFFICIAL_PNG: dict[str, bytes] = {}

THEMES = {
    "authentic": ("#7ec8ff", "#12344f", "#0b1c2c", "#d7ecff"),
    "standard": ("#cfd8e6", "#2a3548", "#121820", "#f2f5fa"),
    "trending": ("#f0d48a", "#5a1a24", "#2a0d12", "#ffe9a8"),
    "highlight": ("#d7b4ff", "#3a1a68", "#16082c", "#f0e2ff"),
    "featured": ("#7de0c7", "#0d4a40", "#06241f", "#c9fff2"),
    "epic": ("#f0d48a", "#5a3a0c", "#241605", "#ffe6a3"),
    "legendary": ("#e7c45a", "#4a2f12", "#1a1106", "#ffe08a"),
    "sample": ("#e7c45a", "#3a2a08", "#161004", "#ffe08a"),
}


def initials(name: str) -> str:
    parts = [p for p in (name or "?").split() if p]
    if not parts:
        return "?"
    if len(parts) == 1:
        return parts[0][:2].upper()
    return (parts[0][0] + parts[-1][0]).upper()


def _theme(card_type: str, mode: str) -> tuple[str, str, str, str]:
    if mode == "authentic":
        return THEMES["authentic"]
    key = (card_type or "standard").strip().lower()
    return THEMES.get(key, THEMES["standard"])


def is_efootball_card_id(pid: str) -> bool:
    return bool(re.fullmatch(r"\d{10,20}", str(pid or "")))


def official_card_url(pid: str) -> str | None:
    if not is_efootball_card_id(pid):
        return None
    return PESDB_CARD.format(pid=pid)


def find_image_file(pid: str, name: str = "") -> Path | None:
    del name
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    for ext in (".png", ".jpg", ".jpeg", ".webp"):
        path = IMAGES_DIR / f"{pid}{ext}"
        if path.exists():
            return path
    return None


def official_card_png(pid: str) -> bytes | None:
    """Fetch published eFootball card art from pesdb.net. Not stored in the repo."""
    key = str(pid or "")
    cached = _OFFICIAL_PNG.get(key)
    if cached:
        return cached
    url = official_card_url(key)
    if not url:
        return None
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "pesdata-local/1.0",
            "Accept": "image/png,image/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=8) as response:
            data = response.read()
            content_type = (response.headers.get_content_type() or "").lower()
    except (urllib.error.URLError, TimeoutError, ValueError, OSError):
        return None
    if content_type not in {"image/png", "image/jpeg", "image/webp"} and not data.startswith(b"\x89PNG"):
        return None
    if len(data) < 1000:
        return None
    if len(_OFFICIAL_PNG) > 128:
        _OFFICIAL_PNG.clear()
    _OFFICIAL_PNG[key] = data
    return data


def store_imported_image(pid: str, source: str | Path) -> str:
    src = Path(source)
    if not src.exists() or not src.is_file():
        return ""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    dest = IMAGES_DIR / f"{pid}{src.suffix.lower() or '.png'}"
    dest.write_bytes(src.read_bytes())
    return str(dest)


def _face_tag(player: dict, pid: str) -> str:
    del pid
    mark = html.escape(initials(player.get("name") or "P"))
    accent = _theme(player.get("card_type") or "", player.get("mode") or "")[3]
    return (
        f'<circle cx="140" cy="185" r="70" fill="#141c28"/>'
        f'<text x="140" y="200" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" '
        f'font-size="48" font-weight="800" fill="{accent}">{mark}</text>'
    )


def card_svg(player: dict) -> str:
    name = html.escape(player.get("name") or "Player")
    short = html.escape((player.get("name") or "Player").split()[-1][:12])
    pos = html.escape((player.get("position") or "CF")[:3])
    ovr = int(player.get("overall") or 0)
    nation = html.escape((player.get("nationality") or "")[:14])
    kind = (player.get("card_type") or "Standard").lower()
    mode = player.get("mode") or "dream-team"
    frame, glow, plate, accent = _theme(player.get("card_type") or "", mode)
    pid = re.sub(r"[^a-zA-Z0-9]", "", str(player.get("pid") or "x"))
    stars = 5 if ovr >= 90 else 4 if ovr >= 85 else 3
    star_row = "".join(
        f'<text x="{90 + i * 22}" y="368" font-size="16" fill="{accent}">★</text>'
        for i in range(stars)
    )
    portrait = _face_tag(player, pid)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 280 400" role="img" aria-label="{name}">
  <defs>
    <linearGradient id="g{pid}" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0%" stop-color="{glow}"/>
      <stop offset="55%" stop-color="{plate}"/>
      <stop offset="100%" stop-color="#05070c"/>
    </linearGradient>
  </defs>
  <rect width="280" height="400" rx="18" fill="#0b0d12"/>
  <rect x="6" y="6" width="268" height="388" rx="14" fill="url(#g{pid})" stroke="{frame}" stroke-width="5"/>
  <rect x="18" y="18" width="244" height="364" rx="10" fill="none" stroke="{accent}" stroke-width="1.5" opacity="0.55"/>
  <text x="28" y="58" font-family="Segoe UI, Arial, sans-serif" font-size="36" font-weight="800" fill="#fff">{ovr}</text>
  <text x="30" y="82" font-family="Segoe UI, Arial, sans-serif" font-size="14" font-weight="700" fill="{accent}">{pos}</text>
  <text x="248" y="40" text-anchor="end" font-family="Segoe UI, Arial, sans-serif" font-size="13" font-weight="700" fill="{accent}">27</text>
  <circle cx="140" cy="185" r="78" fill="#0a1018" stroke="{frame}" stroke-width="4"/>
  {portrait}
  <rect x="36" y="268" width="208" height="28" rx="6" fill="#000" opacity="0.35"/>
  <text x="140" y="287" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="12" fill="#dbe6f8">{nation} · {html.escape(kind.title())}</text>
  <text x="140" y="328" text-anchor="middle" font-family="Segoe UI, Arial, sans-serif" font-size="20" font-weight="700" fill="#fff">{short}</text>
  {star_row}
</svg>
"""
