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

# Man of the Match — only available for Sofascore-sourced matches (ESPN's
# free API carries no player ratings), so this silently posts nothing for
# an ESPN-sourced match rather than guessing a name.
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

# ── World Cup mode ─────────────────────────────────────────────────
# When True: quiet gaps (no real match event in FILLER_GAP_MINUTES) are
# filled with World Cup top-scorers content.
WORLD_CUP_MODE       = os.getenv("WORLD_CUP_MODE", "true").lower() == "true"
WORLD_CUP_SLUG       = os.getenv("WORLD_CUP_SLUG", "fifa.world")

# Content-filler window & cadence — real match events always take priority
# and reset this clock; filler only fires when nothing has posted recently.
FILLER_START_HOUR    = int(os.getenv("FILLER_START_HOUR", "5"))   # 5am UTC
FILLER_END_HOUR      = int(os.getenv("FILLER_END_HOUR",   "23"))  # 11pm UTC
FILLER_GAP_MINUTES   = int(os.getenv("FILLER_GAP_MINUTES", "30"))

# ── Football news (transfers, manager news, World Cup news, gossip) ──
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
    "ksa.1": "Saudi Pro League",
}
TRANSFER_POLL_EVERY_TICKS = int(os.getenv("TRANSFER_POLL_EVERY_TICKS", "5"))

# Player-quote spotlight posts (currently scoped to Messi and Ronaldo —
# see transfers._PLAYER_QUOTE_PATTERNS) and injury-news posts share the
# same news pipeline/freshness rules as every other category above, and
# can each be switched off independently.
POST_PLAYER_QUOTES  = os.getenv("POST_PLAYER_QUOTES",  "true").lower() == "true"
POST_INJURY_NEWS    = os.getenv("POST_INJURY_NEWS",    "true").lower() == "true"

# Independent safety net from the dedup state: even if state.json is
# ever lost (a redeploy without a persistent volume, a corrupted file,
# etc.), a headline older than this is never posted as "breaking" news
# no matter what the dedup memory thinks — this is what stops a state
# wipe from replaying an entire morning's stories hours later. Applies
# to every news category (player transfers, manager sackings, manager
# transfers, deal-done, gossip, World Cup news) — this bot only ever
# posts what's current.
TRANSFER_MAX_AGE_HOURS = int(os.getenv("TRANSFER_MAX_AGE_HOURS", "6"))

# Cap for breaking football news specifically — a burst of headlines
# (deadline day, a big World Cup night) can otherwise post many times
# in a row even though MAX_POSTS_PER_HOUR hasn't been hit yet, which
# reads as spammy and risks a Facebook flag. Max 1 news post every 30
# minutes keeps reach healthy without flooding the page.
TRANSFER_MAX_POSTS_PER_WINDOW = int(os.getenv("TRANSFER_MAX_POSTS_PER_WINDOW", "2"))
TRANSFER_WINDOW_MINUTES       = int(os.getenv("TRANSFER_WINDOW_MINUTES",       "30"))

# ── VAR / disallowed goals ────────────────────────────────────────────
POST_VAR_DISALLOWED  = os.getenv("POST_VAR_DISALLOWED", "true").lower() == "true"

# ── Data source order ──────────────────────────────────────────────
# Sofascore is tried first; ESPN is the automatic fallback.
PRIMARY_SOURCE  = os.getenv("PRIMARY_SOURCE", "sofascore")
FALLBACK_SOURCE = os.getenv("FALLBACK_SOURCE", "espn")
