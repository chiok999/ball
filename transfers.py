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
import email.utils
from datetime import datetime, timezone
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


def _scale_up(w: int, h: int, target_min: int = 960) -> tuple:
    """Scales (w, h) up, preserving aspect ratio, until the shorter side
    reaches roughly target_min. Preserving the exact ratio matters for
    CDNs like BBC's ichef "ice" endpoint, which crops to the requested
    WxH rather than just resizing — asking for the wrong ratio would
    warp or badly crop the photo instead of just making it bigger."""
    scale = max(1, round(target_min / max(1, min(w, h))))
    return w * scale, h * scale


def _upgrade_image_url(url: str) -> str:
    """Best-effort attempt to get a bigger image than the feed's default
    thumbnail, by recognizing a few common CDN URL patterns and asking
    for a larger size variant. Falls back to the original URL untouched
    if none of these patterns match — this never invents a URL that
    wasn't derivable from a real pattern, it only asks the same CDN for
    a different size of the same image."""
    if not url:
        return url
    try:
        # WIDTHxHEIGHT baked into a path segment — this is the actual
        # pattern BBC's ichef ("images/ice/144x81/...") and Sky's 365dm
        # CDN ("e0.365dm.com/23/06/320x180/...") both use for their RSS
        # thumbnails. Scaled up preserving aspect ratio (see _scale_up)
        # since these are crop-resize endpoints, not simple resizers.
        seg = re.search(r"/(\d{2,4})x(\d{2,4})/", url)
        if seg:
            w, h = int(seg.group(1)), int(seg.group(2))
            if min(w, h) < 500:
                new_w, new_h = _scale_up(w, h)
                return url[:seg.start()] + f"/{new_w}x{new_h}/" + url[seg.end():]
        # BBC's other ichef shape: a single-number size segment, e.g.
        # ".../ichef.bbci.co.uk/news/240/cpsprodpb/..." or
        # ".../ace/standard/240/...". Restricted to the bbci.co.uk
        # domain specifically — a bare number elsewhere in a URL is too
        # ambiguous (could easily be an ID, not a size) to safely touch.
        if "bbci.co.uk" in url:
            m = re.search(r"/(\d{2,4})/", url)
            if m and int(m.group(1)) < 700:
                return url[:m.start(1)] + "976" + url[m.end(1):]
        # Generic CMS query params: ?width=200 / &w=150
        upgraded = re.sub(r"([?&](?:width|w)=)\d+", r"\g<1>976", url)
        if upgraded != url:
            return upgraded
        # Dimensions baked into the filename itself: name_640x360.jpg
        m2 = re.search(r"_(\d+)x(\d+)(\.\w+)(\?.*)?$", url)
        if m2:
            w, h = int(m2.group(1)), int(m2.group(2))
            if min(w, h) < 500:
                new_w, new_h = _scale_up(w, h)
                return url[:m2.start(1)] + f"{new_w}x{new_h}" + m2.group(3) + (m2.group(4) or "")
    except Exception:
        pass
    return url


def _parse_iso(s: str):
    """Parses an ISO8601 timestamp (ESPN's "published" field). Returns
    an aware UTC datetime, or None if the string is missing/unparseable
    — callers treat None as "age unknown", not "definitely stale"."""
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(timezone.utc)
    except Exception:
        return None


def _parse_rss_date(s: str):
    """Parses an RFC822 <pubDate> (BBC/Sky RSS). Returns an aware UTC
    datetime, or None if missing/unparseable."""
    if not s:
        return None
    try:
        dt = email.utils.parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _is_fresh(published) -> bool:
    """A headline older than config.TRANSFER_MAX_AGE_HOURS is never
    posted as breaking news, independent of dedup state — this is what
    stops a state.json wipe (e.g. a redeploy without a persistent
    volume) from replaying an entire morning's stories hours later.
    Unknown publish time (None) is treated as fresh — we only ever
    suppress on a POSITIVE signal that something is old, never guess
    an article is old just because we couldn't parse its date."""
    if published is None:
        return True
    age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
    return age_hours <= config.TRANSFER_MAX_AGE_HOURS

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
    Returns "" if none is found — caller treats that as no photo. Any
    URL found is run through _upgrade_image_url() to try for a larger
    variant than the feed's default (usually small) thumbnail."""
    thumb = item.find(f"{_MEDIA_NS}thumbnail")
    if thumb is not None and thumb.get("url"):
        return _upgrade_image_url(thumb.get("url"))
    content = item.find(f"{_MEDIA_NS}content")
    if content is not None and content.get("url"):
        return _upgrade_image_url(content.get("url"))
    for enc in item.findall("enclosure"):
        if (enc.get("type") or "").startswith("image") and enc.get("url"):
            return _upgrade_image_url(enc.get("url"))
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
                items.append({
                    "title": title, "link": link, "image": _rss_image(item),
                    "published": _parse_rss_date(item.findtext("pubDate")),
                })
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
    """ESPN news articles typically carry an "images" list, often with
    several crops/sizes of the same photo. We want the LARGEST one —
    grabbing whichever came first in the list is how you end up with a
    144x81 thumbnail stretched to fill a 1080x1080 card, which is
    exactly the blurry/pixelated result to avoid. Defensively parsed —
    any shape mismatch just returns "" and the caller falls back to a
    generated card rather than crashing."""
    images = article.get("images") or []
    best_url, best_area = "", 0
    for im in images:
        url = im.get("url")
        if not url:
            continue
        area = (im.get("width") or 0) * (im.get("height") or 0)
        if area >= best_area:
            best_area, best_url = area, url
    return best_url


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
                "published": _parse_iso(article.get("published") or article.get("lastModified")),
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
            "published": entry.get("published"),
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
            "published": entry.get("published"),
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
        if not _is_fresh(item.get("published")):
            continue  # too old to post as "breaking" regardless of dedup state
        seen_this_pass.add(item["key"])
        new_items.append(item)
    return new_items
