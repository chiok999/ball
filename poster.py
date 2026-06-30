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
    ⚽ Saka 12'  ⚽ Havertz 45'  ⚽ Trossard 89'
    Chelsea
    ⚽ Sterling 34'
    #Arsenal #Chelsea #PL #ScoreLineLive
"""

import time
import requests
import config

_FB_API = "v22.0"   # bump here when Meta deprecates the current version

# ══════════════════════════════════════════════════════════════════
# COUNTRY → FLAG EMOJI
# ══════════════════════════════════════════════════════════════════

COUNTRY_FLAG = {
    # Europe
    "England": "🏴󠁧󠁢󠁥󠁮󠁧󠁿", "Scotland": "🏴󠁧󠁢󠁳󠁣󠁴󠁿", "Wales": "🏴󠁧󠁢󠁷󠁬󠁳󠁿",
    "Germany": "🇩🇪", "France": "🇫🇷", "Spain": "🇪🇸", "Italy": "🇮🇹",
    "Portugal": "🇵🇹", "Netherlands": "🇳🇱", "Belgium": "🇧🇪",
    "Croatia": "🇭🇷", "Serbia": "🇷🇸", "Poland": "🇵🇱",
    "Turkey": "🇹🇷", "Ukraine": "🇺🇦", "Switzerland": "🇨🇭",
    "Austria": "🇦🇹", "Denmark": "🇩🇰", "Sweden": "🇸🇪",
    "Norway": "🇳🇴", "Finland": "🇫🇮", "Hungary": "🇭🇺",
    "Czech Republic": "🇨🇿", "Czechia": "🇨🇿", "Slovakia": "🇸🇰",
    "Romania": "🇷🇴", "Greece": "🇬🇷", "Iceland": "🇮🇸",
    "Ireland": "🇮🇪", "Republic of Ireland": "🇮🇪",
    "Northern Ireland": "🏴󠁧󠁢󠁥󠁮󠁧󠁿",
    "Albania": "🇦🇱", "Kosovo": "🇽🇰", "Montenegro": "🇲🇪",
    "Slovenia": "🇸🇮", "Bosnia": "🇧🇦",
    "Bosnia and Herzegovina": "🇧🇦", "Bosnia & Herzegovina": "🇧🇦",
    "Bulgaria": "🇧🇬", "North Macedonia": "🇲🇰",
    "Georgia": "🇬🇪", "Armenia": "🇦🇲", "Azerbaijan": "🇦🇿",
    "Russia": "🇷🇺", "Belarus": "🇧🇾", "Moldova": "🇲🇩",
    "Lithuania": "🇱🇹", "Latvia": "🇱🇻", "Estonia": "🇪🇪",
    "Luxembourg": "🇱🇺", "Malta": "🇲🇹", "Cyprus": "🇨🇾",
    "Israel": "🇮🇱", "Kazakhstan": "🇰🇿",
    "Faroe Islands": "🇫🇴", "Gibraltar": "🇬🇮",
    "San Marino": "🇸🇲", "Andorra": "🇦🇩", "Liechtenstein": "🇱🇮",
    # Americas
    "Brazil": "🇧🇷", "Argentina": "🇦🇷", "Uruguay": "🇺🇾",
    "Colombia": "🇨🇴", "Chile": "🇨🇱", "Peru": "🇵🇪",
    "Ecuador": "🇪🇨", "Bolivia": "🇧🇴", "Paraguay": "🇵🇾",
    "Venezuela": "🇻🇪",
    "USA": "🇺🇸", "United States": "🇺🇸", "Mexico": "🇲🇽",
    "Canada": "🇨🇦", "Costa Rica": "🇨🇷", "Panama": "🇵🇦",
    "Honduras": "🇭🇳", "Jamaica": "🇯🇲", "Haiti": "🇭🇹",
    "Trinidad and Tobago": "🇹🇹", "Trinidad & Tobago": "🇹🇹",
    "El Salvador": "🇸🇻", "Guatemala": "🇬🇹", "Nicaragua": "🇳🇮",
    "Cuba": "🇨🇺", "Curacao": "🇨🇼", "Martinique": "🇲🇶",
    "Aruba": "🇦🇼", "Bermuda": "🇧🇲", "Grenada": "🇬🇩",
    "Guyana": "🇬🇾", "Belize": "🇧🇿", "Suriname": "🇸🇷",
    # Africa
    "Nigeria": "🇳🇬", "Ghana": "🇬🇭", "Senegal": "🇸🇳",
    "Morocco": "🇲🇦", "Egypt": "🇪🇬", "Cameroon": "🇨🇲",
    "Ivory Coast": "🇨🇮", "Cote d'Ivoire": "🇨🇮",
    "South Africa": "🇿🇦", "Tunisia": "🇹🇳", "Algeria": "🇩🇿",
    "Mali": "🇲🇱", "Zambia": "🇿🇲", "Zimbabwe": "🇿🇼",
    "Tanzania": "🇹🇿", "Uganda": "🇺🇬", "Kenya": "🇰🇪",
    "Ethiopia": "🇪🇹", "Congo": "🇨🇬", "DR Congo": "🇨🇩",
    "Guinea": "🇬🇳", "Guinea-Bissau": "🇬🇼",
    "Burkina Faso": "🇧🇫", "Benin": "🇧🇯",
    "Gabon": "🇬🇦", "Angola": "🇦🇴", "Mozambique": "🇲🇿",
    "Rwanda": "🇷🇼", "Liberia": "🇱🇷", "Sierra Leone": "🇸🇱",
    "Gambia": "🇬🇲", "Togo": "🇹🇬", "Niger": "🇳🇪",
    "Namibia": "🇳🇦", "Botswana": "🇧🇼", "Malawi": "🇲🇼",
    "Mauritania": "🇲🇷", "Cape Verde": "🇨🇻",
    "Cape Verde Islands": "🇨🇻",
    "Equatorial Guinea": "🇬🇶", "Sudan": "🇸🇩",
    "South Sudan": "🇸🇸", "Somalia": "🇸🇴",
    "Central African Republic": "🇨🇫",
    "Sao Tome and Principe": "🇸🇹",
    "Comoros": "🇰🇲", "Seychelles": "🇸🇨",
    "Eswatini": "🇸🇿", "Lesotho": "🇱🇸",
    # Asia
    "Japan": "🇯🇵", "South Korea": "🇰🇷", "Korea Republic": "🇰🇷",
    "China": "🇨🇳", "Australia": "🇦🇺",
    "Iran": "🇮🇷", "IR Iran": "🇮🇷",
    "Saudi Arabia": "🇸🇦", "Qatar": "🇶🇦",
    "UAE": "🇦🇪", "United Arab Emirates": "🇦🇪",
    "Iraq": "🇮🇶", "Jordan": "🇯🇴",
    "Oman": "🇴🇲", "Bahrain": "🇧🇭", "Kuwait": "🇰🇼",
    "India": "🇮🇳", "Thailand": "🇹🇭", "Vietnam": "🇻🇳",
    "Indonesia": "🇮🇩", "Malaysia": "🇲🇾", "Philippines": "🇵🇭",
    "Uzbekistan": "🇺🇿", "Tajikistan": "🇹🇯",
    "North Korea": "🇰🇵", "Korea DPR": "🇰🇵",
    "Syria": "🇸🇾", "Lebanon": "🇱🇧", "Palestine": "🇵🇸",
    "Pakistan": "🇵🇰", "Bangladesh": "🇧🇩",
    "Hong Kong": "🇭🇰", "Singapore": "🇸🇬",
    "Sri Lanka": "🇱🇰", "Nepal": "🇳🇵",
    "Myanmar": "🇲🇲", "Cambodia": "🇰🇭",
    "Kyrgyzstan": "🇰🇬", "Turkmenistan": "🇹🇲",
    # Oceania
    "New Zealand": "🇳🇿", "Fiji": "🇫🇯",
    "Papua New Guinea": "🇵🇬", "Solomon Islands": "🇸🇧",
}

COMP_HASHTAG = {
    "Premier League":             "PL",
    "Bundesliga":                 "Bundesliga",
    "La Liga":                    "LaLiga",
    "Serie A":                    "SerieA",
    "Ligue 1":                    "Ligue1",
    "Champions League":           "UCL",
    "Europa League":              "UEL",
    "Europa Conference League":   "UECL",
    "FA Cup":                     "FACup",
    "EFL Cup":                    "EFLCup",
    "Championship":               "Championship",
    "Eredivisie":                 "Eredivisie",
    "MLS":                        "MLS",
    "Brasileirao":                "Brasileirao",
    "Liga MX":                    "LigaMX",
    "Belgian Pro League":         "JPL",
    "Saudi Pro League":           "SPL",
    "AFC Champions Elite":        "ACL",
    "CAF Champions League":       "CAFCL",
    "International Friendly":     "Friendly",
    "FIFA World Cup":             "WorldCup",
    "European Championship":      "EURO",
    "UEFA Nations League":        "NationsLeague",
    "Copa America":               "CopaAmerica",
    "Gold Cup":                   "GoldCup",
    "AFCON":                      "AFCON",
    "WC Qualifier Europe":        "WCQ",
    "WC Qualifier Africa":        "WCQ",
    "WC Qualifier CONCACAF":      "WCQ",
    "WC Qualifier South America": "WCQ",
    "WC Qualifier Asia":          "WCQ",
    "WC Qualifier Oceania":       "WCQ",
}


def _comp_tag(comp_name: str) -> str:
    tag = COMP_HASHTAG.get(comp_name, "")
    if not tag:
        tag = comp_name.replace(" ", "")
    return f"#{tag}"


def team_flag(name: str) -> str:
    if name in COUNTRY_FLAG:
        return COUNTRY_FLAG[name]
    for country, flag in COUNTRY_FLAG.items():
        if country.lower() in name.lower():
            return flag
    return ""


def _td(name: str, is_intl: bool) -> str:
    if is_intl:
        f = team_flag(name)
        return f"{f} {name}" if f else name
    return f"🏟️ {name}"


def _scoreline(match: dict, home_sc, away_sc) -> str:
    is_intl = match.get("_is_intl", False)
    h = _td(match["homeTeam"]["name"], is_intl)
    a = _td(match["awayTeam"]["name"], is_intl)
    return f"{h} {home_sc} - {away_sc} {a}"


def _live_scoreline(match: dict) -> str:
    """Current full-time score (used for live events like halftime / red card)."""
    h  = match["score"]["fullTime"].get("home")
    a  = match["score"]["fullTime"].get("away")
    hs  = str(h) if h is not None else "0"
    as_ = str(a) if a is not None else "0"
    return _scoreline(match, hs, as_)


def _final_scoreline(match: dict) -> str:
    return _live_scoreline(match)


def _minute(minute) -> str:
    s = str(minute).strip().rstrip("'")
    if ":" in s:
        s = s.split(":")[0]
    return s


def _hashtags(match: dict) -> str:
    h    = match["homeTeam"]["name"].replace(" ", "")
    a    = match["awayTeam"]["name"].replace(" ", "")
    comp = _comp_tag(match.get("_comp_name", ""))
    return f"#{h} #{a} {comp} #ScoreLineLive"


def _comp_header(match: dict) -> str:
    flag = match.get("_comp_flag", "⚽")
    name = match.get("_comp_name", "Football")
    return f"{flag} {name}"


# ══════════════════════════════════════════════════════════════════
# RATE LIMITING
# ══════════════════════════════════════════════════════════════════

_last_post_time  = 0.0
_posts_this_hour = 0
_hour_start      = time.time()


def _rate_ok() -> bool:
    global _posts_this_hour, _hour_start
    now = time.time()
    if now - _hour_start > 3600:
        _posts_this_hour = 0
        _hour_start      = now
    if _posts_this_hour >= config.MAX_POSTS_PER_HOUR:
        print(f"[POSTER] ⚠️  Hourly limit ({config.MAX_POSTS_PER_HOUR}) reached")
        return False
    gap = config.MIN_POST_GAP - (now - _last_post_time)
    if gap > 0:
        time.sleep(gap)
    return True


# ══════════════════════════════════════════════════════════════════
# FACEBOOK POSTING
# ══════════════════════════════════════════════════════════════════

def post(message: str) -> bool:
    """Post a text update to the Facebook page feed."""
    global _last_post_time, _posts_this_hour
    if not config.FB_PAGE_ID:
        print(f"\n{'='*50}\n[FB POST]\n{message}\n{'='*50}\n")
        return True
    if not _rate_ok():
        return False
    try:
        r = requests.post(
            f"https://graph.facebook.com/{_FB_API}/{config.FB_PAGE_ID}/feed",
            data={"message": message, "access_token": config.FB_PAGE_ACCESS_TOKEN},
            timeout=15,
        )
        if r.status_code == 200:
            _last_post_time   = time.time()
            _posts_this_hour += 1
            print(f"[POSTER] ✅ Posted! id={r.json().get('id','?')}")
            return True
        err = r.json().get("error", {})
        print(f"[POSTER] ❌ {r.status_code}: {err.get('message', r.text[:120])}")
        return False
    except Exception as e:
        print(f"[POSTER] ❌ {e}")
        return False


def post_photo(image_path: str, caption: str = "") -> bool:
    """Upload a photo to the Facebook page."""
    global _last_post_time, _posts_this_hour
    if not config.FB_PAGE_ID:
        print(f"\n{'='*50}\n[FB PHOTO] {image_path}\n{caption}\n{'='*50}\n")
        return True
    if not _rate_ok():
        return False
    try:
        with open(image_path, "rb") as img_file:
            r = requests.post(
                f"https://graph.facebook.com/{_FB_API}/{config.FB_PAGE_ID}/photos",
                data={"caption": caption, "access_token": config.FB_PAGE_ACCESS_TOKEN},
                files={"source": img_file},
                timeout=60,
            )
        if r.status_code == 200:
            _last_post_time   = time.time()
            _posts_this_hour += 1
            print(f"[POSTER] ✅ Photo posted! id={r.json().get('id','?')}")
            return True
        err = r.json().get("error", {})
        print(f"[POSTER] ❌ Photo {r.status_code}: {err.get('message', r.text[:120])}")
        return False
    except FileNotFoundError:
        print(f"[POSTER] ❌ Image not found: {image_path}")
        return False
    except Exception as e:
        print(f"[POSTER] ❌ Photo error: {e}")
        return False


# ══════════════════════════════════════════════════════════════════
# MESSAGE FORMATTERS
# ══════════════════════════════════════════════════════════════════

def fmt_daily_preview(matches: list) -> str:
    from datetime import datetime, timezone
    now     = datetime.now(timezone.utc)
    day_num  = now.strftime("%d").lstrip("0") or "0"
    date_str = f"{now.strftime('%A')} {day_num} {now.strftime('%B')}"

    if not matches:
        return (
            f"📅 Today's Fixtures | {date_str}\n"
            "No big matches today. Check back tomorrow!\n"
            "#ScoreLineLive"
        )

    sorted_m = sorted(matches, key=lambda m: m.get("utcDate", ""))
    by_comp: dict[str, list] = {}
    for m in sorted_m:
        comp = m.get("_comp_name", "Football")
        by_comp.setdefault(comp, []).append(m)

    lines = [f"📅 Today's Fixtures | {date_str}"]
    for comp, comp_matches in by_comp.items():
        flag    = comp_matches[0].get("_comp_flag", "⚽")
        is_intl = comp_matches[0].get("_is_intl", False)
        lines.append(f"{flag} {comp}")
        for m in comp_matches:
            h = _td(m["homeTeam"]["name"], is_intl)
            a = _td(m["awayTeam"]["name"], is_intl)
            try:
                ko = datetime.fromisoformat(m["utcDate"].replace("Z", "+00:00"))
                t  = ko.strftime("%H:%M")
            except Exception:
                t = "TBD"
            lines.append(f"{h} vs {a} ({t})")

    lines.append("#ScoreLineLive")
    return "\n".join(lines)


def fmt_lineup(match: dict) -> str:
    is_intl = match.get("_is_intl", False)
    h = _td(match["homeTeam"]["name"], is_intl)
    a = _td(match["awayTeam"]["name"], is_intl)
    lines = [
        f"📋 LINEUPS | {_comp_header(match)}",
        f"{h} vs {a}",
    ]
    for lu in match.get("lineups", []):
        team      = lu.get("team", "")
        formation = lu.get("formation", "")
        players   = [p["player"].get("name", "?") for p in lu.get("startXI", [])]
        if players:
            header = f"{team} ({formation})" if formation else team
            lines.append(f"{header}: {', '.join(players)}")
    lines.append(_hashtags(match))
    return "\n".join(lines)


def fmt_kickoff(match: dict) -> str:
    return "\n".join([
        f"🟢 KICKOFF | {_comp_header(match)}",
        _scoreline(match, 0, 0),
        _hashtags(match),
    ])


def fmt_goal(match: dict, goal: dict) -> str:
    scorer = goal["scorer"]["name"]
    minute = _minute(goal["minute"])

    sc = goal.get("score", [])
    if sc and len(sc) == 2 and sc[0] is not None:
        h_sc, a_sc = sc[0], sc[1]
    else:
        h_sc, a_sc = 0, 0
        for g in match.get("goals", []):
            if g["isHome"]:
                h_sc += 1
            else:
                a_sc += 1
            if g is goal:
                break

    return "\n".join([
        f"⚽ GOAL | {_comp_header(match)}",
        _scoreline(match, h_sc, a_sc),
        f"{scorer} ⚽ {minute}'",
        _hashtags(match),
    ])


def fmt_halftime(match: dict) -> str:
    """
    Half-time score post.
    Uses score.halfTime from football-data.org which provides it accurately.
    Falls back to score.fullTime if halfTime is unavailable.
    """
    ht  = match["score"].get("halfTime", {})
    hs  = ht.get("home")
    as_ = ht.get("away")

    # Fallback: use current fullTime score if halfTime not populated yet
    if hs is None or as_ is None:
        ft  = match["score"].get("fullTime", {})
        hs  = ft.get("home") or 0
        as_ = ft.get("away") or 0

    return "\n".join([
        f"⏸️ HALF TIME | {_comp_header(match)}",
        _scoreline(match, hs, as_),
        _hashtags(match),
    ])


def fmt_red_card(match: dict, booking: dict) -> str:
    """
    Red card post.
    Shows the player, their team, the minute, and the current live score.
    """
    player  = booking["player"]["name"]
    team    = booking["team"]["shortName"]
    minute  = _minute(booking["minute"])
    card    = booking.get("card", "RED_CARD")
    # Second yellow shown differently
    emoji   = "🟨🟥" if card == "YELLOW_RED_CARD" else "🟥"

    return "\n".join([
        f"{emoji} RED CARD | {_comp_header(match)}",
        _live_scoreline(match),
        f"{player} ({team}) {emoji} {minute}'",
        _hashtags(match),
    ])


def fmt_extratime(match: dict) -> str:
    return "\n".join([
        f"⏱️ EXTRA TIME | {_comp_header(match)}",
        _final_scoreline(match),
        _hashtags(match),
    ])


# ══════════════════════════════════════════════════════════════════
# STATS FORMATTERS (non-matchday content)
# ══════════════════════════════════════════════════════════════════

def fmt_standings(league: tuple, rows: list) -> str:
    """
    🏆 League Table post — top 6 + relegation zone.

    Example:
      🏆 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League — League Table
      ━━━━━━━━━━━━━━━━━━━━━━━━
      🥇 Arsenal        28GP  +20 GD  59pts
      🥈 Man City       28GP  +18 GD  57pts
      ...
      ⬇️ 18. Luton      28GP  -19 GD  21pts
      #PL #ScoreLineLive
    """
    _, name, flag, tag = league
    lines = [f"🏆 {flag} {name} — League Table", "━" * 26]

    top    = rows[:6]
    bottom = rows[-3:] if len(rows) > 9 else []

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}
    champ  = {4: "🔵", 5: "🟡", 6: "🟡"}  # UCL / UEL zone colour hints

    for r in top:
        pos  = r["pos"]
        icon = medals.get(pos, champ.get(pos, f"{pos}."))
        team = r["team"][:15]
        lines.append(
            f"{icon} {team:<15}  {r['played']}GP  {r['gd']:>4} GD  {r['points']}pts"
        )

    if bottom:
        lines.append("  ⋮")
        lines.append("⚠️  Relegation Zone")
        for r in bottom:
            team = r["team"][:15]
            lines.append(
                f"⬇️ {r['pos']}. {team:<14}  {r['points']}pts  {r['gd']:>4} GD"
            )

    lines.append(f"\n#{tag} #ScoreLineLive")
    return "\n".join(lines)


def fmt_top_scorers(league: tuple, scorers: list) -> str:
    """
    👟 Top Scorers / Golden Boot post — top 10.

    Example:
      👟 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League — Top Scorers
      ━━━━━━━━━━━━━━━━━━━━━━━━
      🥇 Erling Haaland (Man City) — 22 ⚽
      🥈 Cole Palmer (Chelsea) — 19 ⚽
      ...
      #PL #GoldenBoot #ScoreLineLive
    """
    _, name, flag, tag = league
    lines = [f"👟 {flag} {name} — Golden Boot Race", "━" * 26]

    medals = {1: "🥇", 2: "🥈", 3: "🥉"}

    for s in scorers[:10]:
        rank   = s["rank"]
        icon   = medals.get(rank, f"{rank}.")
        player = s["player"]
        team   = s["team"][:13]
        goals  = s["goals"]
        lines.append(f"{icon} {player} ({team}) — {goals} ⚽")

    lines.append(f"\n#{tag} #GoldenBoot #ScoreLineLive")
    return "\n".join(lines)


def fmt_upcoming_fixtures(fixtures: list) -> str:
    """
    📅 Upcoming Fixtures post — next 48 hours grouped by date then competition.
    """
    from datetime import datetime, timezone

    if not fixtures:
        return ""

    lines = ["📅 Upcoming Fixtures — Next 48 Hours"]

    by_date: dict[str, list] = {}
    for f in fixtures:
        d = f["utcDate"][:10]
        by_date.setdefault(d, []).append(f)

    for date_str, day_fixtures in sorted(by_date.items()):
        try:
            dt        = datetime.fromisoformat(date_str)
            day_label = dt.strftime("%A %d %B")
        except Exception:
            day_label = date_str
        lines.append(f"\n📆 {day_label}")

        by_comp: dict[str, list] = {}
        for f in day_fixtures:
            by_comp.setdefault(f["comp"], []).append(f)

        for comp, comp_fixtures in by_comp.items():
            cflag = comp_fixtures[0].get("comp_flag", "⚽")
            lines.append(f"{cflag} {comp}")
            for f in comp_fixtures[:5]:
                try:
                    ko = datetime.fromisoformat(
                        f["utcDate"].replace("Z", "+00:00")
                    )
                    t  = ko.strftime("%H:%M")
                except Exception:
                    t = "TBD"
                lines.append(f"  {f['home']} vs {f['away']}  ({t} UTC)")

    lines.append("\n#ScoreLineLive")
    return "\n".join(lines)


def fmt_fulltime(match: dict) -> str:
    prefix = "FULL TIME"
    if match.get("_went_to_penalties"):
        ph = match.get("_penalty_home")
        pa = match.get("_penalty_away")
        prefix = "FULL TIME (Penalties)" if (ph is not None and pa is not None) else "FULL TIME (Pens)"
    elif match.get("_went_to_et"):
        prefix = "FULL TIME (AET)"

    lines = [
        f"🏁 {prefix} | {_comp_header(match)}",
        _final_scoreline(match),
    ]

    if match.get("_went_to_penalties"):
        ph = match.get("_penalty_home")
        pa = match.get("_penalty_away")
        if ph is not None and pa is not None:
            winner = match["homeTeam"]["name"] if ph > pa else match["awayTeam"]["name"]
            lines.append(f"{winner} win {ph} - {pa} on penalties")

    home_goals = [g for g in match.get("goals", []) if     g["isHome"]]
    away_goals = [g for g in match.get("goals", []) if not g["isHome"]]

    if home_goals:
        lines.append(match["homeTeam"]["name"])
        for g in home_goals:
            lines.append(f"⚽ {g['scorer']['name']} {_minute(g['minute'])}'")
    if away_goals:
        lines.append(match["awayTeam"]["name"])
        for g in away_goals:
            lines.append(f"⚽ {g['scorer']['name']} {_minute(g['minute'])}'")

    lines.append(_hashtags(match))
    return "\n".join(lines)
