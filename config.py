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

# ── Transfermarkt weekly-dataset hourly highlight ──────────────────────
# Separate from POST_TRANSFER_NEWS (breaking news, immediate). This is
# real historical data (github.com/dcaribou/transfermarkt-datasets),
# refreshed weekly, drip-fed as one highlight per hour.
POST_TRANSFERMARKT_HIGHLIGHTS = os.getenv("POST_TRANSFERMARKT_HIGHLIGHTS", "true").lower() == "true"
TRANSFERMARKT_INTERVAL_MIN    = int(os.getenv("TRANSFERMARKT_INTERVAL_MIN", "60"))
