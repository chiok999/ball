"""
worldcup.py — World Cup filler content
==========================================
Fills quiet gaps (no real match event in the last 30 min, 5am-11pm)
with World Cup stats. Two content types, rotated:
  - Top scorers (Golden Boot race)
  - Win probability for the next unstarted World Cup fixture (via elo.py)

⚠️  Top-scorer endpoint needs a live smoke test — ESPN's stat-leaders
endpoint shape couldn't be verified against a live response from this
sandbox (no network access to espn.com). It's defensively parsed: any
mismatch returns None, which just skips that filler slot rather than
posting broken data or crashing.
"""

import requests

ESPN_STATS_API = "https://site.web.api.espn.com/apis/common/v3/sports/soccer"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
}


def _get(url: str, timeout: int = 10) -> dict | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        print(f"[WORLDCUP] HTTP {r.status_code}: {url[:90]}")
    except Exception as e:
        print(f"[WORLDCUP] ❌ {e}")
    return None


def get_top_scorers(league_slug: str = "fifa.world", limit: int = 5) -> list[dict] | None:
    """Returns [{"rank": 1, "player": "...", "team": "...", "goals": N}, ...]
    or None if the endpoint shape doesn't match / request fails."""
    data = _get(
        f"{ESPN_STATS_API}/{league_slug}/statistics/byathlete"
        f"?category=offensive&sort=offensive.total.goals:desc&limit={limit}"
    )
    if not data:
        return None
    try:
        entries = data.get("athletes", []) or data.get("stats", {}).get("categories", [{}])[0].get("leaders", [])
        scorers = []
        for i, entry in enumerate(entries[:limit], start=1):
            athlete = entry.get("athlete", entry)
            name = athlete.get("displayName") or athlete.get("shortName") or "Unknown"
            team = (athlete.get("team", {}) or {}).get("displayName", "")
            stats = entry.get("stats", [])
            goals = next((s.get("value") for s in stats if s.get("name") == "goals"), None)
            if goals is None:
                continue
            scorers.append({"rank": i, "player": name, "team": team, "goals": int(goals)})
        return scorers or None
    except Exception as e:
        print(f"[WORLDCUP] Top scorers parse error: {e}")
        return None
