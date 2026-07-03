"""
elo.py — Win probability via ClubElo
=======================================
Real Elo ratings from api.clubelo.com (plain CSV, no key, no Selenium)
replace whatever was previously driving win-probability numbers.

Standard Elo win-probability formula:
    P(home win) = 1 / (1 + 10^-((EloHome + HomeAdv - EloAway) / 400))
Draw probability is estimated from the closeness of the two win
probabilities (Elo doesn't natively model draws) using a simple,
widely-used approximation.
"""

import csv
import io
import time
import requests

CLUB_ELO_API = "http://api.clubelo.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
}

_cache: dict[str, tuple[float, float]] = {}  # date -> (timestamp, ratings dict pickled as-is)
_CACHE_TTL = 3600 * 6  # ClubElo updates ~daily; 6h cache is plenty


def _fetch_today_ratings() -> dict[str, float]:
    """Returns {team_name: elo} for all teams rated today. Cached."""
    now = time.time()
    if "ratings" in _cache and (now - _cache["ratings"][0]) < _CACHE_TTL:
        return _cache["ratings"][1]

    try:
        r = requests.get(f"{CLUB_ELO_API}/{time.strftime('%Y-%m-%d')}", headers=HEADERS, timeout=10)
        if r.status_code != 200:
            print(f"[ELO] HTTP {r.status_code}")
            return _cache.get("ratings", (0, {}))[1]
        reader = csv.DictReader(io.StringIO(r.text))
        ratings = {}
        for row in reader:
            try:
                ratings[row["Club"]] = float(row["Elo"])
            except (KeyError, ValueError):
                continue
        _cache["ratings"] = (now, ratings)
        return ratings
    except Exception as e:
        print(f"[ELO] ❌ {e}")
        return _cache.get("ratings", (0, {}))[1]


def _resolve(team_name: str, ratings: dict[str, float]) -> float | None:
    if team_name in ratings:
        return ratings[team_name]
    low = team_name.lower()
    for name, elo in ratings.items():
        if name.lower() == low:
            return elo
    # Loose substring fallback for name variants (e.g. "Man City" vs "Manchester City")
    for name, elo in ratings.items():
        if low in name.lower() or name.lower() in low:
            return elo
    return None


def win_probability(home_team: str, away_team: str, home_advantage: int = 60) -> dict | None:
    """
    Returns {"home": pct, "draw": pct, "away": pct} (ints summing ~100),
    or None if either team's Elo rating can't be resolved — caller should
    skip the post rather than show a fabricated number.
    """
    ratings = _fetch_today_ratings()
    if not ratings:
        return None

    home_elo = _resolve(home_team, ratings)
    away_elo = _resolve(away_team, ratings)
    if home_elo is None or away_elo is None:
        print(f"[ELO] Could not resolve rating for '{home_team}' or '{away_team}'")
        return None

    diff = (home_elo + home_advantage) - away_elo
    p_home_vs_away = 1 / (1 + 10 ** (-diff / 400))

    # Draw approximation: draws are most likely when teams are close in
    # strength. This scales a base draw rate (~26%, roughly the historical
    # average across top leagues) down as the gap between teams widens.
    closeness = 1 - abs(p_home_vs_away - 0.5) * 2  # 1.0 when evenly matched, 0.0 when lopsided
    draw_pct = 0.20 + 0.14 * closeness

    home_pct = p_home_vs_away * (1 - draw_pct)
    away_pct = (1 - p_home_vs_away) * (1 - draw_pct)

    total = home_pct + draw_pct + away_pct
    return {
        "home": round(home_pct / total * 100),
        "draw": round(draw_pct / total * 100),
        "away": round(away_pct / total * 100),
    }
