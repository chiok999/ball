"""
transfermarkt.py — Weekly transfermarkt-datasets recap, posted hourly
=========================================================================
Separate from transfers.py (which posts breaking news the moment it's
found). This is real historical transfer data — player, clubs, fee,
date — downloaded once a week and drip-fed as one highlight per hour
so the page has a steady, accurate "on this deal" style post even on
days with no breaking news and no live match.

Source: the transfers.csv.gz table from the open dcaribou/transfermarkt-
datasets project (github.com/dcaribou/transfermarkt-datasets), hosted
publicly, refreshed weekly by the project's own pipeline. No scraping,
no key, no cost.

IMPORTANT: every number shown here is real data from that table — never
invented, never randomized, never a "reliability tier" guess. If a
field is missing (e.g. undisclosed fee), the post says so rather than
filling in a placeholder number.
"""

import os
import csv
import gzip
import io
import time
import requests

TRANSFERMARKT_CSV_URL = "https://pub-e682421888d945d684bcae8890b0ec20.r2.dev/data/transfers.csv.gz"
CACHE_PATH = "transfermarkt_transfers_cache.csv"
CACHE_META_PATH = "transfermarkt_cache_meta.txt"
REFRESH_INTERVAL_DAYS = 7
RECENT_WINDOW_DAYS = 45  # only surface transfers from roughly the current window

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
}

_rows_cache: list[dict] | None = None


def _cache_is_stale() -> bool:
    if not os.path.exists(CACHE_META_PATH) or not os.path.exists(CACHE_PATH):
        return True
    try:
        with open(CACHE_META_PATH) as f:
            last_fetch = float(f.read().strip())
        return (time.time() - last_fetch) > REFRESH_INTERVAL_DAYS * 86400
    except Exception:
        return True


def refresh_if_needed() -> bool:
    """Downloads the weekly CSV only if the local cache is missing/stale.
    Returns True if a fresh copy is available (cached or freshly downloaded)."""
    global _rows_cache
    if not _cache_is_stale():
        return True
    try:
        print("[TRANSFERMARKT] Cache stale — downloading weekly dataset...")
        r = requests.get(TRANSFERMARKT_CSV_URL, headers=HEADERS, timeout=30)
        if r.status_code != 200:
            print(f"[TRANSFERMARKT] HTTP {r.status_code} — keeping old cache if any")
            return os.path.exists(CACHE_PATH)
        raw_csv = gzip.decompress(r.content).decode("utf-8", errors="replace")
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            f.write(raw_csv)
        with open(CACHE_META_PATH, "w") as f:
            f.write(str(time.time()))
        _rows_cache = None  # force reparse
        print("[TRANSFERMARKT] ✅ Weekly dataset refreshed")
        return True
    except Exception as e:
        print(f"[TRANSFERMARKT] ❌ {e}")
        return os.path.exists(CACHE_PATH)


def _load_rows() -> list[dict]:
    global _rows_cache
    if _rows_cache is not None:
        return _rows_cache
    if not os.path.exists(CACHE_PATH):
        _rows_cache = []
        return _rows_cache
    rows = []
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows.append(row)
    except Exception as e:
        print(f"[TRANSFERMARKT] Parse error: {e}")
    _rows_cache = rows
    return rows


def _recent_and_notable(rows: list[dict]) -> list[dict]:
    from datetime import datetime, timezone, timedelta
    cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_WINDOW_DAYS)
    out = []
    for r in rows:
        date_str = r.get("transfer_date", "")
        try:
            d = datetime.fromisoformat(date_str).replace(tzinfo=timezone.utc)
        except Exception:
            continue
        if d < cutoff:
            continue
        out.append(r)
    # Biggest fees first (transfers with no fee sort last, still included)
    def fee_key(r):
        try:
            return -float(r.get("transfer_fee") or 0)
        except (ValueError, TypeError):
            return 0
    out.sort(key=fee_key)
    return out


def get_next_highlight(already_posted: set) -> dict | None:
    """
    Returns the next not-yet-posted highlight (real data, biggest fee
    first within the recent window), or None if the cache is empty/stale
    or everything recent has already been posted this window.
    """
    if not refresh_if_needed():
        return None
    rows = _load_rows()
    if not rows:
        return None

    for r in _recent_and_notable(rows):
        player = r.get("player_name", "Unknown")
        date_str = r.get("transfer_date", "")
        key = f"tm_highlight:{player}:{date_str}"
        if key in already_posted:
            continue
        fee_raw = r.get("transfer_fee")
        try:
            fee_eur = float(fee_raw) if fee_raw not in (None, "") else None
        except ValueError:
            fee_eur = None
        return {
            "key":            key,
            "player":         player,
            "from_club":      r.get("from_club_name", "Unknown"),
            "to_club":        r.get("to_club_name", "Unknown"),
            "transfer_date":  date_str,
            "fee_eur":        fee_eur,   # None = undisclosed, shown honestly as such
        }
    return None
