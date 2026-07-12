"""
sofascore.py — Primary live-score source (ESPN is the fallback)
==================================================================
Plain requests.get() against Sofascore's public JSON endpoints — no
Selenium, no key, same "free API" philosophy as the ESPN reader.

⚠️  IMPORTANT — NEEDS A LIVE SMOKE TEST ON DEPLOY
This sandbox has no network access to sofascore.com, so the exact
current JSON shape below (endpoints + field names) could not be
verified against a live response. It's built from the well-documented,
widely-used public shape of these endpoints, defensively parsed so a
field-name mismatch degrades to "no matches from Sofascore this poll"
rather than crashing — which automatically triggers the ESPN fallback
in scraper.py. First deploy: watch the logs for
"[SOFASCORE] parsed 0 matches" on a day you know has fixtures, and if
that happens consistently, the field names below need adjusting.

Endpoints used:
  Live events   : /api/v1/sport/football/events/live
  Scheduled day : /api/v1/sport/football/scheduled-events/{YYYY-MM-DD}
  Incidents     : /api/v1/event/{id}/incidents   (goals, cards, VAR)
"""

import time
import requests
from datetime import datetime, timezone

SOFASCORE_API = "https://api.sofascore.com/api/v1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
    "Accept-Language": "en-US,en;q=0.9",
    # Cloudflare-fronted sites like Sofascore often check these even when
    # a convincing User-Agent alone isn't enough — cheap to send, no
    # guarantee against an IP-level block (see _get()'s 403 handling
    # below), but costs nothing to try.
    "Referer": "https://www.sofascore.com/",
    "Origin":  "https://www.sofascore.com",
}

# Set the first time a 403 is seen this run, so we log the "likely
# datacenter-IP block" warning once loudly instead of once per poll
# forever — the repeated per-poll "[SOFASCORE] parsed 0 matches" line
# alone looks identical to "quiet day, no matches" and previously took
# a log-diving session to tell apart from an actual outage.
_warned_blocked = False

# Sofascore tournament-name substrings we care about, mapped to the same
# display names ESPN uses so downstream formatting/hashtags stay identical.
_TOURNAMENT_MAP = {
    "premier league":            "Premier League",
    "laliga":                    "La Liga",
    "la liga":                   "La Liga",
    "bundesliga":                "Bundesliga",
    "serie a":                   "Serie A",
    "ligue 1":                   "Ligue 1",
    "championship":              "Championship",
    "champions league":          "Champions League",
    "europa league":             "Europa League",
    "conference league":         "Europa Conference League",
    "mls":                       "MLS",
    "fifa world cup":            "FIFA World Cup",
    "world cup":                 "FIFA World Cup",
}

_STATUS_MAP = {
    "notstarted": "SCHEDULED",
    "inprogress": "IN_PLAY",
    "halftime":   "PAUSED",
    "finished":   "FINISHED",
    "postponed":  "CANCELLED",
    "cancelled":  "CANCELLED",
    "abandoned":  "CANCELLED",
}


def _get(url: str, timeout: int = 10) -> dict | None:
    global _warned_blocked
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        if r.status_code == 429:
            print("[SOFASCORE] ⚠️  Rate limited")
            return None
        if r.status_code == 403:
            if not _warned_blocked:
                print(
                    "[SOFASCORE] 🚫 403 Forbidden — this almost always means "
                    "Sofascore's Cloudflare protection is blocking this "
                    "server's IP (common on Railway/Heroku/Render datacenter "
                    "ranges), NOT a header/parsing problem. ESPN fallback "
                    "will be used for the rest of this run. Test from a "
                    "non-datacenter network to confirm before spending time "
                    "on header/cookie tweaks."
                )
                _warned_blocked = True
            return None
        print(f"[SOFASCORE] HTTP {r.status_code}: {url[:90]}")
    except Exception as e:
        print(f"[SOFASCORE] ❌ {e}")
    return None


def _map_tournament(raw_name: str) -> str | None:
    low = (raw_name or "").lower()
    for key, display in _TOURNAMENT_MAP.items():
        if key in low:
            return display
    return None


def _get_incidents(event_id) -> list[dict]:
    data = _get(f"{SOFASCORE_API}/event/{event_id}/incidents")
    if not data:
        return []
    return data.get("incidents", []) or []


def _normalize_event(event: dict, comp_flag_fn, is_intl_fn) -> dict | None:
    try:
        home = event.get("homeTeam", {})
        away = event.get("awayTeam", {})
        home_name = home.get("name", "")
        away_name = away.get("name", "")
        if not home_name or not away_name:
            return None

        tournament_name = (
            event.get("tournament", {}).get("name", "")
            or event.get("tournament", {}).get("uniqueTournament", {}).get("name", "")
        )
        display_name = _map_tournament(tournament_name)
        if not display_name:
            # Not a league we track by name — let the caller decide via
            # international-team detection instead of dropping outright.
            display_name = tournament_name or "Football"

        status_type = (event.get("status", {}).get("type", "") or "").lower()
        norm_status = _STATUS_MAP.get(status_type, "SCHEDULED")
        if norm_status == "CANCELLED":
            return None

        home_sc = event.get("homeScore", {}).get("current")
        away_sc = event.get("awayScore", {}).get("current")

        went_to_et = bool(event.get("homeScore", {}).get("period2") is not None
                           and "extra" in (event.get("status", {}).get("description", "") or "").lower())
        went_to_penalties = "penalt" in (event.get("status", {}).get("description", "") or "").lower()
        if went_to_penalties:
            norm_status = "SHOOTOUT" if norm_status == "IN_PLAY" else norm_status
            went_to_et = True

        ko_ts = event.get("startTimestamp")
        utc_date = (
            datetime.fromtimestamp(ko_ts, tz=timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
            if ko_ts else ""
        )

        goals, bookings, var_events = [], [], []
        if norm_status in ("IN_PLAY", "PAUSED", "EXTRA_TIME", "SHOOTOUT", "FINISHED"):
            for inc in _get_incidents(event.get("id")):
                itype = (inc.get("incidentType") or "").lower()
                minute = str(inc.get("time", "?"))
                is_home = inc.get("isHome", True)
                if itype == "goal":
                    # Sofascore's incident shape carries the assist provider
                    # (when there is one) under "assist1" — defensively
                    # parsed; if the field isn't there, no assist is shown.
                    assist_player = inc.get("assist1") or inc.get("assist") or {}
                    assist_name = assist_player.get("name") if isinstance(assist_player, dict) else None
                    goals.append({
                        "minute": minute,
                        "scorer": {"name": inc.get("player", {}).get("name", "Unknown")},
                        "assist": {"name": assist_name} if assist_name else {},
                        "team":   {"shortName": home_name if is_home else away_name},
                        "isHome": is_home,
                        "score":  [inc.get("homeScore"), inc.get("awayScore")],
                    })
                elif itype == "card" and (inc.get("incidentClass") or "").lower() == "red":
                    bookings.append({
                        "minute": minute,
                        "card":   "RED_CARD",
                        "player": {"name": inc.get("player", {}).get("name", "Unknown")},
                        "team":   {"shortName": home_name if is_home else away_name},
                        "isHome": is_home,
                    })
                elif itype in ("vardecision", "var"):
                    incident_class = (inc.get("incidentClass") or "").lower()
                    reason = inc.get("reason") or inc.get("confirmed") or "VAR Review"
                    if "disallow" in incident_class or "goal" in incident_class:
                        var_events.append({
                            "minute": minute,
                            "player": inc.get("player", {}).get("name", "Unknown"),
                            "team":   home_name if is_home else away_name,
                            "reason": str(reason),
                        })
            time.sleep(0.1)

        return {
            "id":                  f"sofascore_{event.get('id', '')}",
            "_raw_id":             str(event.get("id", "")),
            "_league_slug":        "",   # Sofascore has no ESPN-style slug; used for lineup lookups only
            "utcDate":             utc_date,
            "status":              norm_status,
            "_minute":             str(event.get("time", {}).get("currentPeriodStartTimestamp", "") or ""),
            "_source":             "sofascore",
            "_comp_name":          display_name,
            "_comp_flag":          comp_flag_fn(display_name),
            "_is_intl":            is_intl_fn(home_name, away_name),
            "_is_world_cup":       "world cup" in display_name.lower(),
            "var_events":          var_events,
            "_went_to_et":         went_to_et,
            "_went_to_penalties":  went_to_penalties,
            "_penalty_home":       event.get("homeScore", {}).get("penalties"),
            "_penalty_away":       event.get("awayScore", {}).get("penalties"),
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


def get_best_player(event_id) -> dict | None:
    """
    Man of the Match, best-effort: fetches the lineups endpoint (player
    ratings per side) and returns whichever player has the highest
    numeric rating across both teams. Returns None on any failure or
    missing data — the caller must treat that as "skip the MOTM post
    for this match", never as a reason to guess or invent a name.

    ⚠️ Same caveat as the rest of this file: the exact lineups/ratings
    JSON shape below is the well-documented public Sofascore pattern
    but could not be smoke-tested against a live response in this
    sandbox. Defensively parsed — a field-name mismatch degrades to
    None (no MOTM posted) rather than crashing the bot. Watch the logs
    on first deploy for "[SOFASCORE] MOTM: no rated players found" on
    a finished match — if that happens consistently, the field paths
    below need adjusting against a real response.

    Returns: {"name": str, "team_side": "home"|"away", "rating": float,
              "photo_url": str} or None.
    """
    data = _get(f"{SOFASCORE_API}/event/{event_id}/lineups")
    if not data:
        print("[SOFASCORE] MOTM: lineups endpoint returned nothing")
        return None

    best = None  # (rating, name, side, player_id)
    for side in ("home", "away"):
        squad = (data.get(side) or {}).get("players", []) or []
        for entry in squad:
            player = entry.get("player", {}) or {}
            stats = entry.get("statistics", {}) or {}
            rating = stats.get("rating")
            name = player.get("name")
            pid = player.get("id")
            if rating is None or not name:
                continue
            try:
                rating = float(rating)
            except (TypeError, ValueError):
                continue
            if best is None or rating > best[0]:
                best = (rating, name, side, pid)

    if best is None:
        print("[SOFASCORE] MOTM: no rated players found")
        return None

    rating, name, side, pid = best
    photo_url = f"{SOFASCORE_API}/player/{pid}/image" if pid else ""
    return {"name": name, "team_side": side, "rating": round(rating, 1), "photo_url": photo_url}


def get_todays_matches(comp_flag_fn, is_intl_fn) -> list[dict]:
    """Returns [] on any failure — the caller (scraper.py) treats an
    empty list as a signal to fall back to ESPN for this poll."""
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
            n = _normalize_event(e, comp_flag_fn, is_intl_fn)
            if n:
                seen_ids.add(eid)
                matches.append(n)

    print(f"[SOFASCORE] parsed {len(matches)} matches")
    return matches
