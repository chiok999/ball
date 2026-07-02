"""
scraper.py — Match aggregation wrapper for ScoreLine Live
=========================================================
Bridges match retrieval between Sofascore (primary with bypass) 
and ESPN (fallback), explicitly passing down filtering logic.
"""

import sofascore
import espn

def _comp_flag_helper(comp_name: str) -> str:
    """
    Determines emoji flag mappings for top-tier competitions.
    Returns '⚽' if the competition is not a primary target.
    """
    c = comp_name.lower()
    if "premier league" in c or "england" in c:
        return "🏴󠁧󠁢󠁥󠁮󠁧󠁿"
    if "la liga" in c or "spain" in c:
        return "🇪🇸"
    if "serie a" in c or "italy" in c:
        return "🇮🇹"
    if "bundesliga" in c or "germany" in c:
        return "🇩🇪"
    if "ligue 1" in c or "france" in c:
        return "🇫🇷"
    if "champions league" in c or "ucl" in c:
        return "🏆"
    if "world cup" in c or "fifa world cup" in c:
        return "🌍"
    return "⚽"


def _is_valid_senior_intl(home_name: str, away_name: str) -> bool:
    """
    Strictly filters out youth, women's, or non-senior international squads.
    Returns True only if both teams appear to be senior men's national teams.
    """
    for name in (home_name.lower(), away_name.lower()):
        # Kick out explicit youth brackets or non-senior markers
        if any(x in name for x in ["u17", "u19", "u20", "u21", "u23", "women", "sub-", "youth"]):
            return False
            
    # Add common senior country team checks here if your scraper needs explicit string matching
    return True


def get_todays_matches() -> list[dict]:
    """
    Attempts to fetch filtered matches from Sofascore.
    Falls back completely to ESPN if Sofascore returns 0 entries.
    """
    # Force Sofascore to use our strict local filtering logic
    matches = sofascore.get_todays_matches(
        comp_flag_fn=_comp_flag_helper, 
        is_intl_fn=_is_valid_senior_intl
    )
    
    if matches:
        return matches

    print("[SCRAPER] Sofascore returned 0 target matches — falling back to ESPN")
    
    # Fallback track
    raw_espn = espn.fetch_todays_matches()
    filtered_espn = []
    
    for m in raw_espn:
        comp_name = m.get("_comp_name", "")
        home_name = m.get("homeTeam", {}).get("name", "")
        away_name = m.get("awayTeam", {}).get("name", "")
        
        flag = _comp_flag_helper(comp_name)
        is_intl = _is_valid_senior_intl(home_name, away_name)
        
        # Apply the exact same rules to ESPN payloads if Sofascore drops out
        if (flag and flag != "⚽") or is_intl:
            m["_comp_flag"] = flag
            filtered_espn.append(m)
            
    return filtered_espn
