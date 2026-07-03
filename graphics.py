"""
graphics.py — Branded image cards for Facebook photo posts
==============================================================
Facebook's algorithm meaningfully favors photo posts over plain text.
This renders a simple, on-brand PNG for each post so bot.py can use
poster.post_photo() instead of poster.post() — no external image APIs,
no stock-photo licensing, no scraped player photos. Fully self-generated.

Uses Pillow's built-in scalable default font (Aileron, bundled inside
Pillow itself since 9.2) — no font files to ship, works identically on
Railway's minimal container as anywhere else Pillow is installed.
"""

import os
import time
import textwrap
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont

CARD_SIZE = (1080, 1080)
OUT_DIR = "cards"
os.makedirs(OUT_DIR, exist_ok=True)

BRAND_NAME = "MATCH CORNA LIVE"

# Background color per post category
ACCENTS = {
    "default":  "#14532D",  # pitch green
    "goal":     "#14532D",
    "kickoff":  "#14532D",
    "fulltime": "#1E3A5F",  # deep blue
    "var":      "#7A1F1F",  # red
    "transfer": "#7C2D12",  # burnt orange/red — matches 🚨 urgency
    "stats":    "#312E81",  # indigo (used by World Cup filler cards)
}
GOLD  = "#FFD400"
WHITE = "#FFFFFF"


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.load_default(size=size)


def _fetch_crest(url: str, max_size=(170, 170)):
    """Best-effort team crest fetch (e.g. ESPN's team.logo URL). Returns
    None on any failure — caller falls back to text-only, never crashes."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=6)
        if r.status_code != 200:
            return None
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        img.thumbnail(max_size)
        return img
    except Exception:
        return None


def _base_canvas(accent_key: str):
    color = ACCENTS.get(accent_key, ACCENTS["default"])
    top = _hex_to_rgb(color)
    bottom = tuple(max(0, c - 30) for c in top)
    img = Image.new("RGB", CARD_SIZE, top)
    draw = ImageDraw.Draw(img)
    for y in range(CARD_SIZE[1]):
        t = y / CARD_SIZE[1]
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (CARD_SIZE[0], y)], fill=row)
    return img, draw


def _draw_wordmark(draw, marker: str):
    draw.text((60, 50), f"{marker} {BRAND_NAME}", font=_font(32), fill=GOLD)


def _save(img) -> str:
    path = os.path.join(OUT_DIR, f"card_{int(time.time() * 1000)}.png")
    img.save(path, "PNG")
    return path


# ══════════════════════════════════════════════════════════════════
# GENERIC CARD — VAR, transfer news, top scorers, win probability
# ══════════════════════════════════════════════════════════════════

def render_card(kind: str, marker: str, title: str, lines: list) -> str:
    img, draw = _base_canvas(kind)
    W, H = CARD_SIZE
    _draw_wordmark(draw, marker)

    y = 190
    for line in textwrap.wrap(title, width=20):
        draw.text((60, y), line, font=_font(60), fill=WHITE)
        y += 74

    y += 30
    body_font = _font(40)
    for line in lines:
        for wrapped in (textwrap.wrap(line, width=30) or [""]):
            draw.text((60, y), wrapped, font=body_font, fill=WHITE)
            y += 54
        y += 14

    draw.text((60, H - 80), "Follow our page: Match Corna", font=_font(28), fill=GOLD)
    return _save(img)


# ══════════════════════════════════════════════════════════════════
# SCORE CARD — kickoff / goal / fulltime, with crest logos if available
# ══════════════════════════════════════════════════════════════════

def render_score_card(kind: str, marker: str, home_name: str, away_name: str,
                       home_score, away_score, event_line: str = "",
                       home_crest_url: str = "", away_crest_url: str = "") -> str:
    """
    event_line can be multi-line (separated by "\n") — used by bot.py to
    show the scorer on one line and the assist (🎯 Name) on the next.
    """
    img, draw = _base_canvas(kind)
    W, H = CARD_SIZE
    _draw_wordmark(draw, marker)

    home_crest = _fetch_crest(home_crest_url)
    away_crest = _fetch_crest(away_crest_url)

    crest_y = 260
    if home_crest:
        img.paste(home_crest, (100, crest_y), home_crest)
    if away_crest:
        img.paste(away_crest, (W - 100 - away_crest.width, crest_y), away_crest)

    # Score, centered
    score_text = f"{home_score} - {away_score}"
    score_font = _font(110)
    bbox = draw.textbbox((0, 0), score_text, font=score_font)
    tw = bbox[2] - bbox[0]
    draw.text(((W - tw) / 2, crest_y + 30), score_text, font=score_font, fill=WHITE)

    # Team names below crests
    name_font = _font(34)
    for name, cx in ((home_name, 185), (away_name, W - 185)):
        for i, line in enumerate(textwrap.wrap(name, width=14)[:2]):
            bbox = draw.textbbox((0, 0), line, font=name_font)
            lw = bbox[2] - bbox[0]
            draw.text((cx - lw / 2, crest_y + 190 + i * 42), line, font=name_font, fill=WHITE)

    # Event line(s) — scorer/minute, "Kickoff!", AET/pens note, and
    # optionally a second line for the assist provider.
    if event_line:
        ev_font = _font(42)
        y = crest_y + 300
        for raw_line in event_line.split("\n"):
            for line in textwrap.wrap(raw_line, width=32) or [""]:
                bbox = draw.textbbox((0, 0), line, font=ev_font)
                lw = bbox[2] - bbox[0]
                draw.text(((W - lw) / 2, y), line, font=ev_font, fill=GOLD)
                y += 52

    draw.text((60, H - 80), "Follow our page: Match Corna", font=_font(28), fill=GOLD)
    return _save(img)
