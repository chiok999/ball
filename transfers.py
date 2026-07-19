"""
transfers.py — Breaking football news, immediate (present/future only)
=========================================================================
Six tracked categories, each checked in this order (first match wins):
  1. Manager sacking   — sackings, resignations, "parts ways"
  2. Manager transfer  — new appointments, unveilings, interim bosses
  3. Injury            — sidelined/ruled-out/surgery/return-date stories
  4. Deal done         — signings/moves that are CONFIRMED/official only
  5. Deal collapsed    — a move that fell through / is off / collapsed

Transfer news is CONFIRMED-ONLY: no gossip, no rumours, no in-progress
speculation. A headline that's just "linked with"/"wants to sign"/
"interested in" matches no category here and is silently dropped.

Four free sources, combined and deduped, posted the moment something
new is found:

  1. ESPN  /news endpoint (per league)                  — site.api.espn.com
  2. BBC Sport Football RSS                             — feeds.bbci.co.uk
  3. Sky Sports RSS (mixed feed, URL-filtered to /football/)
  4. 90min RSS                                          — 90min.com

All native/free, no scraping libraries, no paid API. RSS is parsed with
the standard library (xml.etree) so no new dependency is needed.

FRESHNESS IS ENFORCED, NOT ASSUMED: every candidate is run through
_is_fresh() (config.TRANSFER_MAX_AGE_HOURS) before it's ever returned.
This is what keeps the page "present going forward" — nothing here
ever surfaces old news, regardless of dedup state.

Every candidate also carries a "description" field (the RSS
<description>/ESPN shortDescription — a short teaser sentence or two,
distinct from the headline) so poster.fmt_football_news() can build a
caption that reads as more than just the headline repeated. This
module does NOT invent facts, scores, fees, or "reliability tiers" — a
headline (and its feed-supplied teaser) is taken and lightly
categorized, never embellished.
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
# CATEGORY PATTERNS — order matters: checked top to bottom, first
# match wins, so a headline that could fit two buckets (rare) lands
# in whichever is listed first.
#
# NOTE ON WHY THESE ARE REGEX, NOT LITERAL PHRASES:
# Real headlines use every tense and phrasing under the sun —
# "agreeing a deal to sign", "prefer to join" (no "s"), "knock out"
# (present tense, not "knocked"), "extend his contract" (not "new
# contract"). Each pattern below uses \b word-stems with optional
# tense endings (s|ed|ing) so "sign/signs/signing/signed" all match
# from one pattern, same idea for join/agree/reject/extend/etc.
# ══════════════════════════════════════════════════════════════════

_MANAGER_SACKING_PATTERNS = [
    r"\bsack(?:ed|s|ing)?\b", r"\bfired\b",
    r"\bstep(?:s|ped)?\s+down\b", r"\bresign(?:s|ed|ation)?\b",
    r"\bpart(?:s|ed)?\s+ways\b", r"\brelieved\s+of\b",
    r"\bleaves?\s+(?:his|her|their)\s+(?:role|post)\b",
    r"\bout\s+as\s+(?:manager|head\s+coach|boss)\b",
    r"\bsacking\b",
]

_MANAGER_TRANSFER_PATTERNS = [
    r"\b(?:appoint(?:s|ed|ment)?|nam(?:es|ed)|confirm(?:s|ed)?|unveil(?:s|ed)?|hir(?:e|es|ed|ing))\b[^.]{0,25}\b(?:manager|head\s+coach|boss|coach)\b",
    r"\bnew\s+(?:manager|head\s+coach|boss)\b",
    r"\btakes?\s+over\s+as\s+(?:manager|coach|boss)\b",
    r"\btakes?\s+(?:the\s+)?helm\b",
    r"\binterim\s+(?:manager|boss|coach)\b",
    r"\bagrees?\s+to\s+become\b[^.]{0,25}\bmanager\b",
    r"\bset\s+to\s+become\b[^.]{0,25}\b(?:manager|head\s+coach|boss)\b",
]

# "Deal done" — the transfer is CONFIRMED/complete, not just rumoured
# or in progress. Checked before the general player-transfer bucket so
# "Here we go! Player completes move to Club" lands here, not there.
_DEAL_DONE_PATTERNS = [
    r"\bhere\s+we\s+go\b",
    r"\bdone\s+deal\b",
    r"\bofficial(?:ly)?\b[^.]{0,20}\bsign(?:s|ed|ing)?\b",
    r"\bconfirm(?:s|ed)?\s+(?:the\s+)?(?:signing|transfer|deal|move)\b",
    r"\bcomplete(?:s|d)?\s+(?:a\s+|his\s+|her\s+)?(?:move|transfer|signing)\b",
    r"\bunveil(?:s|ed|ing)?\s+(?:new\s+)?(?:signing|signings)\b",
    r"\bmedical\s+(?:completed|done|passed)\b",
    r"\bagree(?:s|d)?\s+(?:a\s+)?(?:permanent\s+)?deal\b",
    r"\bjoins?\s+on\s+a\s+(?:permanent|free|loan)\b",
    r"\bsigns?\s+(?:a\s+)?(?:\d+[- ]year\s+)?(?:deal|contract)\s+with\b",
]

# "Deal collapsed" — a move that was on but has fallen through, been
# called off, or rejected outright. Sits alongside deal_done as the
# only other transfer-news category tracked — no gossip, no
# in-progress speculation.
_DEAL_COLLAPSED_PATTERNS = [
    r"\bdeal\s+(?:collapses?|collapsed|off|falls?\s+through|fell\s+through)\b",
    r"\bmove\s+(?:collapses?|collapsed|off|falls?\s+through|fell\s+through)\b",
    r"\btransfer\s+(?:collapses?|collapsed|off|falls?\s+through|fell\s+through)\b",
    r"\bwalks?\s+away\s+from\s+(?:a\s+)?(?:deal|move|transfer)\b",
    r"\bpulls?\s+out\s+of\s+(?:a\s+|the\s+)?(?:deal|move|transfer)\b",
    r"\b(?:rejects?|rejected|turns?\s+down|turned\s+down)\b[^.]{0,25}\b(?:move|transfer|deal|approach|bid)\b",
    r"\bmove\s+(?:is\s+)?(?:off|dead)\b",
    r"\bwithdraws?\s+(?:from\s+)?(?:the\s+)?(?:deal|move|transfer|talks)\b",
    r"\bends?\s+(?:interest|pursuit)\s+in\b",
]

# Player-quote spotlight — currently scoped to Messi and Ronaldo only
# (the two names Zafar asked for). Requires the player's name AND a
# speech-indicator verb in the same headline, so a plain transfer or
# stats headline that happens to mention either player doesn't get
# miscategorized as a "quote" story. Checked before every other
# category since it's the narrowest (name-anchored) bucket.
_PLAYER_QUOTE_PATTERNS = [
    r"\b(?:lionel\s+)?messi\b[^.]{0,60}\b(?:says?|said|reveals?|reacts?|insists?|admits?|hints?|warns?|opens?\s+up|speaks?\s+out|hits?\s+back|responds?|tells?|claims?|explains?)\b",
    r"\b(?:cristiano\s+)?ronaldo\b[^.]{0,60}\b(?:says?|said|reveals?|reacts?|insists?|admits?|hints?|warns?|opens?\s+up|speaks?\s+out|hits?\s+back|responds?|tells?|claims?|explains?)\b",
    r"\b(?:says?|said|reveals?|reacts?|insists?|admits?)\b[^.]{0,60}\b(?:messi|ronaldo)\b",
]

# Injury news — sidelined/ruled-out/surgery/return-date stories. Checked
# after manager/quote but before deal-done/deal-collapsed so an injury
# story doesn't get miscategorized as a transfer just because it
# mentions a club or a return timeline.
_INJURY_PATTERNS = [
    r"\binjur(?:y|ies|ed)\b",
    r"\bruled\s+out\b", r"\bsidelined\b",
    r"\b(?:hamstring|acl|groin|calf|ankle|knee|thigh|achilles|meniscus|metatarsal|hip|shoulder|back)\s+(?:injury|problem|issue|strain|tear|surgery)\b",
    r"\bundergoes?\s+surgery\b",
    r"\bout\s+for\s+(?:the\s+season|\d+\s+(?:weeks?|months?))\b",
    r"\breturn(?:s|ed|ing)?\s+from\s+injury\b",
    r"\bfitness\s+(?:test|concern|doubt|update)\b",
    r"\bmiss(?:es|ed)?\s+(?:the\s+rest\s+of\s+the\s+season|the\s+world\s+cup)\b",
    r"\bscan\s+(?:result|confirms?)\b",
    r"\bdoubtful\s+for\b",
]

# manager sacking/transfer are checked before deal-done/deal-collapsed
# so a headline that could fit two buckets lands in the more specific
# one. No gossip/rumour/in-progress-speculation category exists any
# more — transfer news here is confirmed-only (deal done or collapsed).
_CATEGORIES = (
    ("player_quote",     [re.compile(p, re.I) for p in _PLAYER_QUOTE_PATTERNS],     "Player Spotlight"),
    ("manager_sacking",  [re.compile(p, re.I) for p in _MANAGER_SACKING_PATTERNS],  "Manager Sacking"),
    ("manager_transfer", [re.compile(p, re.I) for p in _MANAGER_TRANSFER_PATTERNS], "Manager Transfer News"),
    ("injury",           [re.compile(p, re.I) for p in _INJURY_PATTERNS],           "Injury News"),
    ("deal_done",        [re.compile(p, re.I) for p in _DEAL_DONE_PATTERNS],        "Deal Done"),
    ("deal_collapsed",   [re.compile(p, re.I) for p in _DEAL_COLLAPSED_PATTERNS],   "Deal Collapsed"),
)

# Rolling sample of headlines that matched NO category this poll, so a
# quiet day can be diagnosed at a glance instead of guessing — capped
# small so logs don't flood. Cleared at the top of every check_new().
_UNMATCHED_SAMPLE_CAP = 8
_unmatched_sample: list = []


def _classify_headline(headline: str, source: str = "") -> tuple:
    """Returns (category_key, label) for the first matching bucket, or
    (None, None) if the headline doesn't fit any tracked category. On
    a miss, stashes the headline (capped) so check_new() can print a
    sample of what's being dropped — the fastest way to see whether
    the patterns need widening again in the future."""
    for key, patterns, label in _CATEGORIES:
        if any(p.search(headline) for p in patterns):
            return key, label
    if len(_unmatched_sample) < _UNMATCHED_SAMPLE_CAP:
        _unmatched_sample.append(f"{source}: {headline}" if source else headline)
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


def _get_rss(url: str, timeout: int = 10, image_fn=_rss_image) -> list[dict]:
    """Minimal RSS 2.0 parser via stdlib — returns
    [{title, link, image, description, published}, ...]. `description`
    is the feed's own <description> teaser text (raw, may contain HTML
    — poster.py strips/cleans it before it goes in a caption), "" when
    the feed doesn't carry one for that item. `image_fn` lets a
    specific feed supply its own image-selection logic; defaults to
    the generic thumbnail/content/enclosure lookup used by BBC/Sky."""
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
                    "description": (item.findtext("description") or "").strip(),
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
    """Polls every club league in config.TRANSFER_LEAGUES."""
    items = []
    slugs = dict(config.TRANSFER_LEAGUES)

    raw_count = 0
    for slug, league_name in slugs.items():
        data = _get_json(f"{ESPN_NEWS_API}/{slug}/news")
        if not data:
            continue
        for article in data.get("articles", []):
            headline = article.get("headline", "")
            raw_count += 1 if headline else 0
            category, label = _classify_headline(headline, "ESPN") if headline else (None, None)
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
                "description": article.get("description") or article.get("shortDescription") or "",
                "published": _parse_iso(article.get("published") or article.get("lastModified")),
                "source":    "ESPN",
            })
    print(f"[NEWS] ESPN: {raw_count} headlines fetched, {len(items)} matched a category")
    return items


def _bbc_candidates() -> list[dict]:
    items = []
    raw = _get_rss(BBC_FOOTBALL_RSS)
    for entry in raw:
        category, label = _classify_headline(entry["title"], "BBC")
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
            "description": entry.get("description", ""),
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
        category, label = _classify_headline(entry["title"], "Sky")
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
            "description": entry.get("description", ""),
            "published": entry.get("published"),
            "source":   "Sky Sports",
        })
    print(f"[NEWS] Sky: {len(raw_all)} RSS entries fetched ({raw_football} football), {len(items)} matched a category")
    return items


def _90min_candidates() -> list[dict]:
    items = []
    # 90min is football-only (unlike Sky's mixed feed), so no URL filtering
    # needed — every entry is in-scope, same as BBC.
    raw = _get_rss(NINETY_MIN_RSS)
    for entry in raw:
        category, label = _classify_headline(entry["title"], "90min")
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
            "description": entry.get("description", ""),
            "published": entry.get("published"),
            "source":   "90min",
        })
    print(f"[NEWS] 90min: {len(raw)} RSS entries fetched, {len(items)} matched a category")
    return items


def check_new(already_seen: set) -> list[dict]:
    """
    Polls all four sources, returns news items (manager sackings,
    manager transfers, injuries, deal-done, deal-collapsed) not
    present in `already_seen` (caller marks them seen after
    successfully posting). Combined and deduped by key across sources.
    Anything older than config.TRANSFER_MAX_AGE_HOURS is dropped
    regardless of dedup state — this module never surfaces the past.
    """
    candidates = []
    per_source_counts = {}
    _unmatched_sample.clear()
    for fn in (_espn_candidates, _bbc_candidates, _sky_candidates, _90min_candidates):
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
    if _unmatched_sample:
        print(f"[NEWS] sample of headlines that matched NO category this poll "
              f"(widen the patterns if these look like real deal-done/"
              f"deal-collapsed/manager/injury stories): {_unmatched_sample}")
    return new_items
