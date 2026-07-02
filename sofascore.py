import datetime
from curl_cffi import requests  # Upgraded to impersonate real browser TLS handshakes

# Updated headers to exactly match Chrome wire-order conventions
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "en-US,en;q=0.9",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Origin": "https://www.sofascore.com",
    "Referer": "https://www.sofascore.com/",
}

def _get(url: str, timeout: int = 15) -> dict | None:
    """
    Performs an impersonated GET request against Sofascore API endpoints 
    to bypass strict Cloudflare/Imperva TLS fingerprint blocks.
    """
    try:
        # impersonate="chrome" forces curl_cffi to match browser JA3/JA4 hashes
        r = requests.get(url, headers=HEADERS, timeout=timeout, impersonate="chrome")
        
        if r.status_code == 200:
            return r.json()
            
        print(f"[SOFASCORE] HTTP {r.status_code} when requesting: {url[:90]}")
    except Exception as e:
        print(f"[SOFASCORE] ❌ Network request exception: {e}")
    return None

def get_todays_matches() -> list[dict]:
    """
    Fetches today's live and upcoming football matches from Sofascore.
    """
    # Format today's date into YYYY-MM-DD
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    url = f"https://api.sofascore.com/api/v1/sport/football/scheduled-events/{today_str}"
    
    print(f"[SOFASCORE] Fetching match schedule for {today_str}...")
    data = _get(url)
    
    if not data or "events" not in data:
        print("[SOFASCORE] ⚠️ Failed to fetch or parse response payload.")
        return []
        
    normalized_matches = []
    for event in data["events"]:
        try:
            # Extract basic structure safely
            home_team = event.get("homeTeam", {}).get("name", "Unknown Home")
            away_team = event.get("awayTeam", {}).get("name", "Unknown Away")
            status_type = event.get("status", {}).get("type", "inprogress")
            
            # Status resolution logic
            status = "not_started"
            if status_type == "finished":
                status = "finished"
            elif status_type == "inprogress":
                status = "live"

            match_data = {
                "id": str(event.get("id")),
                "home_team": home_team,
                "away_team": away_team,
                "home_score": event.get("homeScore", {}).get("current", 0),
                "away_score": event.get("awayScore", {}).get("current", 0),
                "status": status,
                "minute": event.get("status", {}).get("description", ""),
                "incidents": []
            }
            normalized_matches.append(match_data)
        except KeyError as ke:
            print(f"[SOFASCORE] Key parsing error inside event structure: {ke}")
            continue

    print(f"[SOFASCORE] Successfully parsed {len(normalized_matches)} matches.")
    return normalized_matches

def get_match_incidents(match_id: str) -> list[dict]:
    """
    Fetches real-time events (Goals, Cards) for a specific match ID.
    """
    url = f"https://api.sofascore.com/api/v1/event/{match_id}/incidents"
    data = _get(url)
    
    if not data or "incidents" not in data:
        return []
        
    normalized_incidents = []
    for inc in data["incidents"]:
        try:
            inc_type = inc.get("type")
            # Only track highly vital match metrics
            if inc_type not in ["goal", "card"]:
                continue
                
            normalized_incidents.append({
                "id": str(inc.get("id")),
                "type": inc_type,
                "time": inc.get("time", 0),
                "is_home": inc.get("isHome", False),
                "player": inc.get("player", {}).get("name", "Unknown Player"),
                "detail": inc.get("incidentClass", "")  # e.g., regular, penalty, yellow, red
            })
        except Exception:
            continue
            
    return normalized_incidents
