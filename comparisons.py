"""
comparisons.py — player vs player comparison content, two flavors:

  1. Generational/legend pairings — pulled from player_stats_verified.json
     entries with "type": "comparison" (see filler.py, which already
     handles these identically to solo legend facts — no extra code
     needed there). These stay hand-verified for the same reason every
     other legend stat does: career/historical facts aren't something a
     live stats API gives you cleanly, and a wrong number here is worse
     than no post at all.

  2. Live current-season pairings — THIS module. Fetches both players'
     stats for the current season from API-Football and builds a caption
     from a rotating set of phrasing templates (not one fixed sentence
     every time — that's the fastest way for regular followers to
     notice "this is a bot").

PAIRS is a curated, position-aware seed list — deliberately not an
all-vs-all random combination of every name in ROSTER, because a
goalkeeper vs a striker isn't an interesting comparison no matter how
famous either one is. NOTE: player rosters drift (transfers, injuries,
retirements) — this list reflects a snapshot and should be refreshed
periodically, the same way you'd expect any football content account to
update its talking points as the season moves on.
"""
import random

import stats_api

# Curated, position-aware pairings spanning the Premier League, La Liga,
# Serie A, Bundesliga and Ligue 1 (Champions League is a cup competition
# overlaid on those leagues, not a separate squad list, so it's not used
# for player-vs-player pairing — only for team-level content).
# Format: (player_a, player_b, flavor_label)
PAIRS = [
    ("Erling Haaland",      "Kylian Mbappé",     "striker rivalry"),
    ("Mohamed Salah",       "Vinicius Junior",   "winger rivalry"),
    ("Bukayo Saka",         "Lamine Yamal",      "young winger — next generation"),
    ("Jude Bellingham",     "Jamal Musiala",     "creative midfield rivalry"),
    ("Robert Lewandowski",  "Harry Kane",        "veteran striker rivalry"),
    ("Cole Palmer",         "Florian Wirtz",     "young playmaker rivalry"),
    ("Lautaro Martínez",    "Victor Osimhen",    "Serie A striker rivalry"),
]

_TEMPLATES = [
    "📊 This season: {a_name} — {a_goals}⚽ {a_assists}🎯 in {a_apps} apps. "
    "{b_name} — {b_goals}⚽ {b_assists}🎯 in {b_apps} apps. Who's had the better campaign?",

    "{a_name} ({a_team}) vs {b_name} ({b_team}) — {a_goals} goals vs {b_goals} goals so far this season. "
    "Numbers don't lie... or do they? 🤔",

    "Form check 👀\n{a_name}: {a_goals}⚽ / {a_assists}🎯\n{b_name}: {b_goals}⚽ / {b_assists}🎯\n"
    "Which one are you starting in a cup final?",

    "{a_name} vs {b_name}, {flavor} edition. This season's numbers: "
    "{a_goals}-{b_goals} on goals, {a_assists}-{b_assists} on assists. Settle it in the comments. ⚔️",

    "Real talk — between {a_name} and {b_name} this season, who's actually been better? "
    "{a_goals}⚽{a_assists}🎯 vs {b_goals}⚽{b_assists}🎯. No wrong answers, only strong opinions. 🔥",
]


def _fetch(name: str) -> dict | None:
    return stats_api.search_player_stats(name)


def build_live_comparison_pool(used: dict, cooldown_hours: float, is_eligible_fn) -> list[tuple[str, dict]]:
    """Returns eligible (content_id, payload) candidates — one per curated
    pair not currently on cooldown. `is_eligible_fn` is filler.py's own
    cooldown check, passed in so this module doesn't need to duplicate
    that logic or reach into filler.py's internals."""
    if not stats_api_key_available():
        return []
    out = []
    for a_name, b_name, flavor in PAIRS:
        content_id = f"live_compare:{a_name}_vs_{b_name}"
        if not is_eligible_fn(content_id, cooldown_hours, used):
            continue
        a = _fetch(a_name)
        b = _fetch(b_name)
        if not a or not b:
            continue  # one or both not found this season (transfer, injury, name drift) — skip, don't guess
        out.append((content_id, {"a": a, "b": b, "flavor": flavor}))
    return out


def stats_api_key_available() -> bool:
    import config
    return bool(config.API_FOOTBALL_KEY)


def render_live_comparison(payload: dict) -> str:
    a, b, flavor = payload["a"], payload["b"], payload["flavor"]
    template = random.choice(_TEMPLATES)
    return template.format(
        a_name=a["name"], b_name=b["name"],
        a_team=a["team"], b_team=b["team"],
        a_goals=a["goals"], a_assists=a["assists"], a_apps=a["appearances"],
        b_goals=b["goals"], b_assists=b["assists"], b_apps=b["appearances"],
        flavor=flavor,
    )
