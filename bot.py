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

import config
import scraper
import poster
import stats as stats_module
import transfers
import worldcup
import elo

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
    try:
        from http.server import BaseHTTPRequestHandler, HTTPServer
    except ImportError:
        return
    try:
        server = HTTPServer(("0.0.0.0", config.PORT), _HealthHandler)
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()
        print(f"[KEEPALIVE] Health check server up on port {config.PORT}")
    except Exception as e:
        print(f"[KEEPALIVE] ⚠️ Could not start server: {e}")


# ══════════════════════════════════════════════════════════════════
# LOCAL PERSISTENT STATE MANAGEMENT
# ══════════════════════════════════════════════════════════════════

STATE_FILE = "state.json"
state = {"posted_events": {}, "last_filler_time": 0, "seen_keys": set()}

def _load_state():
    global state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                raw = json.load(f)
                state["posted_events"] = raw.get("posted_events", {})
                state["last_filler_time"] = raw.get("last_filler_time", 0)
                state["seen_keys"] = set(raw.get("seen_keys", []))
        except Exception as e:
            print(f"[STATE] ⚠️ Error loading state: {e}")


def _save_state():
    try:
        raw = {
            "posted_events": state["posted_events"],
            "last_filler_time": state["last_filler_time"],
            "seen_keys": list(state["seen_keys"])
        }
        with open(STATE_FILE, "w") as f:
            json.dump(raw, f, indent=2)
    except Exception as e:
        print(f"[STATE] ⚠️ Error saving state: {e}")


def _cleanup_state():
    """Removes old tracked matches to prevent state swelling over time."""
    now = time.time()
    cutoff = 3600 * 24
    to_del = []
    for mid, mdata in state["posted_events"].items():
        if now - mdata.get("updated_at", 0) > cutoff:
            to_del.append(mid)
    for mid in to_del:
        del state["posted_events"][mid]
    if to_del:
        _save_state()


# ══════════════════════════════════════════════════════════════════
# MAIN BOT LOGIC ENGINES
# ══════════════════════════════════════════════════════════════════

def process_match(m: dict):
    mid = m["id"]
    status = m["status"]

    if mid not in state["posted_events"]:
        state["posted_events"][mid] = {
            "status": "NONE",
            "goals_posted": [],
            "updated_at": time.time()
        }

    mstate = state["posted_events"][mid]
    mstate["updated_at"] = time.time()

    # 1. Handle Lineups Confirmed
    if config.POST_LINEUPS and mstate["status"] == "NONE":
        if m.get("lineups") and len(m["lineups"]) >= 2:
            post_text = poster.fmt_lineups(m)
            post_id = poster.post_to_facebook(post_text)
            if post_id:
                print(f"[BOT] 📋 Lineups Posted for match {mid}!")
                mstate["status"] = "LINEUPS_POSTED"
                _save_state()

    # If lineup criteria wasn't met but match is starting, bump status forward
    if mstate["status"] == "NONE" and status == "SCHEDULED":
        mstate["status"] = "LINEUPS_POSTED"
        _save_state()

    # 2. Handle Kick-off
    if config.POST_KICKOFF and mstate["status"] == "LINEUPS_POSTED" and status == "IN_PLAY":
        post_text = poster.fmt_kickoff(m)
        post_id = poster.post_to_facebook(post_text)
        if post_id:
            print(f"[BOT] 🟢 Kick-off Posted for match {mid}!")
            mstate["status"] = "IN_PLAY"
            _save_state()

    if mstate["status"] == "LINEUPS_POSTED" and status == "IN_PLAY":
        mstate["status"] = "IN_PLAY"
        _save_state()

    # 3. Handle Live Match Goals & In-Play Events
    if status in ("IN_PLAY", "PAUSED", "EXTRA_TIME", "SHOOTOUT"):
        if config.POST_GOALS:
            for g in m.get("goals", []):
                gid = f"{g.get('minute')}:{g.get('scorer', {}).get('name')}:{g.get('isHome')}"
                if gid in mstate["goals_posted"]:
                    continue
                post_text = poster.fmt_goal(m, g)
                post_id = poster.post_to_facebook(post_text)
                if post_id:
                    print(f"[BOT] ⚽ Goal Posted ({gid}) for match {mid}!")
                    mstate["goals_posted"].append(gid)
                    state["last_filler_time"] = time.time()
                    _save_state()

    # 4. Handle Extra Time Announcements
    if status == "EXTRA_TIME" and mstate["status"] == "IN_PLAY":
        post_text = poster.fmt_extra_time(m)
        post_id = poster.post_to_facebook(post_text)
        if post_id:
            print(f"[BOT] ⏱️ Extra Time Posted for match {mid}!")
            mstate["status"] = "EXTRA_TIME"
            _save_state()

    if status == "EXTRA_TIME" and mstate["status"] == "IN_PLAY":
        mstate["status"] = "EXTRA_TIME"
        _save_state()

    # 5. Handle Full Time / Post Match Conclusions
    if config.POST_FULLTIME and mstate["status"] in ("IN_PLAY", "EXTRA_TIME") and status == "FINISHED":
        post_text = poster.fmt_fulltime(m)
        post_id = poster.post_to_facebook(post_text)
        if post_id:
            print(f"[BOT] 🏁 Full Time Posted for match {mid}!")
            mstate["status"] = "FINISHED"
            state["last_filler_time"] = time.time()
            _save_state()

    if status == "FINISHED" and mstate["status"] != "FINISHED":
        mstate["status"] = "FINISHED"
        _save_state()


def maybe_post_preview(matches):
    if not config.POST_DAILY_PREVIEW:
        return
    now = datetime.now(timezone.utc)
    if now.hour != config.DAILY_PREVIEW_HOUR:
        return

    today_str = now.strftime("%Y-%m-%d")
    pkey = f"preview:{today_str}"
    if pkey in state["seen_keys"]:
        return

    post_text = poster.fmt_daily_preview(matches)
    if post_text:
        post_id = poster.post_to_facebook(post_text)
        if post_id:
            print(f"[BOT] 📅 Daily Preview Posted! id={post_id}")
            state["seen_keys"].add(pkey)
            _save_state()


def maybe_post_stats(matches):
    if not config.POST_STATS:
        return
    has_live = any(m["status"] in ("IN_PLAY", "PAUSED", "EXTRA_TIME", "SHOOTOUT") for m in matches)
    if has_live and not config.STATS_ON_MATCHDAYS:
        return

    now = datetime.now(timezone.utc)
    sched = stats_module.get_post_schedule_for_hour(now.hour)
    if not sched:
        return

    today_str = now.strftime("%Y-%m-%d")
    skey = f"stats:{sched['type']}:{today_str}"
    if skey in state["seen_keys"]:
        return

    post_text = None
    if sched["type"] == "standings":
        post_text = stats_module.get_formatted_standings_post()
    elif sched["type"] == "fixtures":
        post_text = stats_module.get_formatted_fixtures_post()

    if post_text:
        post_id = poster.post_to_facebook(post_text)
        if post_id:
            print(f"[BOT] 🏆 Stats Scheduled Post ({sched['type']}) Posted!")
            state["seen_keys"].add(skey)
            _save_state()


def maybe_post_transfer_news(tick):
    """
    Polls for new transfer news every X ticks, formats them elegantly,
    posts them immediately, and instantly saves state to prevent duplicates.
    """
    if not config.POST_TRANSFER_NEWS:
        return
        
    if tick % config.TRANSFER_POLL_EVERY_TICKS != 0:
        return

    try:
        new_transfers = transfers.check_new(state.get("seen_keys", set()))
        if not new_transfers:
            return

        for item in new_transfers:
            key = item["key"]
            
            if key in state.get("seen_keys", set()):
                continue

            post_text = poster.fmt_transfer_news(item)
            image_url = item.get("image")
            post_id = poster.post_to_facebook(post_text, image_url=image_url)

            if post_id:
                print(f"[BOT] 📰 Transfer News Posted! id={post_id}")
                if "seen_keys" not in state:
                    state["seen_keys"] = set()
                state["seen_keys"].add(key)
                _save_state()  # Commit immediately inside loop block

    except Exception as e:
        print(f"[BOT] ⚠️ Error in transfer news cycle: {e}")


def maybe_post_filler(matches):
    if not config.POST_FILLER:
        return
    now = datetime.now(timezone.utc)
    if not (config.FILLER_START_HOUR <= now.hour <= config.FILLER_END_HOUR):
        return

    has_live = any(m["status"] in ("IN_PLAY", "PAUSED", "EXTRA_TIME", "SHOOTOUT") for m in matches)
    if has_live:
        return

    if time.time() - state["last_filler_time"] < (config.FILLER_GAP_MINUTES * 60):
        return

    # Alternate content generation variants
    minute_block = now.minute // 30
    post_text = None

    if minute_block % 2 == 0:
        post_text = worldcup.get_formatted_top_scorers_post()
    else:
        post_text = worldcup.get_formatted_probability_post()

    if post_text:
        post_id = poster.post_to_facebook(post_text)
        if post_id:
            print(f"[BOT] 🔥 Content Filler Posted! id={post_id}")
            state["last_filler_time"] = time.time()
            _save_state()


# ══════════════════════════════════════════════════════════════════
# MAIN INITIALIZATION ENTRY POINT
# ══════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    print("[BOT] Starting Container Setup...")
    _load_state()
    _start_keepalive()

    print("[BOT] Initialization Complete. Starting polling schedule loops...")
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
            print(f"[BOT] ⚠️ Critical Exception caught in loop execution: {e}")

        time.sleep(config.POLL_INTERVAL)
