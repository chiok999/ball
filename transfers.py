"""
transfers.py — Multi-source Transfer Engine for top 5 leagues + MLS
====================================================================
Sources:
  1. ESPN API /news routes
  2. Sky Sports & Football Transfers RSS feeds
Features automated image extraction for rich Facebook Photo layouts.
"""

import requests
import xml.etree.ElementTree as ET
import config

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    "Accept": "application/json, application/xml, */*",
}

_TRANSFER_KEYWORDS = (
    "signs", "signing", "sign for", "completes move", "completes transfer",
    "here we go", "joins", "loan move", "loan deal", "on loan",
    "medical", "confirmed transfer", "official transfer", "transfer fee",
    "transfer deal", "unveiled", "new contract", "deal agreed",
    "agrees to join", "set to join", "close to joining", "bid accepted",
    "agrees terms", "medical scheduled", "transfer market"
)

RSS_FEEDS = [
    "https://www.skysports.com/rss/12040",
    "https://www.footballtransfers.com/en-GB/transfer-news/actions/rss"
]

def _get_json(url: str) -> dict | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=10)
        if r.status_code == 200: 
            return r.json()
    except Exception as e:
        print(f"[TRANSFERS API] ❌ JSON Error: {e}")
    return None

def _is_transfer_headline(headline: str) -> bool:
    low = headline.lower()
    return any(kw in low for kw in _TRANSFER_KEYWORDS)

def _detect_league_from_text(text: str) -> str | None:
    """Matches RSS items only to the 6 allowed leagues, returning category or None."""
    low = text.lower()
    
    is_epl = any(x in low for x in ["premier league", "epl", "arsenal", "chelsea", "manchester", "man city", "liverpool", "tottenham", "spurs", "newcastle", "aston villa", "west ham"])
    if is_epl: return "Premier League"
    
    is_laliga = any(x in low for x in ["la liga", "barcelona", "real madrid", "atletico", "sevilla", "valencia", "betis", "fati", "gavi", "yamal"])
    if is_laliga: return "La Liga"
    
    is_bundesliga = any(x in low for x in ["bundesliga", "bayern", "dortmund", "bvb", "leverkusen", "leipzig", "saibari"])
    if is_bundesliga: return "Bundesliga"
    
    is_seriea = any(x in low for x in ["serie a", "milan", "juventus", "inter milan", "napoli", "roma", "lazio"])
    if is_seriea: return "Serie A"
    
    is_ligue1 = any(x in low for x in ["ligue 1", "psg", "monaco", "marseille", "lyon", "nice", "lille"])
    if is_ligue1: return "Ligue 1"
    
    is_mls = any(x in low for x in ["mls", "major league soccer", "inter miami", "la galaxy", "lewandowski", "messi"])
    if is_mls: return "MLS"
    
    return None

def check_new(already_seen: set) -> list[dict]:
    new_items = []
    
    # ── SOURCE 1: ESPN NEWS ENDPOINTS ───────────────────
    for slug, league_name in config.TRANSFER_LEAGUES.items():
        data = _get_json(f"https://site.api.espn.com/apis/site/v2/sports/soccer/{slug}/news")
        if not data:
            continue
        for article in data.get("articles", []):
            headline = article.get("headline", "")
            if not headline or not _is_transfer_headline(headline):
                continue
                
            key = f"transfer:{article.get('id', headline)}"
            if key in already_seen:
                continue
                
            image_url = None
            if article.get("images"):
                image_url = article["images"][0].get("url")
                
            new_items.append({
                "key":      key,
                "headline": headline,
                "league":   league_name,
                "link":     article.get("links", {}).get("web", {}).get("href", ""),
                "image_url": image_url
            })

    # ── SOURCE 2: LIVE RSS STREAMS ────────────────────────
    for feed_url in RSS_FEEDS:
        try:
            r = requests.get(feed_url, headers=HEADERS, timeout=10)
            if r.status_code != 200: 
                continue
            root = ET.fromstring(r.content)
            for item in root.findall(".//item"):
                title = item.find("title").text if item.find("title") is not None else ""
                if not title or not _is_transfer_headline(title):
                    continue
                    
                detected_league = _detect_league_from_text(title)
                if not detected_league:
                    continue  # Strict filtering: skip transfers unrelated to your 6 leagues
                    
                link = item.find("link").text if item.find("link") is not None else ""
                key = f"rss:{link or title}"
                if key in already_seen:
                    continue
                    
                image_url = None
                enclosure = item.find("enclosure")
                if enclosure is not None:
                    image_url = enclosure.attrib.get("url")
                
                if not image_url:
                    media_content = item.find("{http://search.yahoo.com/mrss/}content")
                    if media_content is not None:
                        image_url = media_content.attrib.get("url")

                new_items.append({
                    "key": key,
                    "headline": title,
                    "league": detected_league,
                    "link": link,
                    "image_url": image_url
                })
        except Exception as e:
            print(f"[TRANSFERS RSS] Error parsing feed {feed_url[:40]}: {e}")

    return new_items
