"""
transfers.py — Transfer news for the top 5 leagues + MLS
============================================================
Source: ESPN's free /news endpoint, per league — same ESPN family
already used for scores, no scraping, no paid API.

  site.api.espn.com/apis/site/v2/sports/soccer/{league}/news

Headlines are filtered for transfer-signal keywords, then handed back
to bot.py to post immediately (not tied to the 30-min filler clock).
Dedup is the caller's job (bot.py already has a generic "seen keys"
mechanism via state.json — this module just returns candidates).
"""

import requests
import config

ESPN_NEWS_API = "https://site.api.espn.com/apis/site/v2/sports/soccer"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, */*",
}

_TRANSFER_KEYWORDS = (
    "signs", "signing", "sign for", "completes move", "completes transfer",
    "here we go", "joins", "loan move", "loan deal", "on loan",
    "medical", "confirmed transfer", "official transfer", "transfer fee",
    "transfer deal", "unveiled", "new contract", "deal agreed",
    "agrees to join", "set to join", "close to joining",
)


def _get(url: str, timeout: int = 10) -> dict | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        print(f"[TRANSFERS] HTTP {r.status_code}: {url[:90]}")
    except Exception as e:
        print(f"[TRANSFERS] ❌ {e}")
    return None


def _is_transfer_headline(headline: str) -> bool:
    low = headline.lower()
    return any(kw in low for kw in _TRANSFER_KEYWORDS)


def check_new(already_seen: set) -> list[dict]:
    """
    Polls ESPN /news for each configured league, returns transfer-flavored
    items not present in `already_seen` (caller marks them seen after
    successfully posting).
    """
    new_items = []
    for slug, league_name in config.TRANSFER_LEAGUES.items():
        data = _get(f"{ESPN_NEWS_API}/{slug}/news")
        if not data:
            continue
        for article in data.get("articles", []):
            headline = article.get("headline", "")
            if not headline or not _is_transfer_headline(headline):
                continue
            key = f"transfer:{article.get('id', headline)}"
            if key in already_seen:
                continue
            new_items.append({
                "key":      key,
                "headline": headline,
                "league":   league_name,
                "link":     (article.get("links", {}).get("web", {}) or {}).get("href", ""),
                "published": article.get("published", ""),
            })
    return new_items
