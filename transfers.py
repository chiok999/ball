"""
transfers.py — Breaking transfer news, immediate (top 5 leagues + MLS)
=========================================================================
Three free sources, combined and deduped, posted the moment something
new is found — not tied to any filler clock:

  1. ESPN  /news endpoint (per league)      — site.api.espn.com
  2. BBC Sport Football RSS                 — feeds.bbci.co.uk
  3. Sky Sports RSS (mixed feed, URL-filtered to /football/)

All native/free, no scraping libraries, no paid API. RSS is parsed with
the standard library (xml.etree) so no new dependency is needed.

This module does NOT invent transfer fees, "reliability tiers", or any
other data it doesn't actually have — a headline is a headline. Real
historical fee data (when useful) comes separately from transfermarkt.py.
"""

import re
import requests
import xml.etree.ElementTree as ET
import config

ESPN_NEWS_API = "https://site.api.espn.com/apis/site/v2/sports/soccer"
BBC_FOOTBALL_RSS = "https://feeds.bbci.co.uk/sport/football/rss.xml"
SKY_SPORTS_RSS = "https://www.skysports.com/rss/12040"  # mixed feed — filtered to /football/ below

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, text/xml, */*",
}

_TRANSFER_KEYWORDS = (
    "signs", "signing", "sign for", "completes move", "completes transfer",
    "here we go", "joins", "loan move", "loan deal", "on loan",
    "medical", "confirmed transfer", "official transfer", "transfer fee",
    "transfer deal", "unveiled", "new contract", "deal agreed",
    "agrees to join", "set to join", "close to joining", "transfer news",
    "rumours", "rumors", "gossip",
)


def _get_json(url: str, timeout: int = 10) -> dict | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        print(f"[TRANSFERS] HTTP {r.status_code}: {url[:90]}")
    except Exception as e:
        print(f"[TRANSFERS] ❌ {e}")
    return None


_MEDIA_NS = "{http://search.yahoo.com/mrss/}"


def _rss_image(item) -> str:
    """Pulls an article image out of an RSS <item> if one is present.
    BBC/Sky both commonly carry one of: <media:thumbnail url="...">,
    <media:content url="...">, or <enclosure url="..." type="image/*">.
    Returns "" if none is found — caller treats that as no photo."""
    thumb = item.find(f"{_MEDIA_NS}thumbnail")
    if thumb is not None and thumb.get("url"):
        return thumb.get("url")
    content = item.find(f"{_MEDIA_NS}content")
    if content is not None and content.get("url"):
        return content.get("url")
    for enc in item.findall("enclosure"):
        if (enc.get("type") or "").startswith("image") and enc.get("url"):
            return enc.get("url")
    return ""


def _get_rss(url: str, timeout: int = 10) -> list[dict]:
    """Minimal RSS 2.0 parser via stdlib — returns
    [{title, link, image}, ...]. `image` is "" when the feed doesn't
    carry one for that item."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            print(f"[TRANSFERS] HTTP {r.status_code}: {url[:90]}")
            return []
        root = ET.fromstring(r.content)
        items = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title:
                items.append({"title": title, "link": link, "image": _rss_image(item)})
        return items
    except ET.ParseError as e:
        print(f"[TRANSFERS] RSS parse error ({url[:40]}): {e}")
        return []
    except Exception as e:
        print(f"[TRANSFERS] ❌ {e}")
        return []


def _is_transfer_headline(headline: str) -> bool:
    low = headline.lower()
    return any(kw in low for kw in _TRANSFER_KEYWORDS)


def _guess_league(headline: str) -> str:
    low = headline.lower()
    checks = [
        ("premier league", "Premier League"), ("epl", "Premier League"),
        ("la liga", "La Liga"), ("bundesliga", "Bundesliga"),
        ("serie a", "Serie A"), ("ligue 1", "Ligue 1"), ("mls", "MLS"),
    ]
    for kw, name in checks:
        if kw in low:
            return name
    return "Football"


def _espn_article_image(article: dict) -> str:
    """ESPN news articles typically carry an "images" list, each with
    a "url" (and sometimes multiple crops/sizes). Defensively parsed —
    any shape mismatch just returns "" and the caller falls back to a
    generated card rather than crashing."""
    images = article.get("images") or []
    for im in images:
        url = im.get("url")
        if url:
            return url
    return ""


def _espn_candidates() -> list[dict]:
    items = []
    for slug, league_name in config.TRANSFER_LEAGUES.items():
        data = _get_json(f"{ESPN_NEWS_API}/{slug}/news")
        if not data:
            continue
        for article in data.get("articles", []):
            headline = article.get("headline", "")
            if not headline or not _is_transfer_headline(headline):
                continue
            items.append({
                "key":       f"transfer:espn:{article.get('id', headline)}",
                "headline":  headline,
                "league":    league_name,
                "link":      (article.get("links", {}).get("web", {}) or {}).get("href", ""),
                "image":     _espn_article_image(article),
                "source":    "ESPN",
            })
    return items


def _bbc_candidates() -> list[dict]:
    items = []
    for entry in _get_rss(BBC_FOOTBALL_RSS):
        if not _is_transfer_headline(entry["title"]):
            continue
        items.append({
            "key":      f"transfer:bbc:{entry['link'] or entry['title']}",
            "headline": entry["title"],
            "league":   _guess_league(entry["title"]),
            "link":     entry["link"],
            "image":    entry.get("image", ""),
            "source":   "BBC Sport",
        })
    return items


def _sky_candidates() -> list[dict]:
    items = []
    for entry in _get_rss(SKY_SPORTS_RSS):
        link = entry["link"]
        # Mixed feed (darts/cricket/F1/etc.) — keep football only
        if "/football/" not in link:
            continue
        if not _is_transfer_headline(entry["title"]):
            continue
        items.append({
            "key":      f"transfer:sky:{link or entry['title']}",
            "headline": entry["title"],
            "league":   _guess_league(entry["title"]),
            "link":     link,
            "image":    entry.get("image", ""),
            "source":   "Sky Sports",
        })
    return items


def check_new(already_seen: set) -> list[dict]:
    """
    Polls all three sources, returns transfer-flavored items not present
    in `already_seen` (caller marks them seen after successfully posting).
    Combined and deduped by key across sources.
    """
    candidates = []
    for fn in (_espn_candidates, _bbc_candidates, _sky_candidates):
        try:
            candidates.extend(fn())
        except Exception as e:
            print(f"[TRANSFERS] ⚠️  {fn.__name__} failed: {e}")

    new_items, seen_this_pass = [], set()
    for item in candidates:
        if item["key"] in already_seen or item["key"] in seen_this_pass:
            continue
        seen_this_pass.add(item["key"])
        new_items.append(item)
    return new_items
