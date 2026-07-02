"""
sofascore.py — Primary live-score source (with Cloudflare Bypass & Strict Filtering)
==================================================================================
Uses curl_cffi to bypass Cloudflare while strictly respecting the league and 
international filtering logic passed down by scraper.py.
"""

import time
from datetime import datetime, timezone
from curl_cffi import requests

SOFASCORE_API = "https://api.sofascore.com/api/v1"

HEADERS = {
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Referer": "https://www.sofascore.com/",
}

def _get(url: str, timeout: int = 15) -> dict | None:
    try:
        r = requests.get(url, headers=HEADERS, impersonate="chrome", timeout=timeout)
        if r.status_code == 200:
            return r.json()
        print(f"[SOFASCORE] HTTP {r.status_code}: {url[:90]}")
    except Exception as e:
        print(f"[SOFASCORE] ❌ Connection error: {e}")
    return None


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
            return None

        home = e.get("homeTeam", {})
        away = e.get("awayTeam", {})
        home_name = home.get("name", "Unknown")
        away_name = away.get("name", "Unknown")

        home_sc = e.get("homeScore", {}).get("current")
        away_sc = e.get("awayScore", {}).get("current")

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
            "goals":    [],
            "bookings": [],
            "lineups":  [],
        }
    except Exception as e:
        print(f"[SOFASCORE] Normalize error: {e}")
        return None


def get_todays_matches(comp_flag_fn=None, is_intl_fn=None) -> list[dict]:
    """
    Fetches matches and strictly filters them down to your 6 major leagues,
    World Cup, and senior international matches using the scraper rules.
    """
    now = datetime.now(timezone.utc)
    today_str = now.strftime("%Y-%m-%d")

    matches = []
    
    # Pull current active live events and today's structural feed
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
            
            # 1. Extract tournament name to check major leagues/World Cup
            comp_name = e.get("tournament", {}).get("name", "")
            
            # Determine if this match fits standard 6 leagues or World Cup criteria
            has_valid_flag = False
            if comp_flag_fn:
                flag = comp_flag_fn(comp_name)
                # If the competition helper maps a valid emoji flag, it's an allowed major league/WC
                if flag and flag != "⚽":
                    has_valid_flag = True

            # 2. Extract team names to check international friendly/country criteria
            home_name = e.get("homeTeam", {}).get("name", "")
            away_name = e.get("awayTeam", {}).get("name", "")
            
            is_valid_intl = False
            if is_intl_fn:
                # Runs your strict script logic checking for 'U17', 'U21', 'Women', etc.
                is_valid_intl = is_intl_fn(home_name, away_name)

            # STRICT BLOCK: Skip if it belongs to neither a target league nor a senior international tier
            if not has_valid_flag and not is_valid_intl:
                continue

            n = _normalize_event(e)
            if n:
                if comp_flag_fn:
                    n["_comp_flag"] = comp_flag_fn(n.get("_comp_name", ""))
                seen_ids.add(eid)
                matches.append(n)
                
    return matches
