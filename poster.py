"""
poster.py — Facebook posting + message formatters
===================================================
Handles text feeds and multi-media visual card post distributions.
"""

import requests
import config

def post_to_facebook(text_content: str, image_url: str = None) -> bool:
    """
    Publishes straight to Facebook Page. If image_url is provided, 
    routes to /photos endpoint to create an image preview with a caption.
    """
    if not config.FB_PAGE_ACCESS_TOKEN or not config.FB_PAGE_ID:
        print("[POSTER] ❌ Error: Page Credentials missing inside configurations.")
        return False

    payload = {
        "access_token": config.FB_PAGE_ACCESS_TOKEN
    }

    if image_url:
        url = f"https://graph.facebook.com/v18.0/{config.FB_PAGE_ID}/photos"
        payload["url"] = image_url
        payload["caption"] = text_content
    else:
        url = f"https://graph.facebook.com/v18.0/{config.FB_PAGE_ID}/feed"
        payload["message"] = text_content

    try:
        r = requests.post(url, data=payload, timeout=15)
        res_json = r.json()
        if r.status_code in (200, 201):
            print(f"[POSTER] ✅ Posted! id={res_json.get('id', res_json.get('post_id'))}")
            return True
        else:
            print(f"[POSTER] ❌ Meta Graph Endpoint Error: {res_json}")
            return False
    except Exception as e:
        print(f"[POSTER] ❌ Connection error during publishing: {e}")
        return False


def _minute(v) -> str:
    if not v: return "1"
    s = str(v).split(":")[0]
    return re.sub(r"\D", "", s) or "1"


def _match_hashtags(match: dict) -> list:
    tags = ["#ScoreLineLive"]
    h = match.get("homeTeam", {}).get("name", "").replace(" ", "")
    a = match.get("awayTeam", {}).get("name", "").replace(" ", "")
    if h: tags.append(f"#{h}")
    if a: tags.append(f"#{a}")
    c = match.get("_comp_name", "").replace(" ", "")
    if c: tags.append(f"#{c}")
    return tags


def _build_post(header: str, lines: list, hashtags: list) -> str:
    body = "\n".join(lines)
    footer = " ".join(hashtags)
    return f"{header}\n\n{body}\n\n{footer}"


def fmt_kickoff(match: dict) -> str:
    header = f"🟢 KICKOFF | {match.get('_comp_flag','⚽')} {match.get('_comp_name','Match')}"
    body = [f"🏟️ {match['homeTeam']['name']} 0 - 0 {match['awayTeam']['name']}"]
    return _build_post(header, body, _match_hashtags(match))


def fmt_goal(match: dict, goal_event: dict) -> str:
    header = f"⚽ GOAL | {match.get('_comp_flag','⚽')} {match.get('_comp_name','Match')}"
    h_sc, a_sc = _current_score(match)
    body = [
        f"🏟️ {match['homeTeam']['name']} {h_sc} - {a_sc} {match['awayTeam']['name']}",
        f"\n🔥 {goal_event['player']} ⚽ {_minute(goal_event['minute'])}' ({goal_event.get('team','')})"
    ]
    return _build_post(header, body, _match_hashtags(match))


def fmt_extra_time(match: dict) -> str:
    header = f"⏱️ EXTRA TIME | {match.get('_comp_flag','⚽')} {match.get('_comp_name','Match')}"
    h_sc, a_sc = _current_score(match)
    body = [f"🏟️ {match['homeTeam']['name']} {h_sc} - {a_sc} {match['awayTeam']['name']}"]
    return _build_post(header, body, _match_hashtags(match))


def fmt_fulltime(match: dict) -> str:
    header = f"🏁 FULL TIME | {match.get('_comp_flag','⚽')} {match.get('_comp_name','Match')}"
    h_sc, a_sc = _current_score(match)
    
    et_str = " (AET)" if match.get("_went_to_et") else ""
    body = [f"🏟️ {match['homeTeam']['name']} {h_sc} - {a_sc} {match['awayTeam']['name']}{et_str}"]

    if match.get("_went_to_penalties"):
        hp = match.get("_penalty_home", 0)
        ap = match.get("_penalty_away", 0)
        body.append(f"🏆 Shootout: {match['homeTeam']['name']} {hp} - {ap} {match['awayTeam']['name']}")

    home_goals = [g for g in match.get("goals", []) if g["isHome"]]
    away_goals = [g for g in match.get("goals", []) if not g["isHome"]]

    if home_goals:
        body.append(f"⚽ {match['homeTeam']['name']}: " + ", ".join(
            f"{g['scorer']['name']} {_minute(g['minute'])}'" for g in home_goals))
    if away_goals:
        body.append(f"⚽ {match['awayTeam']['name']}: " + ", ".join(
            f"{g['scorer']['name']} {_minute(g['minute'])}'" for g in away_goals))

    return _build_post(header, body, _match_hashtags(match))


def _current_score(match: dict) -> tuple:
    h = match["score"]["fullTime"].get("home")
    a = match["score"]["fullTime"].get("away")
    return (h if h is not None else 0, a if a is not None else 0)


def fmt_var_disallowed(match: dict, var_event: dict) -> str:
    header = f"No Goal — VAR Review: {match['homeTeam']['name']} vs {match['awayTeam']['name']}"
    minute = _minute(var_event.get("minute", "?"))
    body = [f"🚨 Disallowed: {var_event['player']} ({minute}') — {var_event.get('team', '')}"]
    if var_event.get("reason"):
        body.append(f"Reason: {var_event['reason']}")
    return _build_post(header, body, _match_hashtags(match))
