"""
config.py — ScoreLine Live configuration
All settings come from environment variables so Railway deployment is clean.
A local .env file is loaded automatically when present (for development).
"""
import os

# Load .env if present (dev only — Railway uses real env vars)
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# ── Facebook ──────────────────────────────────────────────────────
FB_PAGE_ID           = os.getenv("FB_PAGE_ID", "")
FB_PAGE_ACCESS_TOKEN = os.getenv("FB_PAGE_ACCESS_TOKEN", "")

# ── What to post ──────────────────────────────────────────────────
POST_LINEUPS        = os.getenv("POST_LINEUPS",        "true").lower() == "true"
POST_KICKOFF        = os.getenv("POST_KICKOFF",        "true").lower() == "true"
POST_GOALS          = os.getenv("POST_GOALS",          "true").lower() == "true"
POST_HALFTIME       = os.getenv("POST_HALFTIME",       "true").lower() == "true"
POST_RED_CARDS      = os.getenv("POST_RED_CARDS",      "true").lower() == "true"
POST_FULLTIME       = os.getenv("POST_FULLTIME",       "true").lower() == "true"
POST_DAILY_PREVIEW  = os.getenv("POST_DAILY_PREVIEW",  "true").lower() == "true"

# Man of the Match — ESPN's free API carries no player ratings, so this
# currently always posts nothing (kept as a flag for a future source).
POST_MOTM            = os.getenv("POST_MOTM",            "true").lower() == "true"

# Hour (UTC) to post the morning fixture list
DAILY_PREVIEW_HOUR  = int(os.getenv("DAILY_PREVIEW_HOUR", "9"))

# ── Lineups ───────────────────────────────────────────────────────
# Lineups are fetched once a match gets within this many minutes of
# kickoff (real-world availability is ~60 min pre-kickoff on ESPN's
# /summary endpoint) — posting too early just wastes a fetch that
# always comes back empty. process_match() re-checks every tick until
# either lineups are found or the match kicks off.
LINEUP_LEAD_MINUTES  = int(os.getenv("LINEUP_LEAD_MINUTES", "65"))

# ── Polling ───────────────────────────────────────────────────────
POLL_INTERVAL       = int(os.getenv("POLL_INTERVAL", "60"))

# ── Anti-spam ─────────────────────────────────────────────────────
MIN_POST_GAP        = int(os.getenv("MIN_POST_GAP",        "20"))
MAX_POSTS_PER_HOUR  = int(os.getenv("MAX_POSTS_PER_HOUR",  "25"))

# ── Railway keep-alive ────────────────────────────────────────────
PORT = int(os.getenv("PORT", "8080"))

# ── Persistent data directory ────────────────────────────────────────
# Railway rebuilds a fresh container on every deploy, which wipes any
# file written to the default local path (like state.json). Point this
# at a mounted Railway Volume (e.g. "/data") to survive redeploys —
# otherwise the bot has no memory of what it already posted and will
# repost recent matches/goals/news after every update.
DATA_DIR = os.getenv("DATA_DIR", ".")

# ── Football news (deal done, deal collapsed, manager news, injuries) ──
# All current/live — never historical. A single headline "clock",
# shared across every news flavor below.
POST_TRANSFER_NEWS   = os.getenv("POST_TRANSFER_NEWS", "true").lower() == "true"

# Transfer/deal news only posts during these hours (matchday hours are
# busy, so no news noise then) — 6am-9pm Malawi time (CAT, UTC+2), i.e.
# 04:00-19:00 UTC.
TRANSFER_NEWS_START_HOUR = int(os.getenv("TRANSFER_NEWS_START_HOUR", "4"))
TRANSFER_NEWS_END_HOUR   = int(os.getenv("TRANSFER_NEWS_END_HOUR",   "19"))

# Club leagues polled for breaking news via ESPN's per-league /news feed.
TRANSFER_LEAGUES: dict[str, str] = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ger.1": "Bundesliga",
    "ita.1": "Serie A",
    "fra.1": "Ligue 1",
    "usa.1": "MLS",
    "ksa.1": "Saudi Pro League",
}
TRANSFER_POLL_EVERY_TICKS = int(os.getenv("TRANSFER_POLL_EVERY_TICKS", "5"))

# Player-quote spotlight posts (currently scoped to Messi and Ronaldo —
# see transfers._PLAYER_QUOTE_PATTERNS) and injury-news posts share the
# same news pipeline/freshness rules as every other category above, and
# can each be switched off independently.
POST_PLAYER_QUOTES  = os.getenv("POST_PLAYER_QUOTES",  "true").lower() == "true"
POST_INJURY_NEWS    = os.getenv("POST_INJURY_NEWS",    "true").lower() == "true"

# ── Quiet-hours filler content (player stat spotlights) ──────────────
# Fires when there's no live match action, at most once per
# FILLER_INTERVAL_MINUTES, during EITHER window below:
#   - the FILLER_PRE_MATCH_HOURS before any scheduled kickoff today, or
#   - the fixed local-time FILLER_WINDOW_START_HOUR-FILLER_WINDOW_END_HOUR
#     window (covers days with no match at all, or match-day hours
#     outside the pre-match window).
# API_FOOTBALL_KEY is optional — leave blank and the bot still posts
# hand-verified legend/historical stats from player_stats_verified.json,
# it just skips the live current-season top-scorer posts.
API_FOOTBALL_KEY         = os.getenv("API_FOOTBALL_KEY", "")
POST_FILLER_CONTENT      = os.getenv("POST_FILLER_CONTENT", "true").lower() == "true"
FILLER_INTERVAL_MINUTES  = int(os.getenv("FILLER_INTERVAL_MINUTES", "60"))
FILLER_PRE_MATCH_HOURS   = float(os.getenv("FILLER_PRE_MATCH_HOURS", "3"))
FILLER_WINDOW_START_HOUR = int(os.getenv("FILLER_WINDOW_START_HOUR", "18"))  # 6pm local
FILLER_WINDOW_END_HOUR   = int(os.getenv("FILLER_WINDOW_END_HOUR", "22"))   # 10pm local
# Local-time offset from UTC in hours (e.g. 2 for CAT/Malawi). Only
# affects the fixed window above — everything else in the bot runs in UTC.
FILLER_TZ_OFFSET_HOURS   = int(os.getenv("FILLER_TZ_OFFSET_HOURS", "2"))

# Which football-news categories are allowed to post at all, as a
# comma-separated list of: deal_done, deal_collapsed, manager_sacking,
# manager_transfer, injury, player_quote. Default is every category
# (today's behavior). Set e.g. TRANSFER_NEWS_CATEGORIES=deal_done to
# quiet the page down to confirmed signings only — useful right after
# a World Cup or transfer deadline when gossip-adjacent volume across
# every category gets noisy even though gossip itself was never
# posted. POST_PLAYER_QUOTES / POST_INJURY_NEWS above still apply on
# top of this list (both must allow a category for it to post).
_ALL_NEWS_CATEGORIES = {
    "deal_done", "deal_collapsed", "manager_sacking",
    "manager_transfer", "injury", "player_quote",
}
_raw_categories = os.getenv("TRANSFER_NEWS_CATEGORIES", "").strip()
if _raw_categories:
    TRANSFER_NEWS_CATEGORIES = {
        c.strip().lower() for c in _raw_categories.split(",") if c.strip()
    } & _ALL_NEWS_CATEGORIES
else:
    TRANSFER_NEWS_CATEGORIES = set(_ALL_NEWS_CATEGORIES)

# Independent safety net from the dedup state: even if state.json is
# ever lost (a redeploy without a persistent volume, a corrupted file,
# etc.), a headline older than this is never posted as "breaking" news
# no matter what the dedup memory thinks — this is what stops a state
# wipe from replaying an entire morning's stories hours later. Applies
# to every news category (deal-done, deal-collapsed, manager sackings,
# manager transfers, injuries) — this bot only ever posts what's
# current.
TRANSFER_MAX_AGE_HOURS = int(os.getenv("TRANSFER_MAX_AGE_HOURS", "6"))

# Cap for breaking football news specifically — a burst of headlines
# (deadline day) can otherwise post many times in a row even though
# MAX_POSTS_PER_HOUR hasn't been hit yet, which reads as spammy and
# risks a Facebook flag. Max 1 news post every 30 minutes keeps reach
# healthy without flooding the page.
TRANSFER_MAX_POSTS_PER_WINDOW = int(os.getenv("TRANSFER_MAX_POSTS_PER_WINDOW", "1"))
TRANSFER_WINDOW_MINUTES       = int(os.getenv("TRANSFER_WINDOW_MINUTES",       "30"))

# ── VAR / disallowed goals ────────────────────────────────────────────
POST_VAR_DISALLOWED  = os.getenv("POST_VAR_DISALLOWED", "true").lower() == "true"

