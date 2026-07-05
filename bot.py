"""
bot.py — Match Corna Live main bot
==================================
Events posted:
  1. 📋 Lineup confirmed (ESPN does not provide this — field is always empty)
  2. 📌 Kick-off
  3. ⚽ Goal (with score, scorer, and assist when available)
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
import transfers
import worldcup
import elo
import graphics
import article

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
_filler_rotation_idx:  int   = 0


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
    """Separate, tighter cap just for breaking transfer news. A deadline-day
    burst of headlines across several leagues can pass MAX_POSTS_PER_HOUR
    easily while still looking spammy on its own — this keeps transfer
    posts specifically to config.TRANSFER_MAX_POSTS_PER_WINDOW per
    config.TRANSFER_WINDOW_MINUTES, independent of everything else the
    bot posts (goals, kickoffs, etc. are unaffected)."""
    global _transfer_post_timestamps
    now = time.time()
    # getattr with defaults: if config.py on the deployed environment is
    # older than bot.py (e.g. only one of the two files got redeployed),
    # this must never crash the poll loop — just fall back to the safe
    # default (2 per 30 min) instead of raising AttributeError.
    max_posts = getattr(config, "TRANSFER_MAX_POSTS_PER_WINDOW", 2)
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
    respects rate limiting and resets the same 30-min content clock."""
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
def _key_elo_update(mid: str)           -> str: return f"elo_updated:{mid}"
def _key_winprob(mid: str)              -> str: return f"winprob:{mid}"
def _key_var(mid: str, v: dict)         -> str: return f"var:{mid}:{v.get('minute','?')}:{v.get('player','?')}"


# ══════════════════════════════════════════════════════════════════
# WORLD CUP FILLER CONTENT (5am–11pm, at least every 30 min)
# ══════════════════════════════════════════════════════════════════

def maybe_post_filler(matches: list):
    """
    Real match events always post immediately and reset the clock
    (via _post_if_new). This only fires when nothing has posted in the
    last FILLER_GAP_MINUTES, inside the FILLER_START_HOUR–FILLER_END_HOUR
    window, rotating between top scorers and win probability.
    """
    global _filler_rotation_idx

    if not config.WORLD_CUP_MODE:
        return

    now = datetime.now(timezone.utc)
    if not (config.FILLER_START_HOUR <= now.hour < config.FILLER_END_HOUR):
        return

    elapsed_min = (time.time() - _last_event_post_time) / 60
    if elapsed_min < config.FILLER_GAP_MINUTES:
        return

    rotation = ["top_scorers", "win_probability"]
    kind = rotation[_filler_rotation_idx % len(rotation)]
    _filler_rotation_idx += 1

    if kind == "top_scorers" and config.WORLD_CUP_MODE:
        scorers = worldcup.get_top_scorers(config.WORLD_CUP_SLUG)
        if scorers:
            print("[FILLER] 👟 Posting World Cup top scorers")
            lines = [f"{s['rank']}. {s['player']} - {s['goals']}" for s in scorers[:5]]
            img = _safe_image(graphics.render_card, "stats", "🚩", "World Cup Top Scorers", lines)
            if _post_now(poster.fmt_top_scorers(scorers), image_path=img):
                return
        # fall through to win-probability if top scorers unavailable this cycle

    if config.POST_WIN_PROBABILITY:
        upcoming = [
            m for m in matches
            if m.get("_is_world_cup") and m["status"] == "SCHEDULED"
        ]
        upcoming.sort(key=lambda m: m.get("utcDate", ""))
        if upcoming:
            m = upcoming[0]
            # Every match needs a stable id for the dedup key below —
            # sofascore.py/scraper.py normalize matches with an "id"
            # field, but fall back to a name+kickoff-time composite so
            # this never crashes if a source is ever missing it.
            mid = m.get("id") or f"{m['homeTeam']['name']}_{m['awayTeam']['name']}_{m.get('utcDate', '')}"
            if _already_posted(_key_winprob(mid)):
                # Already posted the probability for this exact fixture —
                # this was the bug: the old code used _post_now() with no
                # dedup key at all, so the SAME upcoming match (still the
                # earliest scheduled one until it kicks off) got reposted
                # every single filler cycle. Skip it and fall through so
                # a quiet cycle doesn't post nothing at all.
                print(f"[FILLER] ⏭️  Win probability already posted for {m['homeTeam']['name']} vs {m['awayTeam']['name']} — skipping repeat")
            else:
                probs = elo.win_probability(
                    m["homeTeam"]["name"], m["awayTeam"]["name"],
                    home_advantage=config.ELO_HOME_ADVANTAGE,
                )
                if probs:
                    print(f"[FILLER] 🔮 Posting win probability: {m['homeTeam']['name']} vs {m['awayTeam']['name']}")
                    lines = [
                        f"{m['homeTeam']['name']} - {probs['home']}%",
                        f"Draw - {probs['draw']}%",
                        f"{m['awayTeam']['name']} - {probs['away']}%",
                    ]
                    img = _safe_image(
                        graphics.render_card, "stats", "🚩",
                        f"{m['homeTeam']['name']} vs {m['awayTeam']['name']}", lines,
                    )
                    if _post_if_new(_key_winprob(mid), poster.fmt_win_probability(m, probs), image_path=img):
                        return
                else:
                    print("[FILLER] ⚠️  Win probability unavailable this cycle (ClubElo unreachable or team ratings unresolved)")
        else:
            print("[FILLER] ⚠️  No upcoming World Cup fixture to show win probability for")

    print("[FILLER] ⚠️  Nothing posted this cycle — both top scorers and win probability unavailable")


# ══════════════════════════════════════════════════════════════════
# FOOTBALL NEWS — transfers, manager news, World Cup news, post-match
# reactions. Immediate, not tied to the filler clock. Present/future
# only — transfers.py enforces freshness, this never replays old news.
# ══════════════════════════════════════════════════════════════════

# kind -> graphics.py card "kind" (badge color/label). Falls back to
# "transfer" styling for any category not listed here.
_NEWS_CARD_KIND = {
    "transfer":  "transfer",
    "manager":   "manager",
    "worldcup":  "worldcup",
    "interview": "interview",
    "tracker":   "stats",
}


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
        if not _transfer_rate_limit_ok():
            break  # remaining items stay unseen and get retried next poll
        label = item.get("category_label", "News")
        print(f"[NEWS] 📰 {label} ({item['league']}): {item['headline'][:60]}")
        card_kind = _NEWS_CARD_KIND.get(item.get("category"), "transfer")
        img = None
        # Prefer the real article photo (people want to see the player
        # or manager, not a solid-color text card) — falls back
        # automatically to the generated card if the source had no
        # image or it failed to download/decode.
        if item.get("image"):
            img = _safe_image(
                graphics.render_photo_card, card_kind, item["headline"],
                item["image"], source=item.get("source"),
            )
        if not img:
            img = _safe_image(graphics.render_card, card_kind, "", label.upper(), [item["headline"]])
        # Fetch the linked article and pull out a few concrete facts
        # (fee, contract length, one short quote) so the caption is a
        # brief story instead of just the headline again — see
        # article.py for why this extracts facts rather than
        # rewriting the article's prose. Only done here (post time,
        # after the rate-limit check above), not during
        # transfers.check_new(), so items held back by the cap this
        # cycle never cost a wasted fetch.
        try:
            facts = article.fetch_and_extract_facts(item.get("link", ""))
        except Exception as e:
            print(f"[NEWS] ⚠️  Article fetch/extract failed, posting without extra facts: {e}")
            facts = {}
        if _post_if_new(item["key"], poster.fmt_football_news(item, article_facts=facts), image_path=img):
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
    # Fixed: lineups now come from ESPN's /summary endpoint (scoreboard
    # never had them). Fetched once, close to kickoff, per match.
    if (config.POST_LINEUPS
            and status == "SCHEDULED"
            and match.get("_league_slug")
            and not _already_posted(_key_lineup(mid))):
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
                    event_line += f" (assist: {assist})"
                img = _safe_image(
                    graphics.render_scoreboard_card, "goal", hname, aname, h_sc, a_sc,
                    competition=match.get("_comp_name", ""),
                    event_line=event_line,
                    status_label=f"{poster._minute(goal['minute'])}' \u2022 LIVE", show_pulse=True,
                    home_crest_url=match["homeTeam"].get("crest", ""), away_crest_url=match["awayTeam"].get("crest", ""),
                )
                _post_if_new(key, poster.fmt_goal(match, goal), image_path=img)
                time.sleep(2)

    # ── Extra time ────────────────────────────────────────────────
    if status in ("EXTRA_TIME", "SHOOTOUT") or (
            status == "FINISHED" and match.get("_went_to_et")):
        if not _already_posted(_key_extratime(mid)):
            print(f"[BOT] ⏱️  Extra time: {hname} vs {aname}")
            _post_if_new(_key_extratime(mid), poster.fmt_extratime(match))

    # ── Full time ─────────────────────────────────────────────────
    if status == "FINISHED" and not _already_posted(_key_elo_update(mid)):
        h_sc, a_sc = match["score"]["fullTime"].get("home"), match["score"]["fullTime"].get("away")
        elo.record_result(hname, aname, h_sc, a_sc, home_advantage=config.ELO_HOME_ADVANTAGE)
        _mark_posted(_key_elo_update(mid))

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
            status_label = "FULL TIME \u2022 PENALTIES"
        elif match.get("_went_to_et"):
            status_label = "FULL TIME \u2022 AET"
        img = _safe_image(
            graphics.render_scoreboard_card, "fulltime", hname, aname, h_sc or 0, a_sc or 0,
            competition=match.get("_comp_name", ""),
            status_label=status_label, show_pulse=False,
            event_line=poster.scorers_line(match),
            home_crest_url=match["homeTeam"].get("crest", ""), away_crest_url=match["awayTeam"].get("crest", ""),
        )
        _post_if_new(_key_fulltime(mid), poster.fmt_fulltime(match), image_path=img)


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
    global _last_event_post_time
    _load_state()
    # Resuming the filler clock from persisted state, not from "now":
    # blindly stamping time.time() here meant every restart re-armed the
    # 30-min WORLD_CUP_MODE filler wait from zero, regardless of how long
    # the page had actually been quiet — on a debugging session with
    # frequent redeploys this meant filler basically never got a chance
    # to fire. _events[key] is set to time.time() on every real post
    # (via _mark_posted) and during startup seeding, so the most recent
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
    print(f"  Lineups       : {config.POST_LINEUPS} (via ESPN /summary, fetched near kickoff)")
    print(f"  Kick-off      : {config.POST_KICKOFF}")
    print(f"  Goals         : {config.POST_GOALS} (assists included when the source provides one)")
    print(f"  VAR/No Goal   : {config.POST_VAR_DISALLOWED} (best-effort — verify against a live match)")
    print(f"  Extra time    : True")
    print(f"  Full time     : {config.POST_FULLTIME}")
    print(f"  Preview       : {config.POST_DAILY_PREVIEW} @ {config.DAILY_PREVIEW_HOUR}:00 UTC")
    print(f"  World Cup mode: {config.WORLD_CUP_MODE} (filler every {config.FILLER_GAP_MINUTES}min, {config.FILLER_START_HOUR}:00-{config.FILLER_END_HOUR}:00 UTC)")
    print(f"  Football news : {config.POST_TRANSFER_NEWS} — transfers, managers, World Cup, reactions "
          f"({', '.join(config.TRANSFER_LEAGUES.values())}, World Cup)")
    print(f"  Win probability: {config.POST_WIN_PROBABILITY} (ClubElo)")
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
