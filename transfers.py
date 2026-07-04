"""
transfers.py — Breaking football news, immediate (present/future only)
=========================================================================
Covers everything happening right now, never the past:
  - Transfers (signings, loan moves, deals agreed)
  - Manager news (sackings, resignations, new appointments)
  - World Cup news (retirements, knockouts/eliminations, upcoming
    fixtures, qualification results)
  - Post-match reactions (interviews, press conferences, reactions to
    a result that just happened)

Five free sources, combined and deduped, posted the moment something
new is found — not tied to any filler clock:

  1. ESPN  /news endpoint (per league + World Cup slug) — site.api.espn.com
  2. BBC Sport Football RSS                             — feeds.bbci.co.uk
  3. Sky Sports RSS (mixed feed, URL-filtered to /football/)
  4. The Guardian Football RSS                          — theguardian.com
  5. 90min RSS                                          — 90min.com

All native/free, no scraping libraries, no paid API. RSS is parsed with
the standard library (xml.etree) so no new dependency is needed.

FRESHNESS IS ENFORCED, NOT ASSUMED: every candidate is run through
_is_fresh() (config.TRANSFER_MAX_AGE_HOURS) before it's ever returned.
This is what keeps the page "present going forward" — nothing here
ever surfaces old news, regardless of dedup state.

This module does NOT invent facts, scores, fees, or "reliability
tiers" — a headline is a headline, taken and lightly categorized, never
embellished.
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
GUARDIAN_FOOTBALL_RSS = "https://www.theguardian.com/football/rss"
NINETY_MIN_RSS = "https://www.90min.com/posts.rss"

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
        seg = re.search(r"/(\d{2,4})x(\d{2,4})/", url)
        if seg:
            w, h = int(seg.group(1)), int(seg.group(2))
            if min(w, h) < 500:
                new_w, new_h = _scale_up(w, h)
                return url[:seg.start()] + f"/{new_w}x{new_h}/" + url[seg.end():]
        if "bbci.co.uk" in url:
            m = re.search(r"/(\d{2,4})/", url)
            if m and int(m.group(1)) < 700:
                return url[:m.start(1)] + "976" + url[m.end(1):]
        upgraded = re.sub(r"([?&](?:width|w)=)\d+", r"\g<1>976", url)
        if upgraded != url:
            return upgraded
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
    volume) from replaying an entire morning's stories hours later, and
    what keeps this whole module "present going forward" only.
    Unknown publish time (None) is treated as fresh — we only ever
    suppress on a POSITIVE signal that something is old, never guess
    an article is old just because we couldn't parse its date."""
    if published is None:
        return True
    age_hours = (datetime.now(timezone.utc) - published).total_seconds() / 3600
    return age_hours <= config.TRANSFER_MAX_AGE_HOURS


# ══════════════════════════════════════════════════════════════════
# CATEGORY KEYWORDS — order matters: checked top to bottom, first
# match wins, so a headline that could fit two buckets (rare) lands
# in whichever is listed first.
# ══════════════════════════════════════════════════════════════════

_MANAGER_KEYWORDS = (
    "sacked", "sacks", "sacking", "steps down", "stepped down",
    "resigns", "resignation", "parts ways", "part ways",
    "relieved of", "relieved of his duties", "fired as manager",
    "appointed as", "appoints", "appointed head coach", "new head coach",
    "named manager", "named head coach", "confirmed as manager",
    "takes over as manager", "interim manager", "interim boss",
)

_WORLDCUP_KEYWORDS = (
    "retires from international", "announces international retirement",
    "hangs up his boots", "international retirement",
    "knocked out", "crash out", "crashed out", "eliminated from",
    "exit the world cup", "exit world cup", "dumped out",
    "through to the final", "reach the semi-final", "reach the quarter-final",
    "into the semi-final", "into the quarter-final", "book their place",
    "qualify for the last", "advance to the last", "world cup qualifier",
    "world cup draw", "world cup fixture", "world cup preview",
    "next up in the world cup", "kick off their world cup",
)

_INTERVIEW_KEYWORDS = (
    "reacts to", "speaks after", "post-match press conference",
    "post-match interview", "speaks to media", "press conference:",
    "hails", "blasts", "praises", "on the win", "on the defeat",
    "on the loss", "reaction:", "responds to criticism",
    "full interview", "exclusive interview",
)

_TRANSFER_KEYWORDS = (
    "signs", "signing", "sign for", "completes move", "completes transfer",
    "completes his move", "completes a move", "seals move", "seals a move",
    "here we go", "joins", "loan move", "loan deal", "on loan",
    "medical", "confirmed transfer", "official transfer", "transfer fee",
    "transfer deal", "unveiled", "new contract", "deal agreed",
    "agrees to join", "set to join", "close to joining", "transfer news",
    "rumours", "rumors", "gossip", "move to", "moves to", "switches to",
)

# category -> (keywords, badge/graphics kind, display label used in captions)
_CATEGORIES = (
    ("manager",  _MANAGER_KEYWORDS,  "Manager News"),
    ("worldcup", _WORLDCUP_KEYWORDS, "World Cup News"),
    ("interview", _INTERVIEW_KEYWORDS, "Post-Match Reaction"),
    ("transfer", _TRANSFER_KEYWORDS,  "Transfer News"),
)


def _classify_headline(headline: str) -> tuple:
    """Returns (category_key, label) for the first matching bucket, or
    (None, None) if the headline doesn't fit any tracked category."""
    low = headline.lower()
    for key, keywords, label in _CATEGORIES:
        if any(kw in low for kw in keywords):
            return key, label
    return None, None


def _guess_league(headline: str) -> str:
    low = headline.lower()
    checks = [
        ("world cup", "World Cup"),
        ("premier league", "Premier League"), ("epl", "Premier League"),
        ("la liga", "La Liga"), ("bundesliga", "Bundesliga"),
        ("serie a", "Serie A"), ("ligue 1", "Ligue 1"), ("mls", "MLS"),
    ]
    for kw, name in checks:
        if kw in low:
            return name
    return "Football"


def _get_json(url: str, timeout: int = 10) -> dict | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code == 200:
            return r.json()
        print(f"[NEWS] HTTP {r.status_code}: {url[:90]}")
    except Exception as e:
        print(f"[NEWS] ❌ {e}")
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


def _guardian_image(item) -> str:
    """The Guardian's RSS carries several <media:content medium="image">
    entries per item, each a different width variant (commonly ranging
    from ~140px thumbnails up to 1900px). Picking the first one (like
    _rss_image does for BBC/Sky, which only ever carry one candidate)
    would grab whichever tiny thumbnail happens to be listed first —
    so here we scan all of them and keep the widest, matching the
    "largest available" approach _espn_article_image() already uses
    for ESPN's own multi-size image lists. Falls back to _rss_image()
    (thumbnail/enclosure) if no sized media:content is present."""
    best_url, best_width = "", 0
    for content in item.findall(f"{_MEDIA_NS}content"):
        if (content.get("medium") or "").lower() != "image":
            continue
        url = content.get("url")
        if not url:
            continue
        try:
            width = int(content.get("width") or 0)
        except ValueError:
            width = 0
        if width >= best_width:
            best_width, best_url = width, url
    return best_url or _rss_image(item)


def _get_rss(url: str, timeout: int = 10, image_fn=_rss_image) -> list[dict]:
    """Minimal RSS 2.0 parser via stdlib — returns
    [{title, link, image}, ...]. `image` is "" when the feed doesn't
    carry one for that item. `image_fn` lets a specific feed (e.g.
    Guardian) supply its own image-selection logic; defaults to the
    generic thumbnail/content/enclosure lookup used by BBC/Sky."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            print(f"[NEWS] HTTP {r.status_code}: {url[:90]}")
            return []
        root = ET.fromstring(r.content)
        items = []
        for item in root.iter("item"):
            title = (item.findtext("title") or "").strip()
            link = (item.findtext("link") or "").strip()
            if title:
                items.append({
                    "title": title, "link": link, "image": image_fn(item),
                    "published": _parse_rss_date(item.findtext("pubDate")),
                })
        return items
    except ET.ParseError as e:
        print(f"[NEWS] RSS parse error ({url[:40]}): {e}")
        return []
    except Exception as e:
        print(f"[NEWS] ❌ {e}")
        return []


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
    """Polls every club league in config.TRANSFER_LEAGUES PLUS the
    World Cup slug (config.WORLD_CUP_SLUG) — this is what pulls in
    World Cup knockout results, retirements, and upcoming-fixture
    previews, not just club transfer gossip."""
    items = []
    slugs = dict(config.TRANSFER_LEAGUES)
    slugs[config.WORLD_CUP_SLUG] = "World Cup"

    raw_count = 0
    for slug, league_name in slugs.items():
        data = _get_json(f"{ESPN_NEWS_API}/{slug}/news")
        if not data:
            continue
        for article in data.get("articles", []):
            headline = article.get("headline", "")
            raw_count += 1 if headline else 0
            category, label = _classify_headline(headline) if headline else (None, None)
            if not category:
                continue
            items.append({
                "key":       f"news:{category}:espn:{article.get('id', headline)}",
                "headline":  headline,
                "category":  category,
                "category_label": label,
                "league":    league_name,
                "link":      (article.get("links", {}).get("web", {}) or {}).get("href", ""),
                "image":     _espn_article_image(article),
                "published": _parse_iso(article.get("published") or article.get("lastModified")),
                "source":    "ESPN",
            })
    print(f"[NEWS] ESPN: {raw_count} headlines fetched, {len(items)} matched a category")
    return items


def _bbc_candidates() -> list[dict]:
    items = []
    raw = _get_rss(BBC_FOOTBALL_RSS)
    for entry in raw:
        category, label = _classify_headline(entry["title"])
        if not category:
            continue
        items.append({
            "key":      f"news:{category}:bbc:{entry['link'] or entry['title']}",
            "headline": entry["title"],
            "category": category,
            "category_label": label,
            "league":   _guess_league(entry["title"]),
            "link":     entry["link"],
            "image":    entry.get("image", ""),
            "published": entry.get("published"),
            "source":   "BBC Sport",
        })
    print(f"[NEWS] BBC: {len(raw)} RSS entries fetched, {len(items)} matched a category")
    return items


def _sky_candidates() -> list[dict]:
    items = []
    raw_all = _get_rss(SKY_SPORTS_RSS)
    raw_football = 0
    for entry in raw_all:
        link = entry["link"]
        # Mixed feed (darts/cricket/F1/etc.) — keep football only
        if "/football/" not in link:
            continue
        raw_football += 1
        category, label = _classify_headline(entry["title"])
        if not category:
            continue
        items.append({
            "key":      f"news:{category}:sky:{link or entry['title']}",
            "headline": entry["title"],
            "category": category,
            "category_label": label,
            "league":   _guess_league(entry["title"]),
            "link":     link,
            "image":    entry.get("image", ""),
            "published": entry.get("published"),
            "source":   "Sky Sports",
        })
    print(f"[NEWS] Sky: {len(raw_all)} RSS entries fetched ({raw_football} football), {len(items)} matched a category")
    return items


def _guardian_candidates() -> list[dict]:
    items = []
    # Guardian's feed carries several sized <media:content> variants per
    # item (unlike BBC/Sky's single thumbnail) — _guardian_image picks
    # the widest one so photo cards get the sharpest source image
    # available, same "largest wins" rule ESPN's own image list uses.
    raw = _get_rss(GUARDIAN_FOOTBALL_RSS, image_fn=_guardian_image)
    for entry in raw:
        category, label = _classify_headline(entry["title"])
        if not category:
            continue
        items.append({
            "key":      f"news:{category}:guardian:{entry['link'] or entry['title']}",
            "headline": entry["title"],
            "category": category,
            "category_label": label,
            "league":   _guess_league(entry["title"]),
            "link":     entry["link"],
            "image":    entry.get("image", ""),
            "published": entry.get("published"),
            "source":   "The Guardian",
        })
    print(f"[NEWS] Guardian: {len(raw)} RSS entries fetched, {len(items)} matched a category")
    return items


def _90min_candidates() -> list[dict]:
    items = []
    # 90min is football-only (unlike Sky's mixed feed), so no URL filtering
    # needed — every entry is in-scope, same as BBC/Guardian.
    raw = _get_rss(NINETY_MIN_RSS)
    for entry in raw:
        category, label = _classify_headline(entry["title"])
        if not category:
            continue
        items.append({
            "key":      f"news:{category}:90min:{entry['link'] or entry['title']}",
            "headline": entry["title"],
            "category": category,
            "category_label": label,
            "league":   _guess_league(entry["title"]),
            "link":     entry["link"],
            "image":    entry.get("image", ""),
            "published": entry.get("published"),
            "source":   "90min",
        })
    print(f"[NEWS] 90min: {len(raw)} RSS entries fetched, {len(items)} matched a category")
    return items


def check_new(already_seen: set) -> list[dict]:
    """
    Polls all three sources, returns news items (transfers, manager
    news, World Cup news, post-match reactions) not present in
    `already_seen` (caller marks them seen after successfully
    posting). Combined and deduped by key across sources. Anything
    older than config.TRANSFER_MAX_AGE_HOURS is dropped regardless of
    dedup state — this module never surfaces the past.
    """
    candidates = []
    per_source_counts = {}
    for fn in (_espn_candidates, _bbc_candidates, _sky_candidates, _guardian_candidates, _90min_candidates):
        try:
            result = fn()
            per_source_counts[fn.__name__] = len(result)
            candidates.extend(result)
        except Exception as e:
            per_source_counts[fn.__name__] = f"FAILED: {e}"
            print(f"[NEWS] ⚠️  {fn.__name__} failed: {e}")

    dedup_skipped, stale_skipped = 0, 0
    stale_ages = []
    new_items, seen_this_pass = [], set()
    for item in candidates:
        if item["key"] in already_seen or item["key"] in seen_this_pass:
            dedup_skipped += 1
            continue
        if not _is_fresh(item.get("published")):
            stale_skipped += 1
            pub = item.get("published")
            if pub is not None:
                age_h = round((datetime.now(timezone.utc) - pub).total_seconds() / 3600, 1)
                stale_ages.append(f"{item['source']}/{item['category']}:{age_h}h")
            else:
                stale_ages.append(f"{item['source']}/{item['category']}:UNPARSEABLE")
            continue  # too old to post as "breaking" regardless of dedup state
        seen_this_pass.add(item["key"])
        new_items.append(item)

    print(
        f"[NEWS] poll summary: candidates_by_source={per_source_counts} "
        f"total_candidates={len(candidates)} already_seen_skipped={dedup_skipped} "
        f"stale_skipped={stale_skipped} new_items={len(new_items)}"
    )
    if stale_ages:
        print(f"[NEWS] stale item ages: {stale_ages}")
    return new_items
