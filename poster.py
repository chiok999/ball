"""
poster.py — Facebook posting + message formatters
===================================================
Post formats:

  Lineup (FD only):
    📋 LINEUPS | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
    🏟️ Arsenal vs Chelsea
    Arsenal (4-3-3): Raya, White, Saliba...
    Chelsea (4-2-3-1): Sanchez, James...
    #Arsenal #Chelsea #PL #ScoreLineLive

  Kickoff:
    🟢 KICKOFF | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
    🏟️ Arsenal 0 - 0 Chelsea
    #Arsenal #Chelsea #PL #ScoreLineLive

  Goal:
    ⚽ GOAL | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
    🏟️ Arsenal 2 - 1 Chelsea
    Saka ⚽ 67'
    #Arsenal #Chelsea #PL #ScoreLineLive

  Half Time (FD only):
    ⏸️ HALF TIME | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
    🏟️ Arsenal 1 - 0 Chelsea
    #Arsenal #Chelsea #PL #ScoreLineLive

  Red Card (FD only):
    🟥 RED CARD | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
    🏟️ Arsenal 1 - 0 Chelsea
    Reece James (Chelsea) 🟥 45'
    #Arsenal #Chelsea #PL #ScoreLineLive

  Extra Time:
    ⏱️ EXTRA TIME | 🏆 Champions League
    🏟️ Arsenal 1 - 1 Real Madrid
    #Arsenal #RealMadrid #UCL #ScoreLineLive

  Full Time:
    🏁 FULL TIME | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
    🏟️ Arsenal 3 - 1 Chelsea
    Arsenal
    ⚽ Goals: Saka 12', Jesus 89'
    Chelsea
    ⚽ Goals: Palmer 43'
    #Arsenal #Chelsea #PL #ScoreLineLive
"""

import re
import requests
import config

def post_to_facebook(message: str, image_url: str = None) -> str | None:
    """
    Publishes to Facebook Page Feed.
    If image_url is supplied, maps to /photos endpoint, otherwise /feed.
    Returns post_id string on success, or None on failure.
    """
    if not config.FB_PAGE_ID or not config.FB_PAGE_ACCESS_TOKEN:
        print("[POSTER] ⚠️ Facebook Configuration missing. Post skipped.")
        return None

    # Determine endpoint target type
    if image_url:
        url = f"https://graph.facebook.com/v18.0/{config.FB_PAGE_ID}/photos"
        payload = {
            "caption": message,
            "url": image_url,
            "access_token": config.FB_PAGE_ACCESS_TOKEN
        }
    else:
        url = f"https://graph.facebook.com/v18.0/{config.FB_PAGE_ID}/feed"
        payload = {
            "message": message,
            "access_token": config.FB_PAGE_ACCESS_TOKEN
        }

    try:
        r = requests.post(url, data=payload, timeout=15)
        res = r.json()
        if r.status_code in (200, 201):
            return res.get("id") or res.get("post_id")
        print(f"[POSTER] ❌ FB Error {r.status_code}: {res}")
    except Exception as e:
        print(f"[POSTER] ❌ Connection to Graph API failed: {e}")
    return None


def _minute(val) -> str:
    """Normalizes '45+2' or '90:12' shapes down to standard minute logs."""
    s = str(val).split(":")[0].strip()
    return s


def _clean_hash(name: str) -> str:
    """Transforms 'Manchester City' -> 'ManchesterCity'."""
    return re.sub(r"\W+", "", name)


def _match_hashtags(match: dict) -> list[str]:
    h = f"#{_clean_hash(match['homeTeam']['name'])}"
    a = f"#{_clean_hash(match['awayTeam']['name'])}"
    tags = [h, a]
    
    comp = match.get("_comp_name", "")
    if "Premier League" in comp:
        tags.append("#PL")
    elif "Champions League" in comp or "UCL" in comp:
        tags.append("#UCL")
    elif "La Liga" in comp:
        tags.append("#LaLiga")
    elif "World Cup" in comp:
        tags.append("#WorldCup2026")
        
    tags.append("#ScoreLineLive")
    return tags


def _build_post(header: str, body: list[str], hashtags: list[str]) -> str:
    body_str = "\n".join(body)
    hash_str = " ".join(hashtags)
    return f"{header}\n━━━━━━━━━━━━━━━━━━━━━\n\n{body_str}\n\n{hash_str}"


def fmt_lineups(match: dict) -> str:
    flag = match.get("_comp_flag", "⚽")
    comp = match.get("_comp_name", "Football Match")
    header = f"📋 LINEUPS | {flag} {comp}"
    
    body = [f"🏟️ {match['homeTeam']['name']} vs {match['awayTeam']['name']}"]
    return _build_post(header, body, _match_hashtags(match))


def fmt_kickoff(match: dict) -> str:
    flag = match.get("_comp_flag", "⚽")
    comp = match.get("_comp_name", "Football Match")
    header = f"🟢 KICKOFF | {flag} {comp}"
    
    body = [f"🏟️ {match['homeTeam']['name']} 0 - 0 {match['awayTeam']['name']}"]
    return _build_post(header, body, _match_hashtags(match))


def fmt_goal(match: dict, goal_event: dict) -> str:
    flag = match.get("_comp_flag", "⚽")
    comp = match.get("_comp_name", "Football Match")
    header = f"⚽ GOAL | {flag} {comp}"
    
    h_sc = match["score"]["fullTime"].get("home", 0)
    a_sc = match["score"]["fullTime"].get("away", 0)
    
    body = [
        f"🏟️ {match['homeTeam']['name']} {h_sc} - {a_sc} {match['awayTeam']['name']}",
        "",
        f"👤 {goal_event['scorer']['name']} ⚽ {_minute(goal_event['minute'])}'"
    ]
    return _build_post(header, body, _match_hashtags(match))


def fmt_extra_time(match: dict) -> str:
    flag = match.get("_comp_flag", "⚽")
    comp = match.get("_comp_name", "Football Match")
    header = f"⏱️ EXTRA TIME | {flag} {comp}"
    
    h_sc = match["score"]["fullTime"].get("home", 0)
    a_sc = match["score"]["fullTime"].get("away", 0)
    
    body = [f"🏟️ {match['homeTeam']['name']} {h_sc} - {a_sc} {match['awayTeam']['name']} (Moving to ET)"]
    return _build_post(header, body, _match_hashtags(match))


def fmt_fulltime(match: dict) -> str:
    flag = match.get("_comp_flag", "⚽")
    comp = match.get("_comp_name", "Football Match")
    
    suffix = ""
    if match.get("_went_to_penalties"):
        suffix = " (AFT penalties)"
    elif match.get("_went_to_et"):
        suffix = " (AET)"
        
    header = f"🏁 FULL TIME{suffix} | {flag} {comp}"
    
    h_sc = match["score"]["fullTime"].get("home", 0)
    a_sc = match["score"]["fullTime"].get("away", 0)
    
    body = [f"🏟️ {match['homeTeam']['name']} {h_sc} - {a_sc} {match['awayTeam']['name']}", ""]
    
    if match.get("_went_to_penalties"):
        hp = match.get("_penalty_home", 0)
        ap = match.get("_penalty_away", 0)
        body.append(f"💥 Penalty Shootout: {match['homeTeam']['name']} {hp} - {ap} {match['awayTeam']['name']}")
        body.append("")

    home_goals = [g for g in match.get("goals", []) if g["isHome"]]
    away_goals = [g for g in match.get("goals", []) if not g["isHome"]]

    if home_goals:
        body.append(f"⚽ {match['homeTeam']['name']}: " + ", ".join(
            f"{g['scorer']['name']} {_minute(g['minute'])}'" for g in home_goals))
    if away_goals:
        body.append(f"⚽ {match['awayTeam']['name']}: " + ", ".join(
            f"{g['scorer']['name']} {_minute(g['minute'])}'" for g in away_goals))

    return _build_post(header, body, _match_hashtags(match))


def fmt_var_disallowed(match: dict, var_event: dict) -> str:
    header = f"No Goal — VAR Review: {match['homeTeam']['name']} vs {match['awayTeam']['name']}"
    minute = _minute(var_event.get("minute", "?"))
    body = [f"🚨 Disallowed: {var_event['player']} ({minute}') — {var_event.get('team', '')}"]
    reason = var_event.get("reason")
    if reason:
        body.append(f"Reason: {reason}")
    return _build_post(header, body, ["#VAR", "#NoGoal", "#ScoreLineLive"])


def fmt_daily_preview(matches: list[dict]) -> str | None:
    if not matches:
        return None
    header = "📅 TODAY'S FIXTURE LIST"
    body = []
    current_comp = None
    
    for m in matches:
        comp = m.get("_comp_name", "Other Matches")
        flag = m.get("_comp_flag", "⚽")
        if comp != current_comp:
            if body:
                body.append("")
            body.append(f"{flag} {comp.upper()}:")
            current_comp = comp
        body.append(f"   ⏰ {m['homeTeam']['name']} vs {m['awayTeam']['name']}")
        
    return _build_post(header, body, ["#Fixtures", "#Matchday", "#ScoreLineLive"])


def fmt_transfer_news(transfer_item: dict) -> str:
    """
    Formats transfer news updates cleanly and professionally.
    No messy links, clear source credit, and an engaging call-to-action.
    """
    league = transfer_item.get("league", "Top Football")
    headline = transfer_item.get("headline", "").strip()
    
    header = f"📰 TRANSFER UPDATE | {league}"
    
    body = [
        f"🚨 {headline}",
        "",
        "ℹ️ Source: ScoreLine Live Scouting / ESPN API"
    ]
    
    tags = ["#TransferNews", "#TransferWindow", "#ScoreLineLive"]
    if "Premier League" in league:
        tags.append("#PL")
    elif "La Liga" in league:
        tags.append("#LaLiga")

    full_post = (
        f"{header}\n"
        f"━━━━━━━━━━━━━━━━━━━━━\n\n"
        f"{"\n".join(body)}\n\n"
        f"👉 Follow our page for more instant football updates and breaking news! ⚽🔥\n\n"
        f"{" ".join(tags)}"
    )
    return full_post
