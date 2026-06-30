"""
bot.py — ScoreLine Live main bot
==================================
Events posted:
  1. 📋 Lineup confirmed (ESPN does not provide this — field is always empty)
  2. 📌 Kick-off
  3. ⚽ Goal (with score and scorer)
  4. ⏱️  Extra time start
  5. 🏁  Full time (includes AET / penalty result)
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
import stats as stats_module

# ══════════════════════════════════════════════════════════════════
# RAILWAY KEEP-ALIVE SERVER
# ══════════════════════════════════════════════════════════════════

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ScoreLine Live is running OK"
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

STATE_FILE = "state.json"

_events:            dict[str, float] = {}
_last_preview_date: str              = ""
_last_stats_date:   str              = ""   # "YYYY-MM-DD" of last stats run
_stats_posted:      set[str]         = set() # which slots were posted today
_post_timestamps:   list[float]      = []    # rolling timestamps for rate limiting
_last_post_time:    float            = 0.0   # for MIN_POST_GAP enforcement


def _load_state():
    global _events, _last_preview_date, _last_stats_date, _stats_posted
    if not os.path.exists(STATE_FILE):
        return
    try:
        with open(STATE_FILE) as f:
            raw = json.load(f)
        _events            = raw.get("events", {})
        _last_preview_date = raw.get("last_preview_date", "")
        _last_stats_date   = raw.get("last_stats_date", "")
        _stats_posted      = set(raw.get("stats_posted", []))
        print(f"[STATE] Loaded {len(_events)} posted events from disk")
    except Exception as e:
        print(f"[STATE] ⚠️  Could not load state: {e}")


def _save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump({
                "events":            _events,
                "last_preview_date": _last_preview_date,
                "last_stats_date":   _last_stats_date,
                "stats_posted":      list(_stats_posted),
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


def _post_if_new(key: str, message: str) -> bool:
    global _post_timestamps, _last_post_time
    if _already_posted(key):
        return False
    if not message:
        return False
    if not _rate_limit_ok():
        return False
    ok = poster.post(message)
    if not ok:
        print(f"[BOT] ⚠️  Post failed — retrying in 10s...")
        time.sleep(10)
        ok = poster.post(message)
    if ok:
        _mark_posted(key)
        _post_timestamps.append(time.time())
        _last_post_time = time.time()
    return ok


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
def _key_extratime(mid: str)            -> str: return f"extratime:{mid}"
def _key_fulltime(mid: str)             -> str: return f"ft:{mid}"


# ══════════════════════════════════════════════════════════════════
# NON-MATCHDAY STATS POSTS
# ══════════════════════════════════════════════════════════════════

def maybe_post_stats(matches: list):
    """
    Post up to 5 stats updates per day on a fixed UTC schedule.
    Skips if today has >= STATS_BUSY_THRESHOLD active matches
    (unless STATS_ON_MATCHDAYS is explicitly set to true).
    """
    global _last_stats_date, _stats_posted

    if not config.POST_STATS:
        return

    now   = datetime.now(timezone.utc)
    today = now.strftime("%Y-%m-%d")

    # Reset slate at midnight
    if _last_stats_date != today:
        _last_stats_date = today
        _stats_posted    = set()
        _save_state()

    # Skip on busy match days unless overridden
    if not config.STATS_ON_MATCHDAYS:
        active = [
            m for m in matches
            if m["status"] == "IN_PLAY"
        ]
        if len(active) >= config.STATS_BUSY_THRESHOLD:
            return

    sched   = stats_module.STATS_SCHEDULE
    minutes = stats_module.STATS_MINUTE
    league1, league2 = stats_module.todays_leagues()

    for slot, hour in sched.items():
        if slot in _stats_posted:
            continue
        target_min = minutes.get(slot, 0)
        # Fire when we're within the correct hour and past the target minute
        if now.hour != hour or now.minute < target_min:
            continue

        print(f"[STATS] ⏰ Firing stats slot: {slot}")
        _run_stats_slot(slot, league1, league2)
        _stats_posted.add(slot)
        _save_state()
        time.sleep(3)  # small gap between consecutive stats posts


def _run_stats_slot(slot: str, league1: tuple, league2: tuple):
    """Fetch data and post for a single stats slot."""
    if slot == "standings_1":
        rows = stats_module.get_standings(league1)
        if rows:
            poster.post(poster.fmt_standings(league1, rows))
        else:
            print(f"[STATS] ⚠️  No standings data for slot {slot}")

    elif slot == "standings_2":
        rows = stats_module.get_standings(league2)
        if rows:
            poster.post(poster.fmt_standings(league2, rows))
        else:
            print(f"[STATS] ⚠️  No standings data for slot {slot}")

    elif slot == "upcoming":
        fixtures = stats_module.get_upcoming_fixtures(days_ahead=2)
        if fixtures:
            msg = poster.fmt_upcoming_fixtures(fixtures)
            if msg:
                poster.post(msg)
        else:
            print("[STATS] ⚠️  No upcoming fixtures found")


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
    # FD provides lineups; ESPN does not
    if (config.POST_LINEUPS
            and status == "SCHEDULED"
            and match.get("lineups")
            and not _already_posted(_key_lineup(mid))):
        print(f"[BOT] 📋 Lineups: {hname} vs {aname}")
        _post_if_new(_key_lineup(mid), poster.fmt_lineup(match))

    # ── Kick-off ──────────────────────────────────────────────────
    if config.POST_KICKOFF and status == "IN_PLAY":
        kickoff_match = {**match, "score": {
            "halfTime": {"home": None, "away": None},
            "fullTime": {"home": 0, "away": 0},
        }}
        print(f"[BOT] 📌 Kickoff: {hname} vs {aname}")
        _post_if_new(_key_kickoff(mid), poster.fmt_kickoff(kickoff_match))

    # ── Goals ─────────────────────────────────────────────────────
    if config.POST_GOALS and status in ("IN_PLAY", "PAUSED", "EXTRA_TIME", "SHOOTOUT", "FINISHED"):
        for idx, goal in enumerate(match.get("goals", [])):
            key = _key_goal(mid, goal, idx)
            if not _already_posted(key):
                scorer = goal["scorer"]["name"]
                print(f"[BOT] ⚽ Goal: {scorer} — {hname} vs {aname}")
                _post_if_new(key, poster.fmt_goal(match, goal))
                time.sleep(2)

    # ── Extra time ────────────────────────────────────────────────
    if status in ("EXTRA_TIME", "SHOOTOUT") or (
            status == "FINISHED" and match.get("_went_to_et")):
        if not _already_posted(_key_extratime(mid)):
            print(f"[BOT] ⏱️  Extra time: {hname} vs {aname}")
            _post_if_new(_key_extratime(mid), poster.fmt_extratime(match))

    # ── Full time ─────────────────────────────────────────────────
    if config.POST_FULLTIME and status == "FINISHED":
        if match.get("_went_to_penalties"):
            print(f"[BOT] 🏁 Full time (penalties): {hname} vs {aname}")
        elif match.get("_went_to_et"):
            print(f"[BOT] 🏁 Full time (AET): {hname} vs {aname}")
        else:
            print(f"[BOT] 🏁 Full time: {hname} vs {aname}")
        _post_if_new(_key_fulltime(mid), poster.fmt_fulltime(match))


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
        ):
            if key not in _events:
                _events[key] = time.time()
                seeded += 1
        for idx, g in enumerate(m.get("goals", [])):
            k = _key_goal(mid, g, idx)
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
    _load_state()
    _start_keepalive()

    print("[STATE] 🌱 Seeding finished matches on startup...")
    _seed_finished(scraper.get_todays_matches())

    print("=" * 60)
    print("  ScoreLine Live Bot — Running")
    print(f"  Poll interval : {config.POLL_INTERVAL}s")
    print("  Data source   : ESPN ✅ (free, no key needed)")
    print(f"  Lineups       : {config.POST_LINEUPS} (not available from ESPN scoreboard)")
    print(f"  Kick-off      : {config.POST_KICKOFF}")
    print(f"  Goals         : {config.POST_GOALS}")
    print(f"  Extra time    : True")
    print(f"  Full time     : {config.POST_FULLTIME}")
    print(f"  Preview       : {config.POST_DAILY_PREVIEW} @ {config.DAILY_PREVIEW_HOUR}:00 UTC")
    print(f"  Stats posts   : {config.POST_STATS} ({'all days' if config.STATS_ON_MATCHDAYS else f'quiet days only (<{config.STATS_BUSY_THRESHOLD} matches)'})")
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
            maybe_post_stats(matches)

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
