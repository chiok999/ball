"""
filler.py — quiet-hours content for days/hours with no live match action.

Combines two deliberately separate pools:
  1. player_stats_verified.json — hand-verified historical/legend facts
     (checked against multiple sources before being added; see that file's
     own "_notes" entry). Only entries marked confidence == "high" are ever
     auto-posted — anything flagged "needs_caveat" requires a human to
     decide how to phrase it, so it's excluded here on purpose.
  2. stats_api.py — live current-season numbers from API-Football's free
     tier (top scorers per league right now). These naturally vary post to
     post since the underlying numbers move, so they don't need the same
     long cooldown a static legend fact does.

`used` is a plain dict of {content_id: iso_timestamp}, owned and persisted
by bot.py alongside its other state — this module only reads/writes entries
into whatever dict it's handed, it doesn't manage its own file.
"""
import json
import random
from datetime import datetime, timezone

import config
import stats_api
import graphics

VERIFIED_POOL_PATH = "player_stats_verified.json"

LEGEND_COOLDOWN_HOURS = 14 * 24   # don't repeat the same curated fact for 2 weeks
LIVE_COOLDOWN_HOURS   = 20        # a "today's top scorer" slot can recur roughly daily — the numbers shift


def _load_verified_pool() -> dict:
    try:
        with open(VERIFIED_POOL_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError) as e:
        print(f"[FILLER] Could not load {VERIFIED_POOL_PATH}: {e}")
        return {}
    return {k: v for k, v in data.items() if not k.startswith("_")}


def _eligible(content_id: str, cooldown_hours: float, used: dict) -> bool:
    last = used.get(content_id)
    if not last:
        return True
    try:
        hours_since = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() / 3600
    except ValueError:
        return True  # malformed timestamp — don't let it permanently block this slot
    return hours_since >= cooldown_hours


def _mark_used(content_id: str, used: dict):
    used[content_id] = datetime.now(timezone.utc).isoformat()


def _legend_candidates(used: dict) -> list[tuple[str, dict]]:
    pool = _load_verified_pool()
    return [
        (f"legend:{eid}", entry) for eid, entry in pool.items()
        # Never auto-post an entry flagged needs_caveat — those need a
        # human decision on exact phrasing/scope, not an automated pick.
        if entry.get("confidence") == "high"
        and _eligible(f"legend:{eid}", LEGEND_COOLDOWN_HOURS, used)
    ]


def _live_candidates(used: dict) -> list[tuple[str, dict]]:
    if not config.API_FOOTBALL_KEY:
        return []
    out = []
    for league_key in stats_api.LEAGUES:
        slot_id = f"live:topscorers:{league_key}"
        if not _eligible(slot_id, LIVE_COOLDOWN_HOURS, used):
            continue
        scorers = stats_api.get_top_scorers(league_key, limit=5)
        if scorers:
            out.append((slot_id, {"league": league_key, "scorers": scorers}))
    return out


def build_filler_post(used: dict) -> tuple[str, str | None] | None:
    """Returns (caption, image_path) for one filler post, or None if
    nothing is eligible right now (everything on cooldown, no verified
    pool file, and no/exhausted API-Football key). Marks whatever it
    picks as used in the `used` dict — caller is responsible for
    persisting that dict."""
    legends = _legend_candidates(used)
    live = _live_candidates(used)

    candidates = [("legend", cid, entry) for cid, entry in legends] + \
                 [("live",   cid, entry) for cid, entry in live]
    if not candidates:
        return None

    kind, content_id, entry = random.choice(candidates)
    _mark_used(content_id, used)

    if kind == "legend":
        hook = entry.get("suggested_hook") or entry.get("topic", "")
        caption = f"{hook}\n\n📊 {entry['stat_line']}"
        image_path = graphics.render_headline_card("stat", entry["topic"], source=None)
        return caption, image_path

    league_name = entry["league"].replace("_", " ").title()
    lines = [
        f"{i + 1}. {p['name']} ({p['team']}) — {p['goals']}⚽ {p['assists']}🎯"
        for i, p in enumerate(entry["scorers"])
    ]
    caption = f"📊 {league_name} Top Scorers\n\n" + "\n".join(lines)
    image_path = graphics.render_card("stat", "📊", f"{league_name} Top Scorers", lines)
    return caption, image_path
