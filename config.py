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
