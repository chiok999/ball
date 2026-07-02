"""
scraper.py — Match aggregation wrapper for ScoreLine Live
=========================================================
Bridges match retrieval between Sofascore (primary with bypass) 
and ESPN (fallback), strictly isolating World Cup targets.
"""

import sofascore
import espn

def _comp_flag_helper(comp_name: str) -> str:
    """
    Isolates World Cup competitions exclusively.
    Returns None if the game belongs to an unrelated competition context.
    """
    c = comp_name.lower()
    if "world cup" in c or "fifa world cup" in c:
        return "🌍"
    return None


def _is_valid_senior_intl(home_name: str, away_name: str) -> bool:
    """
    Strictly filters out youth, women's, or non-senior international squads.
    """
    for name in (home_name.lower(), away_name.lower()):
        if any(x in name for x in ["u17", "u19", "u20", "u21", "u23", "women", "sub-", "youth"]):
            return False
    return True


def get_todays_matches() -> list[dict]:
    """
    Attempts to fetch filtered matches from Sofascore.
    Falls back completely to ESPN if Sofascore returns 0 entries or 404s.
    """
    matches = []
    try:
        matches = sofascore.get_todays_matches(
            comp_flag_fn=_comp_flag_helper, 
            is_intl_fn=_is_valid_senior_intl
        )
    except Exception:
        print("[SCRAPER] Sofascore engine errored out — shifting to ESPN")

    # Filter Sofascore payload for explicit world cup structures matching flag requirements
    if matches:
        valid_sofa = [m for m in matches if m.get("_comp_flag") == "🌍"]
        if valid_sofa:
            return valid_sofa

    print("[SCRAPER] Sofascore returned 0 target matches — falling back to ESPN")
    
    raw_espn = espn.fetch_todays_matches()
    filtered_espn = []
    
    for m in raw_espn:
        comp_name = m.get("_comp_name", "")
        home_name = m.get("homeTeam", {}).get("name", "")
        away_name = m.get("awayTeam", {}).get("name", "")
        
        flag = _comp_flag_helper(comp_name)
        is_intl = _is_valid_senior_intl(home_name, away_name)
        
        if flag == "🌍" and is_intl:
            m["_comp_flag"] = flag
            filtered_espn.append(m)
            
    return filtered_espn
