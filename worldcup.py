"""
worldcup.py — World Cup filler content
==========================================
Fills quiet gaps (no real match event in the last 30 min, 5am-11pm)
with World Cup top-scorers (Golden Boot race) content.

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
        if not entries:
            print("[WORLDCUP] ⚠️  Response had no 'athletes' or 'stats.categories[0].leaders' — endpoint shape may have changed")
            return None
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
        if not scorers:
            print(f"[WORLDCUP] ⚠️  Parsed {len(entries)} entries but none had a readable 'goals' stat — field name may have changed")
            return None
        print(f"[WORLDCUP] Top scorers: parsed {len(scorers)} entries OK")
        return scorers
    except Exception as e:
        print(f"[WORLDCUP] Top scorers parse error: {e}")
        return None


def get_upcoming_fixtures(league_slug: str = "fifa.world", limit: int = 5) -> list[dict] | None:
    """
    Fallback filler content for quiet days, used when get_top_scorers()
    comes back empty (its endpoint has proven unreliable on live
    testing — ESPN's soccer stats support is thin even by their own
    docs). This instead reuses the plain /scoreboard endpoint, which
    is the same one scraper.py already depends on for live scores and
    has been confirmed working — so this filler degrades gracefully
    instead of depending on a second fragile, undocumented shape.

    Returns [{"home": str, "away": str, "date": str}, ...] for the next
    `limit` SCHEDULED matches (today + the next few days), or None if
    the request fails or nothing is scheduled. Never raises — any
    parse error just means "skip this filler slot," same convention
    as get_top_scorers().
    """
    from datetime import datetime, timezone, timedelta

    now = datetime.now(timezone.utc)
    date_range = f"{now.strftime('%Y%m%d')}-{(now + timedelta(days=14)).strftime('%Y%m%d')}"
    data = _get(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{league_slug}/scoreboard?dates={date_range}&limit=100")
    if not data:
        return None
    try:
        fixtures = []
        for e in data.get("events", []):
            state = e.get("status", {}).get("type", {}).get("state", "pre").lower()
            if state != "pre":
                continue  # only unplayed fixtures — this is a "what's coming up" filler, not a results recap
            comp = (e.get("competitions") or [{}])[0]
            competitors = comp.get("competitors", [])
            if len(competitors) < 2:
                continue
            home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
            away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
            home_name = home.get("team", {}).get("displayName", "")
            away_name = away.get("team", {}).get("displayName", "")
            if not home_name or not away_name:
                continue
            fixtures.append({
                "home": home_name,
                "away": away_name,
                "utcDate": e.get("date", ""),
                "comp": "FIFA World Cup",
                "comp_flag": "🌍",
            })
            if len(fixtures) >= limit:
                break
        if not fixtures:
            print("[WORLDCUP] ⚠️  No upcoming fixtures found in scoreboard response")
            return None
        print(f"[WORLDCUP] Upcoming fixtures: parsed {len(fixtures)} entries OK")
        return fixtures
    except Exception as e:
        print(f"[WORLDCUP] Upcoming fixtures parse error: {e}")
        return None
