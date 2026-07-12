"""
bot.py — Match Corna Live main bot
==================================
Events posted:
  1. 📋 Lineup confirmed (~LINEUP_LEAD_MINUTES before kickoff)
  2. 📌 Kick-off
  3. ⚽ Goal (with score, scorer, and assist when available)
  4. 🟥 Red card
  5. ⏸️  Half time (current score + scorers/assists)
  6. ⏱️  Extra time start
  7. 🏁  Full time (includes AET / penalty result)
"""

import json
import os
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

import config
import scraper
import poster
import transfers
import worldcup
import graphics

# ══════════════════════════════════════════════════════════════════
# RAILWAY KEEP-ALIVE SERVER
# ══════════════════════════════════════════════════════════════════

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"Match Corna Live is running OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, fmt, *args):
        pass


def _start_keepalive():
    server = HTTPServer(("0.0.0.0", config.PORT), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[KEEPALIVE] HTTP server running on port {config.PORT}")


# ══════════════════════════════════════════════════════════════════
# STATE
# ══════════════════════════════════════════════════════════════════

STATE_FILE = os.path.join(config.DATA_DIR, "state.json")
os.makedirs(config.DATA_DIR, exist_ok=True)

_events:            dict[str, float] = {}
_last_preview_date: str              = ""
_post_timestamps:   list[float]      = []    # rolling timestamps for rate limiting
_transfer_post_timestamps: list[float] = []  # separate rolling window just for transfer news
_last_post_time:    float            = 0.0   # for MIN_POST_GAP enforcement

# World Cup filler cadence — any real match event resets this clock.
_last_event_post_time: float = 0.0


def _load_state():
    global _events, _last_preview_date
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE) as f:
            raw = json.load(f)
        _events            = raw.get("events", {})
        _last_preview_date = raw.get("last_preview_date", "")
        print(f"[STATE] Loaded {len(_events)} posted events from disk")
    except Exception as e:
        print(f"[STATE] ⚠️  Could not load state: {e}")


def _save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "events":            _events,
                "last_preview_date": _last_preview_date,
            }, f)
    except Exception as e:
        print(f"[STATE] ⚠️  Could not save state: {e}")


def _cleanup_state():
    global _events
    cutoff  = time.time() - 86400
    before  = len(_events)
    _events = {k: v for k, v in _events.items() if v > cutoff}
    removed = before - len(_events)
    if removed:
        print(f"[STATE] Cleaned up {removed} old events")


# ══════════════════════════════════════════════════════════════════
# DUPLICATE DETECTION
# ══════════════════════════════════════════════════════════════════

def _already_posted(key: str) -> bool:
    return key in _events


def _mark_posted(key: str):
    _events[key] = time.time()
    _save_state()


def _rate_limit_ok() -> bool:
    """Return True if it is safe to post now (gap + hourly cap)."""
    global _post_timestamps, _last_post_time
    now = time.time()
    # Enforce minimum gap between posts
    if now - _last_post_time < config.MIN_POST_GAP:
        wait = int(config.MIN_POST_GAP - (now - _last_post_time))
        print(f"[BOT] ⏳ Rate limit: waiting {wait}s (MIN_POST_GAP)")
        time.sleep(wait)
    # Enforce hourly cap
    hour_ago = now - 3600
    _post_timestamps = [t for t in _post_timestamps if t > hour_ago]
    if len(_post_timestamps) >= config.MAX_POSTS_PER_HOUR:
        print(f"[BOT] ⚠️  MAX_POSTS_PER_HOUR ({config.MAX_POSTS_PER_HOUR}) reached — skipping post")
        return False
    return True


def _transfer_rate_limit_ok() -> bool:
    """Separate, tighter cap just for breaking football news. A deadline-day
    burst of headlines across several leagues can pass MAX_POSTS_PER_HOUR
    easily while still looking spammy on its own — this keeps news
    posts specifically to config.TRANSFER_MAX_POSTS_PER_WINDOW per
    config.TRANSFER_WINDOW_MINUTES (default: 1 per 30 minutes),
    independent of everything else the bot posts (goals, kickoffs, etc.
    are unaffected)."""
    global _transfer_post_timestamps
    now = time.time()
    # getattr with defaults: if config.py on the deployed environment is
    # older than bot.py (e.g. only one of the two files got redeployed),
    # this must never crash the poll loop — just fall back to the safe
    # default instead of raising AttributeError.
    max_posts = getattr(config, "TRANSFER_MAX_POSTS_PER_WINDOW", 1)
    window_min = getattr(config, "TRANSFER_WINDOW_MINUTES", 30)
    window_ago = now - window_min * 60
    _transfer_post_timestamps = [t for t in _transfer_post_timestamps if t > window_ago]
    if len(_transfer_post_timestamps) >= max_posts:
        print(
            f"[TRANSFERS] ⚠️  Cap reached ({max_posts} per "
            f"{window_min}min) — holding remaining stories for next window"
        )
        return False
    return True


def _post_if_new(key: str, message: str, image_path: str | None = None) -> bool:
    global _post_timestamps, _last_post_time, _last_event_post_time
    if _already_posted(key):
        return False
    if not message:
        return False
    if not _rate_limit_ok():
        return False
    ok = poster.post_photo(image_path, caption=message) if image_path else poster.post(message)
    if not ok:
        print(f"[BOT] ⚠️  Post failed — retrying in 10s...")
        time.sleep(10)
        ok = poster.post_photo(image_path, caption=message) if image_path else poster.post(message)
    if ok:
        _mark_posted(key)
        _post_timestamps.append(time.time())
        _last_post_time = time.time()
        _last_event_post_time = time.time()
    return ok


def _post_now(message: str, image_path: str | None = None) -> bool:
    """For content with no natural dedup key (filler posts) — still
    respects rate limiting and resets the same content clock."""
    global _post_timestamps, _last_post_time, _last_event_post_time
    if not message:
        return False
    if not _rate_limit_ok():
        return False
    ok = poster.post_photo(image_path, caption=message) if image_path else poster.post(message)
    if ok:
        _post_timestamps.append(time.time())
        _last_post_time = time.time()
        _last_event_post_time = time.time()
    return ok


def _current_goal_score(match: dict, goal: dict) -> tuple:
    sc = goal.get("score", [])
    if sc and len(sc) == 2 and sc[0] is not None:
        return sc[0], sc[1]
    h_sc, a_sc = 0, 0
    for g in match.get("goals", []):
        if g["isHome"]:
            h_sc += 1
        else:
            a_sc += 1
        if g is goal:
            break
    return h_sc, a_sc


def _safe_image(builder, *args, **kwargs) -> str | None:
    """Runs a graphics.py card builder; returns None (falls back to
    text-only post) on any failure rather than blocking the real post."""
    try:
        return builder(*args, **kwargs)
    except Exception as e:
        print(f"[GRAPHICS] ⚠️  Card generation failed, posting text-only: {e}")
        return None


def _minutes_until_kickoff(match: dict) -> float | None:
    """Minutes remaining until kickoff, or None if utcDate is missing/
    unparseable. Negative once the match has actually kicked off."""
    utc_str = match.get("utcDate", "")
    if not utc_str:
        return None
    try:
        ko = datetime.fromisoformat(utc_str.replace("Z", "+00:00"))
        return (ko - datetime.now(timezone.utc)).total_seconds() / 60
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════
# EVENT KEYS
# ══════════════════════════════════════════════════════════════════

def _key_lineup(mid: str)               -> str: return f"lineup:{mid}"
def _key_kickoff(mid: str)              -> str: return f"kickoff:{mid}"
def _key_goal(mid: str, g: dict, idx: int = 0) -> str:
    minute = str(g['minute']).strip()
    if minute in ("?", "", "0"):
        minute = f"idx{idx}"
    return f"goal:{mid}:{g['scorer']['name']}:{minute}"
def _key_redcard(mid: str, b: dict)     -> str:
    return f"redcard:{mid}:{b.get('player', {}).get('name', '?')}:{b.get('minute', '?')}"
def _key_halftime(mid: str)             -> str: return f"halftime:{mid}"
def _key_extratime(mid: str)            -> str: return f"extratime:{mid}"
def _key_fulltime(mid: str)             -> str: return f"ft:{mid}"
def _key_motm(mid: str)                 -> str: return f"motm:{mid}"
def _key_var(mid: str, v: dict)         -> str: return f"var:{mid}:{v.get('minute','?')}:{v.get('player','?')}"


# ══════════════════════════════════════════════════════════════════
# WORLD CUP FILLER CONTENT (5am–11pm, at least every FILLER_GAP_MINUTES)
# ══════════════════════════════════════════════════════════════════

def maybe_post_filler(matches: list):
    """
    Real match events always post immediately and reset the clock
    (via _post_if_new). This only fires when nothing has posted in the
    last FILLER_GAP_MINUTES, inside the FILLER_START_HOUR–FILLER_END_HOUR
    window, posting World Cup top scorers.
    """
    if not config.WORLD_CUP_MODE:
        return

    now = datetime.now(timezone.utc)
    if not (config.FILLER_START_HOUR <= now.hour < config.FILLER_END_HOUR):
        return

    elapsed_min = (time.time() - _last_event_post_time) / 60
    if elapsed_min < config.FILLER_GAP_MINUTES:
        return

    scorers = worldcup.get_top_scorers(config.WORLD_CUP_SLUG)
    if scorers:
        print("[FILLER] 👟 Posting World Cup top scorers")
        lines = [f"{s['rank']}. {s['player']} - {s['goals']}" for s in scorers[:5]]
        img = _safe_image(graphics.render_card, "stats", "🚩", "World Cup Top Scorers", lines)
        if _post_now(poster.fmt_top_scorers(scorers), image_path=img):
            return

    # Top scorers has proven unreliable (ESPN's soccer stats endpoints
    # are thin/undocumented) — fall back to upcoming fixtures, which
    # reuses the plain /scoreboard endpoint scraper.py already depends
    # on and has been confirmed working. This is what actually keeps
    # quiet days from posting nothing at all.
    fixtures = worldcup.get_upcoming_fixtures(config.WORLD_CUP_SLUG)
    if fixtures:
        print("[FILLER] 📅 Posting upcoming World Cup fixtures (top scorers unavailable)")
        if _post_now(poster.fmt_upcoming_fixtures(fixtures)):
            return

    print("[FILLER] ⚠️  Nothing posted this cycle — top scorers and upcoming fixtures both unavailable")


# ══════════════════════════════════════════════════════════════════
# FOOTBALL NEWS — player transfers, manager sackings/transfers, deal
# done, gossip, World Cup news. Immediate, not tied to the filler
# clock. Present/future only — transfers.py enforces freshness, this
# never replays old news.
# ══════════════════════════════════════════════════════════════════

# category -> graphics.py card "kind" (badge color/label). Falls back to
# "transfer" styling for any category not listed here.
_NEWS_CARD_KIND = {
    "player_transfer":  "transfer",
    "manager_sacking":  "manager_sacking",
    "manager_transfer": "manager",
    "deal_done":        "deal_done",
    "gossip":           "gossip",
    "worldcup":         "worldcup",
    "player_quote":     "player_quote",
    "injury":           "injury",
}

# Categories that never use the source's own article photo, even when
# one is available — player-quote/interview photos are frequently
# broadcast screenshots with a rival outlet's on-screen logo baked in
# (this is why the old Post-Match Reaction category was disabled
# outright). A generated headline card sidesteps that instead of
# removing the category entirely.
_NEWS_NO_SOURCE_PHOTO = {"player_quote"}


def maybe_post_transfer_news(tick: int):
    if not config.POST_TRANSFER_NEWS:
        return
    if tick % config.TRANSFER_POLL_EVERY_TICKS != 0:
        return
    try:
        items = transfers.check_new(set(_events.keys()))
    except Exception as e:
        print(f"[NEWS] ⚠️  {e}")
        return
    for item in items:
        category = item.get("category")
        if category == "player_quote" and not config.POST_PLAYER_QUOTES:
            continue
        if category == "injury" and not config.POST_INJURY_NEWS:
            continue
        if not _transfer_rate_limit_ok():
            break  # remaining items stay unseen and get retried next poll
        label = item.get("category_label", "News")
        print(f"[NEWS] 📰 {label} ({item['league']}): {item['headline'][:60]}")
        card_kind = _NEWS_CARD_KIND.get(item.get("category"), "transfer")
        img = None
        # Prefer the real article photo (people want to see the player
        # or manager, not a solid-color text card) — falls back
        # automatically to a vertically-centered headline card if the
        # source had no image or it failed to download/decode.
        if item.get("image") and category not in _NEWS_NO_SOURCE_PHOTO:
            img = _safe_image(
                graphics.render_photo_card, card_kind, item["headline"],
                item["image"], source=item.get("source"),
            )
        if not img:
            img = _safe_image(graphics.render_headline_card, card_kind, item["headline"], source=item.get("source"))
        if _post_if_new(item["key"], poster.fmt_football_news(item), image_path=img):
            _transfer_post_timestamps.append(time.time())
        time.sleep(2)


# ══════════════════════════════════════════════════════════════════
# DAILY FIXTURE PREVIEW
# ══════════════════════════════════════════════════════════════════

def maybe_post_preview(matches: list):
    global _last_preview_date
    if not config.POST_DAILY_PREVIEW:
        return
    now   = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")
    # Fire any time within the preview hour (handles mid-hour restarts)
    if now.hour != config.DAILY_PREVIEW_HOUR or _last_preview_date == today:
        return
    print("[BOT] 📅 Posting daily fixture preview...")
    msg = poster.fmt_daily_preview(matches)
    if poster.post(msg):
        _last_preview_date = today
        _save_state()


# ══════════════════════════════════════════════════════════════════
# PROCESS ONE MATCH
# ══════════════════════════════════════════════════════════════════

def process_match(match: dict):
    mid    = match["id"]
    status = match["status"]
    hname  = match["homeTeam"]["name"]
    aname  = match["awayTeam"]["name"]
    # ── Lineups ───────────────────────────────────────────────────
    # Fetched from ESPN's /summary endpoint, gated to fire only once a
    # match is within config.LINEUP_LEAD_MINUTES of kickoff (real-world
    # availability is ~60 min pre-kickoff) — this is what makes lineups
    # post "~1hr before kickoff for every game" instead of being
    # attempted (and failing) the moment a fixture is first seen hours
    # earlier. Still retried every tick inside the window until either
    # lineups are found or the match kicks off.
    if (config.POST_LINEUPS
            and status == "SCHEDULED"
            and match.get("_league_slug")
            and not _already_posted(_key_lineup(mid))):
        mins_to_ko = _minutes_until_kickoff(match)
        if mins_to_ko is not None and mins_to_ko <= config.LINEUP_LEAD_MINUTES:
            lineups = scraper.get_lineup(match["_league_slug"], match.get("_raw_id", mid))
            if lineups:
                match = {**match, "lineups": lineups}
                print(f"[BOT] 📋 Lineups: {hname} vs {aname}")
                _post_if_new(_key_lineup(mid), poster.fmt_lineup(match))

    # ── VAR / disallowed goals ───────────────────────────────────────
    if config.POST_VAR_DISALLOWED:
        for v in match.get("var_events", []):
            key = _key_var(mid, v)
            if not _already_posted(key):
                print(f"[BOT] 🚨 VAR disallowed: {v.get('player')} — {hname} vs {aname}")
                img = _safe_image(
                    graphics.render_card, "var", "❌",
                    f"No Goal — {hname} vs {aname}",
                    [f"{v.get('player','?')} ({poster._minute(v.get('minute','?'))}') — {v.get('reason','VAR Review')}"],
                )
                _post_if_new(key, poster.fmt_var_disallowed(match, v), image_path=img)

    # ── Kick-off ──────────────────────────────────────────────────
    if config.POST_KICKOFF and status == "IN_PLAY" and not _already_posted(_key_kickoff(mid)):
        kickoff_match = {**match, "score": {
            "halfTime": {"home": None, "away": None},
            "fullTime": {"home": 0, "away": 0},
        }}
        print(f"[BOT] 📌 Kickoff: {hname} vs {aname}")
        img = _safe_image(
            graphics.render_scoreboard_card, "kickoff", hname, aname, 0, 0,
            competition=match.get("_comp_name", ""),
            status_label="KICK-OFF", show_pulse=True,
            home_crest_url=match["homeTeam"].get("crest", ""), away_crest_url=match["awayTeam"].get("crest", ""),
        )
        _post_if_new(_key_kickoff(mid), poster.fmt_kickoff(kickoff_match), image_path=img)

    # ── Goals (scorer + assist, when ESPN/Sofascore provide one) ────
    if config.POST_GOALS and status in ("IN_PLAY", "PAUSED", "EXTRA_TIME", "SHOOTOUT", "FINISHED"):
        for idx, goal in enumerate(match.get("goals", [])):
            key = _key_goal(mid, goal, idx)
            if not _already_posted(key):
                scorer = goal["scorer"]["name"]
                assist = goal.get("assist", {}).get("name")
                print(f"[BOT] ⚽ Goal: {scorer}" + (f" (assist: {assist})" if assist else "") + f" — {hname} vs {aname}")
                h_sc, a_sc = _current_goal_score(match, goal)
                event_line = f"{scorer} {poster._minute(goal['minute'])}'"
                if assist:
                    event_line += f"\n(assist: {assist})"
                # Scorer/assist text is drawn under the SCORING team's
                # own crest, not centered across the card — makes it
                # immediately clear whose goal this is at a glance.
                side_kwargs = {"home_event_line": event_line} if goal["isHome"] else {"away_event_line": event_line}
                img = _safe_image(
                    graphics.render_scoreboard_card, "goal", hname, aname, h_sc, a_sc,
                    competition=match.get("_comp_name", ""),
                    status_label=f"{poster._minute(goal['minute'])}' - LIVE", show_pulse=True,
                    home_crest_url=match["homeTeam"].get("crest", ""), away_crest_url=match["awayTeam"].get("crest", ""),
                    **side_kwargs,
                )
                _post_if_new(key, poster.fmt_goal(match, goal), image_path=img)
                time.sleep(2)

    # ── Red cards ─────────────────────────────────────────────────
    if config.POST_RED_CARDS and status in ("IN_PLAY", "PAUSED", "EXTRA_TIME", "SHOOTOUT", "FINISHED"):
        for booking in match.get("bookings", []):
            if booking.get("card") != "RED_CARD":
                continue
            key = _key_redcard(mid, booking)
            if _already_posted(key):
                continue
            player = booking.get("player", {}).get("name", "Unknown")
            minute = poster._minute(booking.get("minute", "?"))
            print(f"[BOT] 🟥 Red card: {player} {minute}' — {hname} vs {aname}")
            h_sc, a_sc = match["score"]["fullTime"].get("home", 0), match["score"]["fullTime"].get("away", 0)
            event_line = f"{player} {minute}'"
            side_kwargs = {"home_event_line": event_line} if booking.get("isHome") else {"away_event_line": event_line}
            img = _safe_image(
                graphics.render_scoreboard_card, "redcard", hname, aname, h_sc or 0, a_sc or 0,
                competition=match.get("_comp_name", ""),
                status_label=f"{minute}' - RED CARD", show_pulse=True,
                home_crest_url=match["homeTeam"].get("crest", ""), away_crest_url=match["awayTeam"].get("crest", ""),
                **side_kwargs,
            )
            _post_if_new(key, poster.fmt_redcard(match, booking), image_path=img)
            time.sleep(2)

    # ── Half time (current score + scorers/assists) ────────────────
    if config.POST_HALFTIME and status == "PAUSED" and not _already_posted(_key_halftime(mid)):
        print(f"[BOT] ⏸️  Half time: {hname} vs {aname}")
        h_sc, a_sc = match["score"]["fullTime"].get("home", 0), match["score"]["fullTime"].get("away", 0)
        img = _safe_image(
            graphics.render_scoreboard_card, "halftime", hname, aname, h_sc or 0, a_sc or 0,
            competition=match.get("_comp_name", ""),
            status_label="HALF TIME", show_pulse=False,
            home_event_line=poster.scorers_line(match, side="home"),
            away_event_line=poster.scorers_line(match, side="away"),
            home_crest_url=match["homeTeam"].get("crest", ""), away_crest_url=match["awayTeam"].get("crest", ""),
        )
        _post_if_new(_key_halftime(mid), poster.fmt_halftime(match), image_path=img)

    # ── Extra time ────────────────────────────────────────────────
    if status in ("EXTRA_TIME", "SHOOTOUT") or (
            status == "FINISHED" and match.get("_went_to_et")):
        if not _already_posted(_key_extratime(mid)):
            print(f"[BOT] ⏱️  Extra time: {hname} vs {aname}")
            h_sc, a_sc = match["score"]["fullTime"].get("home", 0), match["score"]["fullTime"].get("away", 0)
            img = _safe_image(
                graphics.render_scoreboard_card, "extratime", hname, aname, h_sc or 0, a_sc or 0,
                competition=match.get("_comp_name", ""),
                status_label="EXTRA TIME", show_pulse=False,
                home_event_line=poster.scorers_line(match, side="home"),
                away_event_line=poster.scorers_line(match, side="away"),
                home_crest_url=match["homeTeam"].get("crest", ""), away_crest_url=match["awayTeam"].get("crest", ""),
            )
            _post_if_new(_key_extratime(mid), poster.fmt_extratime(match), image_path=img)

    # ── Full time ─────────────────────────────────────────────────
    if config.POST_FULLTIME and status == "FINISHED" and not _already_posted(_key_fulltime(mid)):
        if match.get("_went_to_penalties"):
            print(f"[BOT] 🏁 Full time (penalties): {hname} vs {aname}")
        elif match.get("_went_to_et"):
            print(f"[BOT] 🏁 Full time (AET): {hname} vs {aname}")
        else:
            print(f"[BOT] 🏁 Full time: {hname} vs {aname}")
        h_sc, a_sc = match["score"]["fullTime"].get("home", 0), match["score"]["fullTime"].get("away", 0)
        status_label = "FULL TIME"
        if match.get("_went_to_penalties"):
            status_label = "FULL TIME - PENALTIES"
        elif match.get("_went_to_et"):
            status_label = "FULL TIME - AET"
        img = _safe_image(
            graphics.render_scoreboard_card, "fulltime", hname, aname, h_sc or 0, a_sc or 0,
            competition=match.get("_comp_name", ""),
            status_label=status_label, show_pulse=False,
            # Each team's scorers sit under their own crest instead of
            # one combined line down the center of the card.
            home_event_line=poster.scorers_line(match, side="home"),
            away_event_line=poster.scorers_line(match, side="away"),
            home_crest_url=match["homeTeam"].get("crest", ""), away_crest_url=match["awayTeam"].get("crest", ""),
        )
        _post_if_new(_key_fulltime(mid), poster.fmt_fulltime(match), image_path=img)

    # ── Man of the Match ─────────────────────────────────────────────
    # Fires once, right after full time posts — only ever has data for
    # Sofascore-sourced matches (see scraper.get_man_of_the_match).
    if (config.POST_MOTM and status == "FINISHED"
            and _already_posted(_key_fulltime(mid))
            and not _already_posted(_key_motm(mid))):
        motm = None
        try:
            motm = scraper.get_man_of_the_match(match)
        except Exception as e:
            print(f"[BOT] ⚠️  MOTM lookup failed: {e}")
        if motm:
            print(f"[BOT] 🌟 Man of the Match: {motm['name']}")
            team = match["homeTeam"] if motm.get("team_side") == "home" else match["awayTeam"]
            opponent = match["awayTeam"] if motm.get("team_side") == "home" else match["homeTeam"]
            img = _safe_image(
                graphics.render_motm_card, motm["name"], team["name"], motm.get("rating"),
                competition=match.get("_comp_name", ""), opponent_name=opponent["name"],
                player_photo_url=motm.get("photo_url", ""), team_crest_url=team.get("crest", ""),
            )
            _post_if_new(_key_motm(mid), poster.fmt_motm(match, motm), image_path=img)
        else:
            # No rating data available (ESPN-sourced match, or the
            # lineups endpoint didn't return anything usable) — mark
            # as posted anyway so we don't retry every tick forever.
            _mark_posted(_key_motm(mid))


# ══════════════════════════════════════════════════════════════════
# STARTUP — seed finished matches to prevent duplicate posts
# ══════════════════════════════════════════════════════════════════

def _seed_finished(matches: list):
    seeded = 0
    for m in matches:
        if m["status"] != "FINISHED":
            continue
        mid = m["id"]
        for key in (
            _key_fulltime(mid),
            _key_kickoff(mid),
            _key_lineup(mid),
            _key_extratime(mid),
            _key_halftime(mid),
            _key_motm(mid),
        ):
            if key not in _events:
                _events[key] = time.time()
                seeded += 1
        for idx, g in enumerate(m.get("goals", [])):
            k = _key_goal(mid, g, idx)
            if k not in _events:
                _events[k] = time.time()
                seeded += 1
        for b in m.get("bookings", []):
            if b.get("card") != "RED_CARD":
                continue
            k = _key_redcard(mid, b)
            if k not in _events:
                _events[k] = time.time()
                seeded += 1
    if seeded:
        _save_state()
        print(f"[STATE] 🌱 Seeded {seeded} keys from already-finished matches")


# ══════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════

def main():
    global _last_event_post_time
    _load_state()
    # Resuming the filler clock from persisted state, not from "now":
    # blindly stamping time.time() here meant every restart re-armed the
    # filler wait from zero, regardless of how long the page had
    # actually been quiet — on a debugging session with frequent
    # redeploys this meant filler basically never got a chance to fire.
    # _events[key] is set to time.time() on every real post (via
    # _mark_posted) and during startup seeding, so the most recent
    # value in there is a true "time since last real thing happened,"
    # surviving restarts. Empty state (first-ever boot) falls back to
    # 0.0, which makes filler eligible on the very first tick.
    _last_event_post_time = max(_events.values()) if _events else 0.0
    _start_keepalive()

    print("[STATE] 🌱 Seeding finished matches on startup...")
    _seed_finished(scraper.get_todays_matches())

    print("=" * 60)
    print("  Match Corna Live Bot — Running")
    print(f"  Poll interval : {config.POLL_INTERVAL}s")
    print(f"  Data source   : {config.PRIMARY_SOURCE} primary, {config.FALLBACK_SOURCE} fallback")
    print(f"  Lineups       : {config.POST_LINEUPS} (via ESPN /summary, ~{config.LINEUP_LEAD_MINUTES}min pre-kickoff)")
    print(f"  Kick-off      : {config.POST_KICKOFF}")
    print(f"  Goals         : {config.POST_GOALS} (assists included when the source provides one)")
    print(f"  Red cards     : {config.POST_RED_CARDS}")
    print(f"  Half time     : {config.POST_HALFTIME}")
    print(f"  VAR/No Goal   : {config.POST_VAR_DISALLOWED} (best-effort — verify against a live match)")
    print(f"  Extra time    : True")
    print(f"  Full time     : {config.POST_FULLTIME}")
    print(f"  Preview       : {config.POST_DAILY_PREVIEW} @ {config.DAILY_PREVIEW_HOUR}:00 UTC")
    print(f"  World Cup mode: {config.WORLD_CUP_MODE} (filler every {config.FILLER_GAP_MINUTES}min, {config.FILLER_START_HOUR}:00-{config.FILLER_END_HOUR}:00 UTC)")
    print(f"  Football news : {config.POST_TRANSFER_NEWS} — player transfers, manager sackings/transfers, "
          f"deal-done, gossip, World Cup news ({', '.join(config.TRANSFER_LEAGUES.values())}, World Cup) "
          f"— max {config.TRANSFER_MAX_POSTS_PER_WINDOW} per {config.TRANSFER_WINDOW_MINUTES}min")
    print(f"  FB Page ID    : {'SET ✅' if config.FB_PAGE_ID else 'NOT SET — dev mode'}")
    print("=" * 60)

    tick = 0

    while True:
        try:
            tick += 1
            now = datetime.now(timezone.utc)
            print(f"\n[BOT] ⏰ Tick #{tick} — {now.strftime('%Y-%m-%d %H:%M:%S UTC')}")

            matches = scraper.get_todays_matches()
            print(f"[BOT] {len(matches)} matches today:")

            for m in matches:
                et_tag  = " [ET]"  if m.get("_went_to_et")       else ""
                pen_tag = " [PEN]" if m.get("_went_to_penalties") else ""
                print(f"       {m.get('_comp_flag','⚽')} "
                      f"{m['homeTeam']['name']} vs {m['awayTeam']['name']} "
                      f"[{m['status']}{et_tag}{pen_tag}]")

            maybe_post_preview(matches)
            maybe_post_transfer_news(tick)

            active = [
                m for m in matches
                if m["status"] in (
                    "SCHEDULED", "IN_PLAY", "PAUSED",
                    "EXTRA_TIME", "SHOOTOUT", "FINISHED"
                )
            ]

            for match in active:
                try:
                    process_match(match)
                except Exception as e:
                    print(f"[BOT] ⚠️  Error on {match.get('id','?')}: {e}")

            maybe_post_filler(matches)

            if tick % (3600 // config.POLL_INTERVAL) == 0:
                _cleanup_state()

        except KeyboardInterrupt:
            print("\n[BOT] Stopped.")
            break
        except Exception as e:
            print(f"[BOT] ❌ Unexpected error: {e}")

        time.sleep(config.POLL_INTERVAL)


if __name__ == "__main__":
    main()
