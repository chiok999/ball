"""
sofascore.py — Primary live-score source (with Cloudflare Bypass)
==================================================================
Uses curl_cffi to impersonate a browser's low-level TLS signature, 
preventing the HTTP 403 errors triggered by standard Python requests.
"""

import time
from datetime import datetime, timezone
from curl_cffi import requests

SOFASCORE_API = "https://api.sofascore.com/api/v1"

# Standard headers to complement the browser impersonation
HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.sofascore.com/",
}

def _get(url: str, timeout: int = 15) -> dict | None:
    try:
        # impersonate="chrome" forces curl_cffi to handle the TLS handshake 
        # exactly like a real desktop Google Chrome client.
        r = requests.get(url, headers=HEADERS, impersonate="chrome", timeout=timeout)
        if r.status_code == 200:
            return r.json()
        print(f"[SOFASCORE] HTTP {r.status_code}: {url[:90]}")
    except Exception as e:
        print(f"[SOFASCORE] ❌ Connection or Bypass error: {e}")
    return None


def get_all_leagues_today() -> list[dict]:
    """Helper to dump raw matches across all leagues for debugging."""
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")
    data = _get(f"{SOFASCORE_API}/sport/football/scheduled-events/{today_str}")
    if not data:
        return []
    return data.get("events", [])


def _normalize_event(e: dict) -> dict | None:
    try:
        status_raw = e.get("status", {}).get("type", "none")
        if status_raw == "notstarted":
            status = "SCHEDULED"
        elif status_raw in ("inprogress", "injurytime"):
            status = "IN_PLAY"
        elif status_raw == "halftime":
            status = "PAUSED"
        elif status_raw == "finished":
            status = "FINISHED"
        else:
            return None  # Drop canceled, postponed, or unknown status structures

        home = e.get("homeTeam", {})
        away = e.get("awayTeam", {})
        home_name = home.get("name", "Unknown")
        away_name = away.get("name", "Unknown")

        home_sc = e.get("homeScore", {}).get("current")
        away_sc = e.get("awayScore", {}).get("current")

        goals = []
        bookings = []

        return {
            "id":       str(e.get("id", "")),
            "status":   status,
            "_comp_name": e.get("tournament", {}).get("name", ""),
            "homeTeam": {"id": str(home.get("id", "")), "name": home_name, "shortName": home.get("shortName", home_name)},
            "awayTeam": {"id": str(away.get("id", "")), "name": away_name, "shortName": away.get("shortName", away_name)},
            "score": {
                "halfTime": {"home": None, "away": None},
                "fullTime": {
                    "home": int(home_sc) if home_sc is not None else None,
                    "away": int(away_sc) if away_sc is not None else None,
                },
            },
            "goals":    goals,
            "bookings": bookings,
            "lineups":  [],
        }
    except Exception as e:
        print(f"[SOFASCORE] Normalize error: {e}")
        return None


def get_todays_matches(comp_flag_fn=None, is_intl_fn=None) -> list[dict]:
    """
    Returns [] on any failure — the caller (scraper.py) treats an
    empty list as a signal to fall back to ESPN for this poll.
    """
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    matches = []
    live = _get(f"{SOFASCORE_API}/sport/football/events/live")
    scheduled = _get(f"{SOFASCORE_API}/sport/football/scheduled-events/{today_str}")

    seen_ids = set()
    for payload in (live, scheduled):
        if not payload:
            continue
        for e in payload.get("events", []):
            eid = e.get("id")
            if eid in seen_ids:
                continue
            
            n = _normalize_event(e)
            if n:
                if comp_flag_fn:
                    n["_comp_flag"] = comp_flag_fn(n.get("_comp_name", ""))
                seen_ids.add(eid)
                matches.append(n)
                
    return matches
