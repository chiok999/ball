"""
elo.py — Self-maintained win probability (no external API)
==============================================================
ClubElo (api.clubelo.com) turned out to be unreachable from Railway
on both HTTP and HTTPS — a connect timeout on 443 and a read timeout
on 80 on the same host points to the host being blocked/unreachable
from this network entirely, not a protocol quirk worth chasing
further. Rather than depend on a third-party host that can silently
go dark again, ratings are now maintained IN-HOUSE from real match
results this bot already observes via ESPN/Sofascore — no key, no
external call, nothing that can time out.

How it works:
  - Every team starts at a neutral 1500 rating the first time it's
    seen (standard Elo convention — nobody is assumed strong or weak
    without evidence).
  - After every match this bot detects as FINISHED, record_result()
    applies a standard Elo update using the actual scoreline.
  - win_probability() reads current ratings and applies the same
    logistic formula ClubElo-based code used before.

Honesty tradeoff, stated plainly: ratings are only as good as the
sample of matches this bot has actually seen. Early in the World Cup
(or right after a fresh deploy with no persisted history), most teams
will still be at or near the 1500 baseline, so predictions will lean
close to 50/50 modified only by home advantage — that's an accurate
reflection of "no evidence yet", not a bug. It self-improves as more
finished matches are recorded. This is preferable to a fabricated
starting number or reviving a dependency on a host that's proven
unreliable.

Ratings persist to config.DATA_DIR (the same Railway Volume state.json
already uses) so a redeploy doesn't wipe accumulated history.
"""

import json
import os

import config

RATINGS_FILE = os.path.join(config.DATA_DIR, "elo_ratings.json")

DEFAULT_RATING = 1500.0
K_FACTOR = 24  # moderate — enough to react to results without wild swings on a small sample

_ratings: dict[str, float] = {}
_loaded = False


def _load() -> None:
    global _ratings, _loaded
    if _loaded:
        return
    _loaded = True
    try:
        if os.path.exists(RATINGS_FILE):
            with open(RATINGS_FILE, "r") as f:
                _ratings = json.load(f)
            print(f"[ELO] Loaded {len(_ratings)} team ratings from disk")
    except Exception as e:
        print(f"[ELO] ⚠️  Could not load ratings file ({e}) — starting fresh")
        _ratings = {}


def _save() -> None:
    try:
        os.makedirs(os.path.dirname(RATINGS_FILE) or ".", exist_ok=True)
        with open(RATINGS_FILE, "w") as f:
            json.dump(_ratings, f)
    except Exception as e:
        print(f"[ELO] ⚠️  Could not save ratings file: {e}")


def _get(team: str) -> float:
    _load()
    return _ratings.get(team, DEFAULT_RATING)


def record_result(home_team: str, away_team: str, home_goals: int, away_goals: int,
                   home_advantage: int = 60) -> None:
    """Applies a standard Elo update from a real finished-match result.
    Safe to call once per finished match — caller is responsible for
    dedup (calling this twice for the same match would double-count
    it, same as any Elo system fed a duplicate result)."""
    _load()
    if home_goals is None or away_goals is None:
        return
    elo_home = _get(home_team)
    elo_away = _get(away_team)

    expected_home = 1 / (1 + 10 ** (-((elo_home + home_advantage - elo_away) / 400)))
    if home_goals > away_goals:
        actual_home = 1.0
    elif home_goals < away_goals:
        actual_home = 0.0
    else:
        actual_home = 0.5

    _ratings[home_team] = elo_home + K_FACTOR * (actual_home - expected_home)
    _ratings[away_team] = elo_away + K_FACTOR * ((1 - actual_home) - (1 - expected_home))
    _save()
    print(f"[ELO] Updated ratings from {home_team} {home_goals}-{away_goals} {away_team} "
          f"({home_team}: {elo_home:.0f}→{_ratings[home_team]:.0f}, "
          f"{away_team}: {elo_away:.0f}→{_ratings[away_team]:.0f})")


def win_probability(home_team: str, away_team: str, home_advantage: int = 60) -> dict | None:
    """
    Returns {"home": pct, "draw": pct, "away": pct} (ints summing ~100).
    Never returns None for missing data anymore — both teams default
    to a neutral 1500 the first time they're seen, so this always
    produces a number now (near 50/50 + home advantage for two unknown
    teams, which is the honest answer when there's no history yet).
    """
    elo_home = _get(home_team)
    elo_away = _get(away_team)

    diff = (elo_home + home_advantage) - elo_away
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
