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
POST_FULLTIME       = os.getenv("POST_FULLTIME",       "true").lower() == "true"
POST_DAILY_PREVIEW  = os.getenv("POST_DAILY_PREVIEW",  "true").lower() == "true"

# Hour (UTC) to post the morning fixture list
DAILY_PREVIEW_HOUR  = int(os.getenv("DAILY_PREVIEW_HOUR", "7"))

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

# ── World Cup mode ─────────────────────────────────────────────────
# When True: quiet gaps (no real match event in FILLER_GAP_MINUTES) are
# filled with World Cup content (top scorers / win probability).
WORLD_CUP_MODE       = os.getenv("WORLD_CUP_MODE", "true").lower() == "true"
WORLD_CUP_SLUG       = os.getenv("WORLD_CUP_SLUG", "fifa.world")

# Content-filler window & cadence — real match events always take priority
# and reset this clock; filler only fires when nothing has posted recently.
FILLER_START_HOUR    = int(os.getenv("FILLER_START_HOUR", "5"))   # 5am UTC
FILLER_END_HOUR      = int(os.getenv("FILLER_END_HOUR",   "23"))  # 11pm UTC
FILLER_GAP_MINUTES   = int(os.getenv("FILLER_GAP_MINUTES", "30"))

# ── Football news (transfers, manager news, World Cup news, reactions) ──
# All current/live — never historical. A single headline "clock",
# shared across every news flavor below.
POST_TRANSFER_NEWS   = os.getenv("POST_TRANSFER_NEWS", "true").lower() == "true"

# Club leagues polled for breaking news via ESPN's per-league /news feed.
TRANSFER_LEAGUES: dict[str, str] = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ger.1": "Bundesliga",
    "ita.1": "Serie A",
    "fra.1": "Ligue 1",
    "usa.1": "MLS",
}
TRANSFER_POLL_EVERY_TICKS = int(os.getenv("TRANSFER_POLL_EVERY_TICKS", "5"))

# Independent safety net from the dedup state: even if state.json is
# ever lost (a redeploy without a persistent volume, a corrupted file,
# etc.), a headline older than this is never posted as "breaking" news
# no matter what the dedup memory thinks — this is what stops a state
# wipe from replaying an entire morning's stories hours later. Applies
# to every news category (transfers, manager news, World Cup news,
# post-match reactions) — this bot only ever posts what's current.
TRANSFER_MAX_AGE_HOURS = int(os.getenv("TRANSFER_MAX_AGE_HOURS", "6"))

# Cap for breaking football news specifically — a burst of headlines
# (deadline day, a big World Cup night) can otherwise post many times
# in a row even though MAX_POSTS_PER_HOUR hasn't been hit yet, which
# reads as spammy and risks a Facebook flag. Per your request: max 2
# news posts (with image) every 15 minutes to keep reach healthy
# without flooding the page.
TRANSFER_MAX_POSTS_PER_WINDOW = int(os.getenv("TRANSFER_MAX_POSTS_PER_WINDOW", "2"))
TRANSFER_WINDOW_MINUTES       = int(os.getenv("TRANSFER_WINDOW_MINUTES",       "15"))

# ── VAR / disallowed goals ────────────────────────────────────────────
POST_VAR_DISALLOWED  = os.getenv("POST_VAR_DISALLOWED", "true").lower() == "true"

# ── Data source order ──────────────────────────────────────────────
# Sofascore is tried first; ESPN is the automatic fallback.
PRIMARY_SOURCE  = os.getenv("PRIMARY_SOURCE", "sofascore")
FALLBACK_SOURCE = os.getenv("FALLBACK_SOURCE", "espn")

# ── Win probability (ClubElo) ─────────────────────────────────────────
POST_WIN_PROBABILITY = os.getenv("POST_WIN_PROBABILITY", "true").lower() == "true"
ELO_HOME_ADVANTAGE    = int(os.getenv("ELO_HOME_ADVANTAGE", "60"))
