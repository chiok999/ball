"""
article.py — best-effort full-article fetch + fact extraction
================================================================
Fetches the article a news headline links to, so the Facebook
caption can say more than just the headline restated.

DELIBERATE DESIGN CHOICE — read before "improving" this into a
generic summarizer: this does NOT rewrite the article's prose into a
paraphrase. Cleanly paraphrasing someone else's sentences without
mirroring their wording/structure closely is a genuinely hard
judgment call, and a rule-based (non-LLM) attempt at it risks landing
too close to the original — a real copyright problem for a page that
republishes news. Instead, this extracts a small set of CONCRETE
FACTS via regex — a transfer fee, a contract length, at most one
short quote (capped at 15 words) — and the caller expresses everything
else in the bot's own plain words. Bare facts like "£45m" or "a
three-year deal" aren't copyrightable expression; a full rewritten
paragraph would be walking much closer to the line.

⚠️  LIVE SMOKE TEST NEEDED ON DEPLOY, same caveat as sofascore.py/
worldcup.py in this project: this sandbox can't reach espn.com,
bbc.co.uk, theguardian.com, or 90min.com to verify the exact HTML
shape of a live article page. The <p>-tag extraction below is a
reasonable generic approach (these are server-rendered news sites,
not JS-only SPAs), but if a site's markup doesn't cooperate, the
defensive design here means it just yields no extra facts for that
source — never a crash, never garbage text in a caption. Watch
Railway logs after deploy for "[ARTICLE] parsed 0 chars" on a source
that should have content, and adjust the extraction if that's
consistent for one particular site.

Network fetches happen at POST time (only for items that already
cleared the rate-limit cap), not at classification time, so a
slow/blocked source degrades gracefully to "no extra facts" instead
of holding up the poll loop.
"""

import re
import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml",
}

FETCH_TIMEOUT = 8
MAX_ARTICLE_CHARS = 6000  # plenty for the first several paragraphs; keeps parsing bounded
MAX_HTML_BYTES = 300_000  # defensive cap in case of a huge/misbehaving response


def _fetch_html(url: str) -> str | None:
    try:
        r = requests.get(url, headers=HEADERS, timeout=FETCH_TIMEOUT)
        if r.status_code == 200:
            return r.text[:MAX_HTML_BYTES]
        print(f"[ARTICLE] HTTP {r.status_code}: {url[:80]}")
    except Exception as e:
        print(f"[ARTICLE] fetch failed: {e}")
    return None


def _extract_paragraphs(html: str) -> str:
    """Dependency-free <p>-tag text extraction. Strips script/style
    blocks first, then keeps only paragraphs that look like real
    sentences (skip short nav/caption/ad fragments with no spaces) —
    a crude but reasonable filter for boilerplate on a news page."""
    html = re.sub(r"(?is)<(script|style|noscript)[^>]*>.*?</\1>", " ", html)
    paras = re.findall(r"(?is)<p[^>]*>(.*?)</p>", html)
    cleaned = []
    total_len = 0
    for p in paras:
        text = re.sub(r"(?s)<[^>]+>", " ", p)
        text = re.sub(r"&[a-zA-Z#0-9]+;", " ", text)
        text = re.sub(r"\s+", " ", text).strip()
        if len(text) > 40 and text.count(" ") > 5:
            cleaned.append(text)
            total_len += len(text)
        if total_len > MAX_ARTICLE_CHARS:
            break
    return " ".join(cleaned)


def fetch_article_text(url: str) -> str:
    """Returns extracted article body text, or "" on ANY failure —
    callers must treat "" as 'no extra facts available this time',
    never as an error to propagate or retry aggressively."""
    if not url:
        return ""
    html = _fetch_html(url)
    if not html:
        return ""
    try:
        text = _extract_paragraphs(html)
        print(f"[ARTICLE] parsed {len(text)} chars from {url[:60]}")
        return text
    except Exception as e:
        print(f"[ARTICLE] parse failed: {e}")
        return ""


# ── Fact extraction (regex, not NLP — deliberately narrow/safe) ─────

_FEE_RE      = re.compile(r"[£€$]\s?\d+(?:\.\d+)?\s?(?:m|million|k|thousand)\b", re.I)
_DURATION_RE = re.compile(
    r"\b(?:a\s+|one[- ]|two[- ]|three[- ]|four[- ]|five[- ]|six[- ]|\d+[- ])"
    r"year[s]?\s+(?:deal|contract)\b", re.I
)
_UNTIL_RE  = re.compile(r"\buntil\s+(?:20\d{2}|summer\s+20\d{2})\b", re.I)
_QUOTE_RE  = re.compile(r'["\u201c\u2018]([^"\u201d\u2019]{8,90})["\u201d\u2019]')


def extract_facts(article_text: str) -> dict:
    """Pulls a small set of concrete facts out of article body text.
    Every value is either a bare number/date/duration (not
    copyrightable expression on its own) or, for at most ONE quote,
    capped at 15 words — this project's own copyright rule, applied
    to what it publishes, not just what it reads."""
    facts: dict = {}
    if not article_text:
        return facts

    fee = _FEE_RE.search(article_text)
    if fee:
        facts["fee"] = fee.group(0)

    duration = _DURATION_RE.search(article_text)
    if duration:
        facts["duration"] = duration.group(0)

    until = _UNTIL_RE.search(article_text)
    if until:
        facts["until"] = until.group(0)

    quote_match = _QUOTE_RE.search(article_text)
    if quote_match:
        quote = quote_match.group(1).strip().rstrip(",;:")
        words = quote.split()
        if len(words) > 15:
            quote = " ".join(words[:15]) + "…"
        facts["quote"] = quote

    return facts


def fetch_and_extract_facts(url: str) -> dict:
    """One-call convenience wrapper: fetch + extract, never raises."""
    try:
        return extract_facts(fetch_article_text(url))
    except Exception as e:
        print(f"[ARTICLE] fetch_and_extract_facts failed: {e}")
        return {}
