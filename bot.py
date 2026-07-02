"""
bot.py — ScoreLine Live main bot
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
import transfers
import worldcup
import elo

STATE_FILE = "state.json"
_state = {"seen_events": [], "seen_transfers": [], "last_post_time": 0}

def _load_state():
    global _state
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE, "r") as f:
                _state = json.load(f)
        except Exception:
            pass

def _save_state():
    try:
        with open(STATE_FILE, "w") as f:
            json.dump(_state, f)
    except Exception as e:
        print(f"[STATE] Save error: {e}")

class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        body = b"ScoreLine Live is running OK"
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, fmt, *args): pass

def _start_keepalive():
    server = HTTPServer(("0.0.0.0", config.PORT), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    print(f"[KEEPALIVE] Health check server up on port {config.PORT}")

def _can_post(min_gap=15) -> bool:
    return (time.time() - _state.get("last_post_time", 0)) >= min_gap

def _mark_posted():
    _state["last_post_time"] = time.time()
    _save_state()

def maybe_post_transfer_news(tick):
    if not config.POST_TRANSFER_NEWS or tick % config.TRANSFER_POLL_EVERY_TICKS != 0:
        return

    print("[BOT] Checking transfer markets across leagues...")
    seen_set = set(_state.get("seen_transfers", []))
    new_items = transfers.check_new(seen_set)

    for item in new_items:
        if not _can_post(config.MIN_POST_GAP):
            rem = int(config.MIN_POST_GAP - (time.time() - _state.get("last_post_time", 0)))
            if rem > 0:
                print(f"[BOT] ⏳ Rate limit: waiting {rem}s (MIN_POST_GAP)")
                time.sleep(rem)

        msg = f"📰 {item['league']}: {item['headline']}\n\nRead details: {item['link']}"
        
        # Pulls image_url automatically out of the item object mapping
        success = poster.post_to_facebook(msg, image_url=item.get("image_url"))
        if success:
            _state.setdefault("seen_transfers", []).append(item["key"])
            _mark_posted()

def process_match(m):
    mid = m["id"]
    status = m["status"]
    seen = _state.setdefault("seen_events", [])

    if status == "SCHEDULED":
        return

    # Kickoff event
    ko_key = f"{mid}:kickoff"
    if ko_key not in seen and config.POST_KICKOFF:
        if _can_post(config.MIN_POST_GAP) and poster.post_to_facebook(poster.fmt_kickoff(m)):
            seen.append(ko_key)
            _mark_posted()

    # Live Goal tracking
    if config.POST_GOALS:
        for g in m.get("goals", []):
            g_key = f"{mid}:goal:{g['minute']}:{g['player'].replace(' ','')}"
            if g_key not in seen:
                if _can_post(config.MIN_POST_GAP) and poster.post_to_facebook(poster.fmt_goal(m, g)):
                    seen.append(g_key)
                    _mark_posted()

    # Match over event
    ft_key = f"{mid}:finished"
    if status == "FINISHED" and ft_key not in seen and config.POST_FULLTIME:
        if _can_post(config.MIN_POST_GAP) and poster.post_to_facebook(poster.fmt_fulltime(m)):
            seen.append(ft_key)
            _mark_posted()

def maybe_post_preview(matches): pass
def maybe_post_stats(matches): pass
def maybe_post_filler(matches): pass
def _cleanup_state(): pass

def main():
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
                print(f"       {m.get('_comp_flag','⚽')} {m['homeTeam']['name']} vs {m['awayTeam']['name']} [{m['status']}]")

            maybe_post_transfer_news(tick)

            active = [m for m in matches if m["status"] in ("IN_PLAY", "PAUSED", "FINISHED")]
            for match in active:
                try:
                    process_match(match)
                except Exception as e:
                    print(f"[BOT] ⚠️ Match tracking error {match.get('id','?')}: {e}")

            time.sleep(config.POLL_INTERVAL)
        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"[BOT] Loop structural failure exception: {e}")
            time.sleep(10)

if __name__ == "__main__":
    main()
