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

# ── Stats posts (non-matchday content) ───────────────────────────
POST_STATS           = os.getenv("POST_STATS",           "true").lower() == "true"
STATS_ON_MATCHDAYS   = os.getenv("STATS_ON_MATCHDAYS",   "false").lower() == "true"
STATS_BUSY_THRESHOLD = int(os.getenv("STATS_BUSY_THRESHOLD", "5"))

# ── Polling ───────────────────────────────────────────────────────
POLL_INTERVAL       = int(os.getenv("POLL_INTERVAL", "60"))

# ── Anti-spam ─────────────────────────────────────────────────────
MIN_POST_GAP        = int(os.getenv("MIN_POST_GAP",        "20"))
MAX_POSTS_PER_HOUR  = int(os.getenv("MAX_POSTS_PER_HOUR",  "25"))

# ── Railway keep-alive ────────────────────────────────────────────
PORT = int(os.getenv("PORT", "8080"))

# ── World Cup mode ─────────────────────────────────────────────────
# When True: standings tables for the 4 leagues below are dropped,
# and quiet gaps are filled with World Cup content instead.
WORLD_CUP_MODE       = os.getenv("WORLD_CUP_MODE", "true").lower() == "true"
WORLD_CUP_SLUG       = os.getenv("WORLD_CUP_SLUG", "fifa.world")

# Leagues whose standings tables are retired while World Cup mode is on
# (Troy: "remove those laliga league1 championship champions league tables")
STANDINGS_RETIRED = {"esp.1", "fra.1", "eng.2", "uefa.champions"}

# Content-filler window & cadence — real match events always take priority
# and reset this clock; filler only fires when nothing has posted recently.
FILLER_START_HOUR    = int(os.getenv("FILLER_START_HOUR", "5"))   # 5am UTC
FILLER_END_HOUR      = int(os.getenv("FILLER_END_HOUR",   "23"))  # 11pm UTC
FILLER_GAP_MINUTES   = int(os.getenv("FILLER_GAP_MINUTES", "30"))

# ── Transfer news ────────────────────────────────────────────────────
POST_TRANSFER_NEWS   = os.getenv("POST_TRANSFER_NEWS", "true").lower() == "true"
TRANSFER_LEAGUES: dict[str, str] = {
    "eng.1": "Premier League",
    "esp.1": "La Liga",
    "ger.1": "Bundesliga",
    "ita.1": "Serie A",
    "fra.1": "Ligue 1",
    "usa.1": "MLS",
}
TRANSFER_POLL_EVERY_TICKS = int(os.getenv("TRANSFER_POLL_EVERY_TICKS", "5"))

# ── VAR / disallowed goals ────────────────────────────────────────────
POST_VAR_DISALLOWED  = os.getenv("POST_VAR_DISALLOWED", "true").lower() == "true"

# ── Data source order ──────────────────────────────────────────────
# Sofascore is tried first; ESPN is the automatic fallback.
PRIMARY_SOURCE  = os.getenv("PRIMARY_SOURCE", "sofascore")
FALLBACK_SOURCE = os.getenv("FALLBACK_SOURCE", "espn")

# ── Win probability (ClubElo) ─────────────────────────────────────────
POST_WIN_PROBABILITY = os.getenv("POST_WIN_PROBABILITY", "true").lower() == "true"
ELO_HOME_ADVANTAGE    = int(os.getenv("ELO_HOME_ADVANTAGE", "60"))
