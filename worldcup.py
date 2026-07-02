"""
worldcup.py — Tournament tracking interfaces for ScoreLine Live
"""

def get_formatted_top_scorers_post() -> str | None:
    """Safely handles the top scorers loop call by returning None."""
    return None

# ── FIXED: MISSING PROBABILITY INTERFACE ───────────────────────────
def get_formatted_probability_post() -> str | None:
    """
    Safely fulfills bot.py's prediction/probability routine check.
    Returns None to skip rendering empty blocks on the feed.
    """
    return None
