"""
stats_api.py — thin client for API-Football's free tier (100 requests/day,
every endpoint included, no card required — https://api-football.com).

Scope note: this module is for CURRENT-SEASON numbers only (top scorers,
team form/goals-for-against). It's deliberately NOT used for historical or
"vs specific opponent" stats (Messi's 2014 World Cup, Ronaldo's Juventus
tally, career head-to-heads) — that data lives in the hand-verified
player_stats_verified.json pool instead. Mixing "freshly fetched, unchecked"
and "manually verified" data into one client would blur the exact
distinction that keeps the verified pool trustworthy — see filler.py, which
combines both pools but keeps them separate and clearly labeled.

Every call is cached to disk with a TTL, and a simple daily-request counter
refuses to hit the network at all once the free-tier quota is nearly used
up, rather than silently burning through it and finding out mid-day.
"""
import os
import json
import time
from datetime import datetime, timezone

import requests

import config

BASE_URL = "https://v3.football.api-sports.io"
CACHE_DIR = "stats_cache"
DAILY_LIMIT = 100
SAFETY_MARGIN = 10  # stop calling with this many requests still "left" on paper

os.makedirs(CACHE_DIR, exist_ok=True)

# API-Football's own numeric league ids — stable across seasons, unlike a
# name-based lookup, and documented on their site. Covers the leagues this
# bot already tracks match data for via ESPN.
LEAGUES = {
    "premier_league":    39,
    "la_liga":          140,
    "serie_a":          135,
    "bundesliga":        78,
    "ligue_1":           61,
    "champions_league":   2,
}


def _usage_file() -> str:
    return os.path.join(CACHE_DIR, "usage.json")


def _today_key() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _load_usage() -> dict:
    try:
        with open(_usage_file()) as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        data = {}
    if data.get("date") != _today_key():
        data = {"date": _today_key(), "count": 0}
    return data


def _save_usage(data: dict):
    try:
        with open(_usage_file(), "w") as f:
            json.dump(data, f)
    except OSError as e:
        print(f"[API-Football] Could not persist usage counter: {e}")


def _requests_remaining_today() -> int:
    return DAILY_LIMIT - _load_usage()["count"]


def _record_request():
    data = _load_usage()
    data["count"] += 1
    _save_usage(data)


def current_season() -> int:
    """European club season year, e.g. 2025 for the 2025-26 season.
    Seasons flip over around July; before that it's still last year's."""
    now = datetime.now(timezone.utc)
    return now.year if now.month >= 7 else now.year - 1


def _cache_path(endpoint: str, params: dict) -> str:
    key = endpoint.strip("/").replace("/", "_")
    parts = "_".join(f"{k}-{v}" for k, v in sorted(params.items()))
    return os.path.join(CACHE_DIR, f"{key}_{parts}.json")


def _api_get(endpoint: str, params: dict, ttl_hours: float = 12) -> dict | None:
    """GET one API-Football endpoint, cached to disk for `ttl_hours`.
    Returns None (never raises) on any failure or missing key — a missing
    filler stat should never take down the bot's actual job of posting
    live scores."""
    if not config.API_FOOTBALL_KEY:
        return None

    path = _cache_path(endpoint, params)
    if os.path.exists(path):
        age_hours = (time.time() - os.path.getmtime(path)) / 3600
        if age_hours < ttl_hours:
            try:
                with open(path) as f:
                    return json.load(f)
            except (json.JSONDecodeError, OSError):
                pass  # fall through and refetch

    if _requests_remaining_today() <= SAFETY_MARGIN:
        used = _load_usage()["count"]
        print(f"[API-Football] Skipping {endpoint} — daily quota nearly used up ({used}/{DAILY_LIMIT})")
        return None

    try:
        resp = requests.get(
            f"{BASE_URL}/{endpoint.lstrip('/')}",
            headers={"x-apisports-key": config.API_FOOTBALL_KEY},
            params=params,
            timeout=10,
        )
        _record_request()
        resp.raise_for_status()
        data = resp.json()
        with open(path, "w") as f:
            json.dump(data, f)
        return data
    except Exception as e:
        print(f"[API-Football] Error fetching {endpoint}: {e}")
        return None


def get_top_scorers(league_key: str, limit: int = 5) -> list[dict]:
    """Top N scorers in one league this season:
    [{name, team, goals, assists}, ...] — empty list on any failure."""
    league_id = LEAGUES.get(league_key)
    if not league_id:
        return []
    data = _api_get("players/topscorers", {"league": league_id, "season": current_season()})
    if not data or not data.get("response"):
        return []
    out = []
    for entry in data["response"][:limit]:
        player = entry.get("player", {})
        stats = (entry.get("statistics") or [{}])[0]
        goals_block = stats.get("goals", {}) or {}
        out.append({
            "name":    player.get("name", "Unknown"),
            "team":    stats.get("team", {}).get("name", ""),
            "goals":   goals_block.get("total") or 0,
            "assists": goals_block.get("assists") or 0,
        })
    return out


def search_player_stats(name: str) -> dict | None:
    """Looks up one player's current-season stats by name, across any
    league API-Football covers — no hardcoded player/team id needed, so
    this works for any player, not just ones we've pre-mapped. Returns
    None if not found (name drift, retired, outside covered leagues) or
    on any failure — never guesses.

    NOTE: API-Football's own schema has a long-standing misspelling —
    'appearences' rather than 'appearances' — handled defensively below
    in case it's ever corrected without notice."""
    data = _api_get("players", {"search": name, "season": current_season()}, ttl_hours=24)
    if not data or not data.get("response"):
        return None
    entry = data["response"][0]
    player = entry.get("player", {})
    stats_list = entry.get("statistics") or [{}]
    stats = stats_list[0]
    goals_block = stats.get("goals", {}) or {}
    games_block = stats.get("games", {}) or {}
    return {
        "name":         player.get("name") or name,
        "team":         stats.get("team", {}).get("name", ""),
        "league":       stats.get("league", {}).get("name", ""),
        "appearances":  games_block.get("appearences") or games_block.get("appearances") or 0,
        "goals":        goals_block.get("total") or 0,
        "assists":      goals_block.get("assists") or 0,
    }


def get_team_form(team_id: int, league_key: str) -> dict | None:
    """Season-to-date form for one team, or None on any failure:
    {form, played, wins, draws, losses, goals_for, goals_against}."""
    league_id = LEAGUES.get(league_key)
    if not league_id:
        return None
    data = _api_get("teams/statistics", {"league": league_id, "season": current_season(), "team": team_id})
    if not data or not data.get("response"):
        return None
    r = data["response"]
    fixtures = r.get("fixtures", {}) or {}
    goals = r.get("goals", {}) or {}
    return {
        "form":           r.get("form", ""),
        "played":         (fixtures.get("played", {}) or {}).get("total", 0),
        "wins":           (fixtures.get("wins", {}) or {}).get("total", 0),
        "draws":          (fixtures.get("draws", {}) or {}).get("total", 0),
        "losses":         (fixtures.get("loses", {}) or {}).get("total", 0),
        "goals_for":      ((goals.get("for", {}) or {}).get("total", {}) or {}).get("total", 0),
        "goals_against":  ((goals.get("against", {}) or {}).get("total", {}) or {}).get("total", 0),
    }
