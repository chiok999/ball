"""
espn.py — High-tier Fallback Match Scraper Engine
=================================================
Fetches live match streams directly from ESPN's public API endpoints,
reformatting payload data structures to match ScoreLine's internal schema.
"""

import requests
from datetime import datetime

def fetch_todays_matches() -> list[dict]:
    """
    Queries ESPN's hidden scoreboard endpoint for today's international fixtures,
    parsing them safely into standardized dictionary structures for scraper.py.
    """
    # Using ESPN's standard soccer scoreboard endpoint
    url = "https://site.api.espn.com/apis/site/v2/sports/soccer/fifa.world/scoreboard"
    
    try:
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            print(f"[ESPN API] Failed to fetch data: HTTP {response.status_code}")
            return []
            
        data = response.json()
        events = data.get("events", [])
        parsed_matches = []
        
        for event in events:
            try:
                # Extracting Competition Context
                competition = "FIFA World Cup"
                
                # Match Status & Timing
                status_obj = event.get("status", {})
                status_type = status_obj.get("type", {}).get("name", "STATUS_SCHEDULED")
                
                # Map raw status formats to ScoreLine expected codes
                match_status = "SCHEDULED"
                if status_type == "STATUS_IN_PROGRESS":
                    match_status = "IN_PLAY"
                elif status_type == "STATUS_FINAL":
                    match_status = "FINISHED"

                # Extract Team Details
                competitors = event.get("competitions", [{}])[0].get("competitors", [])
                if len(competitors) < 2:
                    continue
                    
                # ESPN puts Home/Away as variables inside properties
                home_data = next((c for c in competitors if c.get("homeAway") == "home"), competitors[0])
                away_data = next((c for c in competitors if c.get("homeAway") == "away"), competitors[1])
                
                home_team = {
                    "id": home_data.get("id", "H"),
                    "name": home_data.get("team", {}).get("displayName", "Unknown Home")
                }
                
                away_team = {
                    "id": away_data.get("id", "A"),
                    "name": away_data.get("team", {}).get("displayName", "Unknown Away")
                }
                
                # Extract Scores
                score_obj = {
                    "fullTime": {
                        "home": int(home_data.get("score", 0)),
                        "away": int(away_data.get("score", 0))
                    }
                }
                
                # Construct clean unified payload entry
                match_payload = {
                    "_comp_name": competition,
                    "homeTeam": home_team,
                    "awayTeam": away_team,
                    "status": match_status,
                    "score": score_obj,
                    "goals": [] # Fallback streams fill events dynamically
                }
                
                parsed_matches.append(match_payload)
                
            except Exception as e:
                print(f"[ESPN API] Error parsing individual match event: {e}")
                continue
                
        return parsed_matches

    except Exception as e:
        print(f"[ESPN API] Connection or parsing runtime failure: {e}")
        return []
