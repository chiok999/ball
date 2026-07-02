"""
stats.py — Non-matchday stats content for ScoreLine Live
==========================================================
All data from ESPN free API — no key required.

Posts upcoming fixtures to keep the page active on quiet days.
League tables have been retired to avoid awkward empty posts 
during the current tournament/off-season window.

Daily post schedule (UTC):
  19:00 — 📅 Upcoming Fixtures (next 48 hours)
"""

import time
import requests
from datetime import datetime, timezone, timedelta

import config

ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer"

ESPN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
}

# Only upcoming match lists are kept active during the tournament/off-season
STATS_SCHEDULE = {"upcoming": 19}

# ══════════════════════════════════════════════════════════════════
# AUTOMATION ENGINE INTEGRATION METHODS
# ══════════════════════════════════════════════════════════════════

def get_post_schedule_for_hour(hour: int) -> dict | None:
    """
    Maps the current execution hour to the expected bot task payload.
    Fulfills the bot.py polling expectation.
    """
    for type_key, sched_hour in STATS_SCHEDULE.items():
        if hour == sched_hour:
            if type_key == "upcoming":
                return {"type": "fixtures"}
    return None


def get_formatted_standings_post() -> str | None:
    """
    Retired fallback handler. Returns None to gracefully tell bot.py 
    to skip posting league tables during this period.
    """
    return None


def get_formatted_fixtures_post() -> str | None:
    """
    Aggregates upcoming tournament matches across active tracking definitions.
    Formats them cleanly for high engagement on the Facebook timeline feed.
    """
    fixtures = get_upcoming_fixtures(days_ahead=2)
    if not fixtures:
        return None
        
    lines = ["📅 UPCOMING FIXTURES (Next 48 Hours) ⚽", ""]
    current_comp = None
    
    for f in fixtures[:15]: # Limit density to guarantee optimal scannability on mobile
        if f["comp"] != current_comp:
            if current_comp is not None:
                lines.append("")
            lines.append(f"{f['comp_flag']} {f['comp'].upper()}:")
            current_comp = f["comp"]
            
        try:
            # Safely transform target raw UTC strings ("2026-07-02T19:00Z")
            raw_time = f["utcDate"].replace("Z", "")
            dt = datetime.fromisoformat(raw_time)
            time_str = dt.strftime("%H:%M UTC")
        except Exception:
            time_str = "TBD"
            
        lines.append(f"   ⏱️ {time_str} | {f['home']} vs {f['away']}")
        
    lines.extend(["", "", "#Fixtures #UpcomingMatches #ScoreLineLive"])
    return "\n".join(lines)


# ══════════════════════════════════════════════════════════════════
# DATA EXTRACTION & HTTP PIPELINES
# ══════════════════════════════════════════════════════════════════

def _espn_get(url: str) -> dict | None:
    try:
        r = requests.get(url, headers=ESPN_HEADERS, timeout=10)
        if r.status_code == 200:
            return r.json()
        print(f"[STATS/ESPN] HTTP {r.status_code}: {url[:80]}")
    except Exception as e:
        print(f"[STATS/ESPN] ❌ {e}")
    return None


_UPCOMING_SLUGS = {
    "fifa.world":       "FIFA World Cup",
    "eng.1":            "Premier League",
    "esp.1":            "La Liga",
    "ger.1":            "Bundesliga",
    "ita.1":            "Serie A",
    "fra.1":            "Ligue 1",
    "usa.1":            "MLS",
}

_UPCOMING_FLAGS = {
    "FIFA World Cup": "🌍",
    "Premier League": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", 
    "Bundesliga": "🇩🇪", 
    "La Liga": "🇪🇸", 
    "Serie A": "🇮🇹",
    "Ligue 1": "🇫🇷", 
    "MLS": "🇺🇸",
}


def get_upcoming_fixtures(days_ahead: int = 2) -> list[dict]:
    """Queries ESPN scoreboards for active tournament schedules."""
    now     = datetime.now(timezone.utc)
    results = []
    seen    = set()

    for d in range(1, days_ahead + 1):
        target      = now + timedelta(days=d)
        date_str    = target.strftime("%Y%m%d")
        date_prefix = target.strftime("%Y-%m-%d")

        for slug, league_name in _UPCOMING_SLUGS.items():
            # If World Cup mode is true, restrict scanning strictly to international fixtures
            if config.WORLD_CUP_MODE and slug != "fifa.world":
                continue

            data = _espn_get(
                f"{ESPN_SCOREBOARD}/{slug}/scoreboard?dates={date_str}&limit=30"
            )
            if not data:
                time.sleep(0.1)
                continue
            for e in data.get("events", []):
                if not e.get("date", "").startswith(date_prefix):
                    continue
                comps       = e.get("competitions", [{}])
                comp        = comps[0] if comps else {}
                competitors = comp.get("competitors", [])
                if len(competitors) < 2:
                    continue
                home = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                away = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                home_name = home.get("team", {}).get("displayName", "?")
                away_name = away.get("team", {}).get("displayName", "?")
                uid = f"{date_prefix}:{home_name}:{away_name}"
                if uid in seen:
                    continue
                seen.add(uid)
                results.append({
                    "utcDate":   e.get("date", ""),
                    "home":      home_name,
                    "away":      away_name,
                    "comp":      league_name,
                    "comp_flag": _UPCOMING_FLAGS.get(league_name, "⚽"),
                })
            time.sleep(0.15)

    results.sort(key=lambda m: m["utcDate"])
    return results
