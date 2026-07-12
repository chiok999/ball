"""
poster.py — Facebook posting + message formatters
===================================================
Post formats:

  Lineup (FD only):
    📋 LINEUPS | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
    🏟️ Arsenal vs Chelsea
    Arsenal (4-3-3): Raya, White, Saliba...
    Chelsea (4-2-3-1): Sanchez, James...
    #Arsenal #Chelsea #PL #MatchCornaLive

  Kickoff:
    🟢 KICKOFF | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
    🏟️ Arsenal 0 - 0 Chelsea
    #Arsenal #Chelsea #PL #MatchCornaLive

  Goal:
    ⚽ GOAL | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
    🏟️ Arsenal 2 - 1 Chelsea
    Saka ⚽ 67'
    🎯 Odegaard (assist, when available)
    #Arsenal #Chelsea #PL #MatchCornaLive

  Extra Time:
    ⏱️ EXTRA TIME | 🏆 Champions League
    🏟️ Arsenal 1 - 1 Real Madrid
    #Arsenal #RealMadrid #UCL #MatchCornaLive

  Full Time:
    🏁 FULL TIME | 🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League
    🏟️ Arsenal 3 - 1 Chelsea
    Arsenal
    ⚽ Saka 12'  ⚽ Havertz 45'  ⚽ Trossard 89'
    Chelsea
    ⚽ Sterling 34'
    #Arsenal #Chelsea #PL #MatchCornaLive
"""

import time
import re
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
    return f"#{h} #{a} {comp} #MatchCornaLive"


def _comp_header(match: dict) -> str:
    flag = match.get("_comp_flag", "⚽")
    name = match.get("_comp_name", "Football")
    return f"{flag} {name}"


# ══════════════════════════════════════════════════════════════════
# SHARED SCREENSHOT-STYLE FORMATTER
# ══════════════════════════════════════════════════════════════════
# 🚩 {Header}
#
# {body lines}
#
# Source: {source}      ← only for stats-style posts (omitted for match events)
# #tag1 #tag2 #tag3

def _build_post(header: str, body: list[str], hashtags: list[str], source: str | None = None, marker: str = "🚩") -> str:
    lines = [f"{marker} {header}"]
    if body:
        lines.append("")
        lines.extend(body)
    if source:
        lines.append("")
        lines.append(f"Source: {source}")
    lines.append("")
    lines.append(" ".join(f"#{t}" if not t.startswith('#') else t for t in hashtags[:3]))
    return "\n".join(lines)


def _match_hashtags(match: dict) -> list[str]:
    """Exactly 3 tags: World Cup gets #WorldCup2026, others get their comp tag."""
    home = match["homeTeam"]["name"].replace(" ", "")
    away = match["awayTeam"]["name"].replace(" ", "")
    if match.get("_is_world_cup"):
        return ["WorldCup2026", home, away]
    comp = _comp_tag(match.get("_comp_name", "")).lstrip("#")
    return [comp, home, away]


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
            "#MatchCornaLive"
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

    lines.append("#MatchCornaLive")
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


def _plain_score_line(match: dict, home_sc, away_sc) -> str:
    """Plain team names + tight score, matching the screenshot style
    (no per-team flags in the header line — flags are used in ranked lists)."""
    h = match["homeTeam"]["name"]
    a = match["awayTeam"]["name"]
    return f"{h} {home_sc}-{away_sc} {a}"


def fmt_kickoff(match: dict) -> str:
    header = f"Live: {_plain_score_line(match, 0, 0)} — Kickoff!"
    return _build_post(header, [], _match_hashtags(match))


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

    header = f"Live: {_plain_score_line(match, h_sc, a_sc)}"
    body = [f"⚽ Goal: {scorer} ({minute}')"]
    assist = goal.get("assist", {}).get("name")
    if assist:
        body.append(f"🎯 Assist: {assist}")

    return _build_post(header, body, _match_hashtags(match))


def fmt_extratime(match: dict) -> str:
    return "\n".join([
        f"⏱️ EXTRA TIME | {_comp_header(match)}",
        _final_scoreline(match),
        _hashtags(match),
    ])


def fmt_halftime(match: dict) -> str:
    """
    Half Time: Arsenal 1-0 Chelsea
    ⚽ Arsenal: Saka 34' (assist: Odegaard)
    #Arsenal #Chelsea #PL #MatchCornaLive
    """
    header = f"Half Time: {_plain_score_line(match, *_current_score(match))}"
    body = []

    home_goals = [g for g in match.get("goals", []) if     g["isHome"]]
    away_goals = [g for g in match.get("goals", []) if not g["isHome"]]

    def _goal_line(g: dict) -> str:
        line = f"{g['scorer']['name']} {_minute(g['minute'])}'"
        assist = g.get("assist", {}).get("name")
        if assist:
            line += f" (assist: {assist})"
        return line

    if home_goals:
        body.append(f"⚽ {match['homeTeam']['name']}: " + ", ".join(_goal_line(g) for g in home_goals))
    if away_goals:
        body.append(f"⚽ {match['awayTeam']['name']}: " + ", ".join(_goal_line(g) for g in away_goals))
    if not body:
        body.append("No goals yet")

    return _build_post(header, body, _match_hashtags(match), marker="⏸️")


def fmt_redcard(match: dict, booking: dict) -> str:
    """
    Live: Arsenal 1-0 Chelsea
    🟥 Mbappe 60'
    #Arsenal #Chelsea #PL #MatchCornaLive
    """
    header = f"Live: {_plain_score_line(match, *_current_score(match))}"
    player = booking.get("player", {}).get("name", "Unknown")
    minute = _minute(booking.get("minute", "?"))
    body = [f"🟥 {player} {minute}'"]
    return _build_post(header, body, _match_hashtags(match), marker="🟥")


# ══════════════════════════════════════════════════════════════════
# NON-MATCHDAY CONTENT FORMATTERS (World Cup filler + upcoming fixtures)
# ══════════════════════════════════════════════════════════════════

def fmt_top_scorers(scorers: list, country_of: dict | None = None) -> str:
    """
    🚩 World Cup Top Scorers:

    🇦🇷 1. L. Messi - 6
    🇫🇷 2. Mbappe - 6
    🇳🇴 3. Haaland - 5

    Source: FIFA
    #WorldCup2026 #GoldenBoot #Football

    `country_of` optionally maps player name -> country name for the flag.
    """
    country_of = country_of or {}
    body = []
    for s in scorers[:5]:
        flag = team_flag(country_of.get(s["player"], s.get("team", "")))
        flag_prefix = f"{flag} " if flag else ""
        body.append(f"{flag_prefix}{s['rank']}. {s['player']} - {s['goals']}")

    return _build_post(
        "World Cup Top Scorers:", body,
        ["WorldCup2026", "GoldenBoot", "Football"],
        source="FIFA",
    )



# ══════════════════════════════════════════════════════════════════
# HEADLINE SIMPLIFICATION — best-effort plain-English pass
# ══════════════════════════════════════════════════════════════════
# Source headlines (ESPN/BBC/Guardian/90min) are written for native
# English-speaking readers and often pack a lot into one dense
# sentence. This is a rule-based pass, NOT full rewriting — genuinely
# simplifying a complex sentence needs an LLM step, which this project
# intentionally doesn't use (README: "100% free — no paid APIs"). If
# headlines still read hard after this, a small paid rewrite call is
# the real next step to consider, not piling on more regex here.

# Safe, unambiguous whole-phrase swaps only — nothing that risks
# mangling grammar. Checked case-insensitively.
_HEADLINE_SIMPLIFICATIONS = [
    (r"\bwould prefer to join\b",                 "wants to join"),
    (r"\bclose to agreeing a deal to sign\b",      "close to signing"),
    (r"\bunprofessional\b",                        "rude"),
    (r"\brelieved of (?:his|her|their) duties\b",  "sacked"),
    (r"\ban? enquiry\b",                           "an approach"),
    (r"\bconfirmed as\b",                          "named as"),
    (r"\bpersonal terms\b",                        "personal contract details"),
    (r"\bhighly[- ]rated\b",                       "highly rated"),
]


def _strip_trailing_attribution(text: str) -> str:
    """Drops wire-style trailing attribution clutter like
    ' - Agent Basia Michaels' that adds no meaning for someone
    scanning a Facebook caption."""
    return re.sub(r"\s-\s(?:Agent|Source|Via)\s+[^-]+$", "", text, flags=re.I).strip()


def _soft_wrap(text: str, max_len: int = 90) -> str:
    """A long, dense headline gets broken onto a second line at the
    comma/semicolon nearest the midpoint — same words, easier to scan
    on a phone feed. Never splits mid-word, never makes more than 2
    lines, and leaves short headlines untouched."""
    if len(text) <= max_len:
        return text
    mid = len(text) // 2
    candidates = [m.start() for m in re.finditer(r",\s|;\s", text)]
    if not candidates:
        return text
    split_at = min(candidates, key=lambda i: abs(i - mid))
    return text[:split_at + 1].rstrip(",; ") + "\n" + text[split_at + 1:].strip()


def simplify_headline(text: str) -> str:
    """Strip wire clutter, swap a short list of harder words/phrases
    for simpler equivalents, then soft-wrap if still a long run-on."""
    result = _strip_trailing_attribution(text)
    for pattern, replacement in _HEADLINE_SIMPLIFICATIONS:
        result = re.sub(pattern, replacement, result, flags=re.I)
    return _soft_wrap(result)


def _strip_urls(text: str) -> str:
    """Defensive — headlines shouldn't contain URLs, but strip any if present."""
    return re.sub(r'https?://\S+', '', text).strip()


# category -> (header, marker, primary hashtag). Used by fmt_football_news
# so every news flavor gets its own header/marker instead of everything
# reading as generic "BREAKING NEWS".
_NEWS_CATEGORY_STYLE = {
    "player_transfer":  ("TRANSFER NEWS",         "🚨", "TransferNews"),
    "manager_sacking":  ("MANAGER SACKING",       "🔴", "ManagerSacking"),
    "manager_transfer": ("MANAGER NEWS",          "📋", "ManagerNews"),
    "deal_done":        ("DEAL DONE",             "✅", "DealDone"),
    "gossip":           ("GOSSIP",                "🗣️", "Gossip"),
    "worldcup":         ("WORLD CUP NEWS",        "🌍", "WorldCup2026"),
    "player_quote":     ("PLAYER SPOTLIGHT",      "🎙️", "PlayerSpotlight"),
    "injury":           ("INJURY NEWS",           "🩹", "InjuryNews"),
}


# One-sentence framing per category, used only when the source feed
# gave no usable <description> teaser (see _clean_description below).
# Deliberately generic/non-fabricated — an honest framing line built
# from data we actually have (category, league), NOT an invented fact
# about the story.
_STORY_CONTEXT = {
    "player_transfer":  "This is a developing transfer story in the {league} — expect more twists as talks continue.",
    "manager_sacking":  "A big change in the {league} dugout. We'll bring you the next update as soon as more is confirmed.",
    "manager_transfer": "A new man in the {league} hot seat — follow along as the appointment takes shape.",
    "deal_done":        "It's official — here's the latest confirmed move in the {league}.",
    "gossip":           "Just talk for now in the {league} — nothing confirmed yet, but worth keeping an eye on.",
    "worldcup":         "A big World Cup moment — follow along for how this shapes the tournament picture.",
    "player_quote":     "Straight from the player himself — more reaction as this story develops.",
    "injury":           "An injury update from the {league} — we'll follow up as more details on recovery time emerge.",
}


def _clean_description(desc: str, headline: str) -> str:
    """Turns a raw RSS/ESPN <description> field into a short, clean
    teaser sentence for the caption: strips HTML tags/entities,
    collapses whitespace, caps length so it stays a genuine "teaser"
    rather than a full reproduced paragraph, and drops it entirely if
    it's just a restatement of the headline (common on some feeds)."""
    if not desc:
        return ""
    desc = re.sub(r"<[^>]+>", " ", desc)
    desc = re.sub(r"&[a-zA-Z#0-9]+;", " ", desc)
    desc = re.sub(r"\s+", " ", desc).strip()
    if not desc:
        return ""
    if len(desc) > 220:
        desc = desc[:217].rsplit(" ", 1)[0] + "..."
    if desc.lower() in headline.lower() or headline.lower() in desc.lower():
        return ""
    return desc


def fmt_football_news(item: dict) -> str:
    """
    Present/future football news only — manager sackings, manager
    transfers/appointments, World Cup retirements/knockouts/upcoming
    fixtures, confirmed ("deal done") transfers, in-progress player
    transfers, and gossip/speculation. Header, marker, and primary
    hashtag adapt to item["category"] so each flavor reads distinctly
    on the page.

    Uses the source feed's own <description>/shortDescription teaser
    (item["description"]) for a short natural-language summary line
    under the headline, instead of just repeating the headline. Falls
    back to a generic one-line framing sentence when the feed gave no
    usable teaser (missing, empty, or just a restatement of the
    headline) — this must never leave the caption looking broken just
    because a particular feed item had no description.
    """
    category = item.get("category", "player_transfer")
    header, marker, primary_tag = _NEWS_CATEGORY_STYLE.get(
        category, _NEWS_CATEGORY_STYLE["player_transfer"]
    )
    headline = simplify_headline(_strip_urls(item.get("headline") or item.get("title", "")))
    desc = _clean_description(item.get("description", ""), headline)
    if desc:
        body = [headline, "", desc]
    else:
        context = _STORY_CONTEXT.get(category, _STORY_CONTEXT["player_transfer"]).format(
            league=item.get("league") or "football"
        )
        body = [headline, "", context]
    league_tag = item["league"].replace(" ", "")
    return _build_post(
        header, body,
        [primary_tag, league_tag, "Football"],
        source=item.get("source", "ESPN"),
        marker=marker,
    )


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

    lines.append("\n#MatchCornaLive")
    return "\n".join(lines)


def scorers_line(match: dict, side: str | None = None) -> str:
    """Compact 'Player 27'\\nPlayer 61'' string of goals in the match,
    sorted by minute — for embedding directly on the scoreboard card
    image (graphics.render_scoreboard_card's home_event_line/
    away_event_line params), separate from the fuller per-team
    breakdown fmt_fulltime() uses in the post caption itself.

    `side` optionally filters to just "home" or "away" goals, so the
    card can draw each team's scorers under that team's own crest
    instead of one combined line down the center. Lines are newline-
    joined (not space-joined) so multiple scorers on the same side
    stack vertically under a narrower per-crest column."""
    def _sort_key(g: dict):
        try:
            return int(_minute(g["minute"]))
        except (TypeError, ValueError):
            return 0
    goals = match.get("goals", [])
    if side == "home":
        goals = [g for g in goals if g["isHome"]]
    elif side == "away":
        goals = [g for g in goals if not g["isHome"]]
    goals = sorted(goals, key=_sort_key)
    return "\n".join(f"{g['scorer']['name']} {_minute(g['minute'])}'" for g in goals)


def fmt_fulltime(match: dict) -> str:
    prefix = "Full Time"
    if match.get("_went_to_penalties"):
        prefix = "Full Time (Penalties)"
    elif match.get("_went_to_et"):
        prefix = "Full Time (AET)"

    header = f"{prefix}: {_plain_score_line(match, *_current_score(match))}"
    body = []

    if match.get("_went_to_penalties"):
        ph, pa = match.get("_penalty_home"), match.get("_penalty_away")
        if ph is not None and pa is not None:
            winner = match["homeTeam"]["name"] if ph > pa else match["awayTeam"]["name"]
            body.append(f"🏆 {winner} win {ph}-{pa} on penalties")
            body.append("")

    home_goals = [g for g in match.get("goals", []) if     g["isHome"]]
    away_goals = [g for g in match.get("goals", []) if not g["isHome"]]

    def _goal_line(g: dict) -> str:
        line = f"{g['scorer']['name']} {_minute(g['minute'])}'"
        assist = g.get("assist", {}).get("name")
        if assist:
            line += f" (assist: {assist})"
        return line

    if home_goals:
        body.append(f"⚽ {match['homeTeam']['name']}: " + ", ".join(_goal_line(g) for g in home_goals))
    if away_goals:
        body.append(f"⚽ {match['awayTeam']['name']}: " + ", ".join(_goal_line(g) for g in away_goals))

    return _build_post(header, body, _match_hashtags(match), marker="🏁")


def fmt_motm(match: dict, motm: dict) -> str:
    """
    🌟 Man of the Match: L. Messi (Argentina)
    Rating: 9.2 | Argentina 3-1 Switzerland

    #Argentina #ManOfTheMatch
    """
    team = match["homeTeam"]["name"] if motm.get("team_side") == "home" else match["awayTeam"]["name"]
    header = f"Man of the Match: {motm['name']} ({team})"
    body = [f"⭐ {_plain_score_line(match, *_current_score(match))}"]
    if motm.get("rating") is not None:
        body.append(f"📊 Rating: {motm['rating']}")

    tags = _match_hashtags(match) + ["ManOfTheMatch"]
    return _build_post(header, body, tags, marker="🌟")


def _current_score(match: dict) -> tuple:
    h = match["score"]["fullTime"].get("home")
    a = match["score"]["fullTime"].get("away")
    return (h if h is not None else 0, a if a is not None else 0)


def fmt_var_disallowed(match: dict, var_event: dict) -> str:
    """
    🚩 No Goal — VAR Review: Germany vs Paraguay

    🚨 Disallowed: J. Tah (105') — Goal Disallowed
    Reason: Foul in the build-up

    #WorldCup2026 #VAR #NoGoal
    """
    header = f"No Goal — VAR Review: {match['homeTeam']['name']} vs {match['awayTeam']['name']}"
    minute = _minute(var_event.get("minute", "?"))
    body = [f"🚨 Disallowed: {var_event['player']} ({minute}') — {var_event.get('team', '')}"]
    reason = var_event.get("reason", "")
    if reason and reason.lower() not in ("var review", ""):
        body.append(f"Reason: {reason}")

    if match.get("_is_world_cup"):
        tags = ["WorldCup2026", "VAR", "NoGoal"]
    else:
        tags = [_comp_tag(match.get("_comp_name", "")).lstrip("#"), "VAR", "NoGoal"]

    return _build_post(header, body, tags, marker="❌")
