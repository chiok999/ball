"""
stats.py — Non-matchday stats content for ScoreLine Live
==========================================================
All data from ESPN free API — no key required.

Posts standings and upcoming fixtures to keep the page active
on quiet days (5 posts/day on a fixed UTC schedule).

Daily post schedule (UTC):
  09:00 — 🏆 League Table (primary league of the day)
  14:00 — 🏆 League Table (secondary league of the day)
  19:00 — 📅 Upcoming Fixtures (next 48 hours)

Leagues rotate by weekday so variety is built in automatically.
"""

import time
import requests
from datetime import datetime, timezone, timedelta

ESPN_STANDINGS  = "https://site.api.espn.com/apis/v2/sports/soccer"
ESPN_SCOREBOARD = "https://site.api.espn.com/apis/site/v2/sports/soccer"

ESPN_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
}

# ── League registry ───────────────────────────────────────────────
# (espn_slug, display_name, flag, hashtag)
LEAGUES = [
    ("eng.1",          "Premier League",  "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "PL"),
    ("esp.1",          "La Liga",          "🇪🇸", "LaLiga"),
    ("ger.1",          "Bundesliga",       "🇩🇪", "Bundesliga"),
    ("ita.1",          "Serie A",          "🇮🇹", "SerieA"),
    ("fra.1",          "Ligue 1",          "🇫🇷", "Ligue1"),
    ("eng.2",          "Championship",     "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Championship"),
    ("uefa.champions", "Champions League", "🏆", "UCL"),
]

_DAY_PAIR = [
    (0, 3),  # Mon: Premier League + Serie A
    (1, 4),  # Tue: La Liga + Ligue 1
    (2, 5),  # Wed: Bundesliga + Championship
    (3, 6),  # Thu: Serie A + UCL
    (4, 0),  # Fri: Ligue 1 + Premier League
    (5, 1),  # Sat: Championship + La Liga
    (6, 2),  # Sun: UCL + Bundesliga
]

STATS_SCHEDULE = {
    "standings_1":  9,
    "standings_2": 14,
    "upcoming":    19,
}

STATS_MINUTE = {
    "standings_1": 0,
    "standings_2": 0,
    "upcoming":    0,
}


def todays_leagues() -> tuple[tuple, tuple]:
    weekday = datetime.now(timezone.utc).weekday()
    i, j    = _DAY_PAIR[weekday]
    return LEAGUES[i], LEAGUES[j]


# ══════════════════════════════════════════════════════════════════
# HTTP
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


# ══════════════════════════════════════════════════════════════════
# STANDINGS
# ══════════════════════════════════════════════════════════════════

def _fmt_gd(gd) -> str:
    gd = int(gd)
    return f"+{gd}" if gd > 0 else str(gd)


def get_standings(league: tuple) -> list[dict] | None:
    espn_slug, name, flag, tag = league
    data = _espn_get(f"{ESPN_STANDINGS}/{espn_slug}/standings")
    if not data:
        print(f"[STATS] ⚠️  No standings data for {name}")
        return None
    rows = _parse_espn_standings(data)
    if rows:
        print(f"[STATS] ✅ Standings ({name}): {len(rows)} teams")
    return rows or None


def _parse_espn_standings(data: dict) -> list[dict]:
    rows = []
    try:
        groups = data.get("children") or [data]
        for group in groups:
            standing_obj = group.get("standings") or group
            for entry in standing_obj.get("entries", []):
                team_name = (entry.get("team", {}).get("displayName")
                             or entry.get("team", {}).get("name", "Unknown"))
                stats_map = {s["name"]: s.get("value", 0)
                             for s in entry.get("stats", [])}
                gd = stats_map.get("pointDifferential",
                     stats_map.get("goalDifferential", 0))
                rows.append({
                    "pos":    int(stats_map.get("rank",
                              stats_map.get("rankId", len(rows) + 1))),
                    "team":   team_name,
                    "played": int(stats_map.get("gamesPlayed", 0)),
                    "won":    int(stats_map.get("wins", 0)),
                    "drawn":  int(stats_map.get("ties", 0)),
                    "lost":   int(stats_map.get("losses", 0)),
                    "gd":     _fmt_gd(gd),
                    "points": int(stats_map.get("points", 0)),
                })
        rows.sort(key=lambda r: r["pos"])
    except Exception as e:
        print(f"[STATS] Standings parse error: {e}")
    return rows


# ══════════════════════════════════════════════════════════════════
# UPCOMING FIXTURES
# ══════════════════════════════════════════════════════════════════

_UPCOMING_SLUGS = {
    "eng.1":            "Premier League",
    "esp.1":            "La Liga",
    "ger.1":            "Bundesliga",
    "ita.1":            "Serie A",
    "fra.1":            "Ligue 1",
    "eng.2":            "Championship",
    "uefa.champions":   "Champions League",
    "uefa.europa":      "Europa League",
    "uefa.europa.conf": "Europa Conference League",
    "usa.1":            "MLS",
}

_UPCOMING_FLAGS = {
    "Premier League": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Championship": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Bundesliga": "🇩🇪", "La Liga": "🇪🇸", "Serie A": "🇮🇹",
    "Ligue 1": "🇫🇷", "Champions League": "🏆",
    "Europa League": "🟠", "Europa Conference League": "🟢", "MLS": "🇺🇸",
}


def get_upcoming_fixtures(days_ahead: int = 2) -> list[dict]:
    now     = datetime.now(timezone.utc)
    results = []
    seen    = set()

    for d in range(1, days_ahead + 1):
        target      = now + timedelta(days=d)
        date_str    = target.strftime("%Y%m%d")
        date_prefix = target.strftime("%Y-%m-%d")

        for slug, league_name in _UPCOMING_SLUGS.items():
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
