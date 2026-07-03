"""
graphics.py — Branded image cards for Facebook photo posts (v2)
==================================================================
Facebook's algorithm meaningfully favors photo posts over plain text.
This renders a self-contained PNG for each post — no external image
APIs, no stock-photo licensing, no scraped player photos.

FONTS
  Two open (OFL-licensed) fonts are bundled in fonts/:
    - Anton (condensed display) for scores and big headline words
    - Inter (variable weight)   for labels, names, and body copy
  Bundling real fonts (instead of Pillow's bitmap default) is what
  actually makes these look designed rather than debug-printed.
  IMPORTANT: Pillow's default font — and neither of these two — can
  render color emoji. The old version baked ⚽/🚩/🏁 straight into the
  PNG, which shows as blank boxes on a real render, not the emoji you
  see in source. Emoji now live ONLY in the Facebook caption text
  (poster.py), never inside the image. Category labels in the image
  are plain bold caps text badges instead ("GOAL", "FULL TIME", etc).

CRESTS, NOT HEADSHOTS
  Team crests are pulled the same way the old score cards did (from
  ESPN's own team.logo URL) — that's the club's own badge, standard
  editorial use, same as any TV graphics package.
  Player headshots are deliberately NOT scraped for transfer cards.
  Those photos are normally licensed stock (Getty/AP/etc.) — grabbing
  one from a search result and reposting it on a commercial page is a
  real rights-infringement risk, not just a style choice. Transfer
  cards instead show both clubs' crests with an arrow between them,
  which is accurate, attention-grabbing, and doesn't touch anyone's
  copyrighted photo. Crests come from scraper.get_crest() — a cache
  built from today's matches — and gracefully degrade to a text-only
  card when a club's crest isn't in the cache yet.
"""

import os
import time
import math
import textwrap
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter

CARD_SIZE = (1080, 1080)
OUT_DIR   = "cards"
FONT_DIR  = os.path.join(os.path.dirname(__file__), "fonts")

os.makedirs(OUT_DIR, exist_ok=True)

BRAND_NAME = "MATCH CORNA"
BRAND_SUB  = "LIVE"

# category → (dark bg, darker bg, accent color, badge label)
THEME = {
    "default":  {"bg": "#0B3D24", "bg2": "#082917", "accent": "#F2C230", "label": ""},
    "goal":     {"bg": "#0B3D24", "bg2": "#082917", "accent": "#F2C230", "label": "GOAL"},
    "kickoff":  {"bg": "#0B3D24", "bg2": "#082917", "accent": "#F2C230", "label": "KICK-OFF"},
    "fulltime": {"bg": "#0E2340", "bg2": "#091830", "accent": "#FF9142", "label": "FULL TIME"},
    "var":      {"bg": "#3D0D0D", "bg2": "#280707", "accent": "#FFFFFF", "label": "NO GOAL"},
    "transfer": {"bg": "#3D1B0A", "bg2": "#281106", "accent": "#FFD34D", "label": "TRANSFER"},
    "stats":    {"bg": "#1B1650", "bg2": "#110D38", "accent": "#7FD8FF", "label": "MATCHDAY"},
}

WHITE = "#FFFFFF"


# ══════════════════════════════════════════════════════════════════
# FONTS
# ══════════════════════════════════════════════════════════════════

def _display(size: int) -> ImageFont.FreeTypeFont:
    """Anton — condensed display face for scores / big headline words."""
    return ImageFont.truetype(os.path.join(FONT_DIR, "Anton-Regular.ttf"), size)


def _body(size: int, weight: str = "Regular") -> ImageFont.FreeTypeFont:
    """Inter variable font at a given named weight (Regular/Medium/SemiBold/Bold/Black)."""
    f = ImageFont.truetype(os.path.join(FONT_DIR, "Inter-Variable.ttf"), size)
    try:
        f.set_variation_by_name(weight)
    except Exception:
        pass  # falls back to the font's default instance
    return f


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _fetch_crest(url: str, max_size=(200, 200)):
    """Best-effort team crest fetch (ESPN's team.logo URL). Returns
    None on any failure — caller falls back to text-only, never crashes."""
    if not url:
        return None
    try:
        r = requests.get(url, timeout=6)
        if r.status_code != 200:
            return None
        img = Image.open(BytesIO(r.content)).convert("RGBA")
        img.thumbnail(max_size, Image.LANCZOS)
        return img
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════
# BACKGROUND — vertical gradient + soft diagonal sheen + vignette
# ══════════════════════════════════════════════════════════════════

def _base_canvas(kind: str):
    theme = THEME.get(kind, THEME["default"])
    top, bottom = _hex_to_rgb(theme["bg"]), _hex_to_rgb(theme["bg2"])
    W, H = CARD_SIZE

    grad = Image.new("RGB", (1, H), top)
    gpx = grad.load()
    for y in range(H):
        t = y / H
        gpx[0, y] = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
    img = grad.resize((W, H))

    # Soft diagonal sheen — a translucent white band across the card for
    # a bit of depth without a full texture/noise pass.
    sheen = Image.new("L", CARD_SIZE, 0)
    sdraw = ImageDraw.Draw(sheen)
    sdraw.polygon([(0, H * 0.15), (W * 0.55, 0), (W * 0.75, 0), (0, H * 0.45)], fill=28)
    sheen = sheen.filter(ImageFilter.GaussianBlur(60))
    white_layer = Image.new("RGB", CARD_SIZE, WHITE)
    img = Image.composite(white_layer, img, sheen)

    # Vignette — darken the corners slightly so text stays legible
    # wherever it lands.
    vign = Image.new("L", CARD_SIZE, 0)
    vdraw = ImageDraw.Draw(vign)
    vdraw.ellipse([-W * 0.3, -H * 0.3, W * 1.3, H * 1.3], fill=255)
    vign = vign.filter(ImageFilter.GaussianBlur(140))
    black_layer = Image.new("RGB", CARD_SIZE, (0, 0, 0))
    img = Image.composite(img, black_layer, vign)

    return img, ImageDraw.Draw(img), theme


def _shadow_paste(base: Image.Image, layer: Image.Image, pos: tuple, blur: int = 14, opacity: int = 130):
    """Pastes `layer` (RGBA) onto `base` with a soft drop shadow beneath it."""
    alpha = layer.split()[-1].point(lambda a: min(a, opacity))
    shadow = Image.new("RGBA", base.size, (0, 0, 0, 0))
    shadow.paste((0, 0, 0, 255), (pos[0] + 6, pos[1] + 10), alpha)
    shadow = shadow.filter(ImageFilter.GaussianBlur(blur))
    base_rgba = base.convert("RGBA")
    base_rgba.alpha_composite(shadow)
    base_rgba.alpha_composite(layer, pos)
    base.paste(base_rgba.convert("RGB"))


def _crest_badge(base: Image.Image, crest: Image.Image, center: tuple, diameter: int = 200):
    """White circular backing plate + soft shadow + centered crest — reads
    clean against any background color, unlike a bare logo on a dark bg."""
    plate = Image.new("RGBA", (diameter, diameter), (0, 0, 0, 0))
    ImageDraw.Draw(plate).ellipse([0, 0, diameter, diameter], fill=(255, 255, 255, 255))
    if crest:
        c = crest.copy()
        c.thumbnail((int(diameter * 0.72), int(diameter * 0.72)), Image.LANCZOS)
        plate.alpha_composite(c, ((diameter - c.width) // 2, (diameter - c.height) // 2))
    pos = (center[0] - diameter // 2, center[1] - diameter // 2)
    _shadow_paste(base, plate, pos, blur=16, opacity=110)


# ══════════════════════════════════════════════════════════════════
# SHARED CHROME — category badge + brand watermark
# ══════════════════════════════════════════════════════════════════

def _category_badge(draw, theme, x=60, y=56):
    label = theme["label"]
    if not label:
        return y
    font = _display(34)
    bbox = draw.textbbox((0, 0), label, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    pad_x, pad_y = 26, 14
    draw.rounded_rectangle(
        [x, y, x + tw + pad_x * 2, y + th + pad_y * 2],
        radius=8, fill=theme["accent"],
    )
    draw.text((x + pad_x, y + pad_y - bbox[1]), label, font=font, fill=_hex_to_rgb(theme["bg"]))
    return y + th + pad_y * 2


def _brand_watermark(draw, W, H):
    dot_r = 7
    cx, cy = 60 + dot_r, H - 62
    draw.ellipse([cx - dot_r, cy - dot_r, cx + dot_r, cy + dot_r], fill="#F2C230")
    name_font = _body(26, "Bold")
    sub_font  = _body(20, "Medium")
    name_x = cx + dot_r + 12
    draw.text((name_x, H - 78), BRAND_NAME, font=name_font, fill=WHITE)
    bbox = draw.textbbox((0, 0), BRAND_NAME, font=name_font)
    draw.text((name_x + (bbox[2] - bbox[0]) + 10, H - 76), BRAND_SUB, font=sub_font, fill="#F2C230")


def _save(img) -> str:
    path = os.path.join(OUT_DIR, f"card_{int(time.time() * 1000)}.png")
    img.save(path, "PNG")
    return path


# ══════════════════════════════════════════════════════════════════
# GENERIC CARD — VAR, breaking transfer news, top scorers, win probability
# ══════════════════════════════════════════════════════════════════

def render_card(kind: str, _marker_unused: str, title: str, lines: list) -> str:
    """`_marker_unused` is kept for call-signature compatibility with the
    old emoji-marker API — markers now live only in the FB caption text."""
    img, draw, theme = _base_canvas(kind)
    W, H = CARD_SIZE
    y = _category_badge(draw, theme)
    y += 40

    title_font = _display(64)
    for line in textwrap.wrap(title, width=18):
        draw.text((60, y), line, font=title_font, fill=WHITE)
        bbox = draw.textbbox((0, 0), line, font=title_font)
        y += (bbox[3] - bbox[1]) + 18
    y += 24

    body_font = _body(38, "Medium")
    for line in lines:
        for wrapped in (textwrap.wrap(line, width=34) or [""]):
            draw.text((60, y), wrapped, font=body_font, fill="#E8E8E8")
            bbox = draw.textbbox((0, 0), wrapped, font=body_font)
            y += (bbox[3] - bbox[1]) + 20
        y += 10

    _brand_watermark(draw, W, H)
    return _save(img)


# ══════════════════════════════════════════════════════════════════
# SCORE CARD — kickoff / goal / fulltime, with crest badges
# ══════════════════════════════════════════════════════════════════

def render_score_card(kind: str, _marker_unused: str, home_name: str, away_name: str,
                       home_score, away_score, event_line: str = "",
                       home_crest_url: str = "", away_crest_url: str = "") -> str:
    """
    event_line can be multi-line ("\n"-separated) — bot.py uses this to
    put the scorer on one line and the assist (when available) on the
    next, each rendered as its own pill.
    """
    img, draw, theme = _base_canvas(kind)
    W, H = CARD_SIZE
    _category_badge(draw, theme)

    home_crest = _fetch_crest(home_crest_url)
    away_crest = _fetch_crest(away_crest_url)

    crest_y = 260
    _crest_badge(img, home_crest, (190, crest_y), diameter=190)
    _crest_badge(img, away_crest, (W - 190, crest_y), diameter=190)
    draw = ImageDraw.Draw(img)  # img was mutated in-place via paste; refresh handle

    # Score, centered, big Anton digits with a soft shadow
    score_text = f"{home_score} - {away_score}"
    score_font = _display(130)
    bbox = draw.textbbox((0, 0), score_text, font=score_font)
    tw = bbox[2] - bbox[0]
    sx, sy = (W - tw) / 2, crest_y - 10
    draw.text((sx + 4, sy + 6), score_text, font=score_font, fill=(0, 0, 0))
    draw.text((sx, sy), score_text, font=score_font, fill=WHITE)

    # Team names below crests
    name_font = _body(32, "SemiBold")
    for name, cx in ((home_name, 190), (away_name, W - 190)):
        ny = crest_y + 130
        for line in textwrap.wrap(name, width=15)[:2]:
            bbox = draw.textbbox((0, 0), line, font=name_font)
            lw = bbox[2] - bbox[0]
            draw.text((cx - lw / 2, ny), line, font=name_font, fill=WHITE)
            ny += 40

    # Event line(s) — each rendered as its own accent pill for contrast
    if event_line:
        ev_font = _body(38, "Bold")
        y = crest_y + 250
        for raw_line in event_line.split("\n"):
            bbox = draw.textbbox((0, 0), raw_line, font=ev_font)
            tw = bbox[2] - bbox[0]
            pad_x, pad_y = 28, 14
            box = [(W - tw) / 2 - pad_x, y, (W + tw) / 2 + pad_x, y + (bbox[3] - bbox[1]) + pad_y * 2]
            draw.rounded_rectangle(box, radius=999, fill=theme["accent"])
            draw.text(((W - tw) / 2, y + pad_y - bbox[1]), raw_line, font=ev_font, fill=_hex_to_rgb(theme["bg"]))
            y += (bbox[3] - bbox[1]) + pad_y * 2 + 16

    _brand_watermark(draw, W, H)
    return _save(img)


# ══════════════════════════════════════════════════════════════════
# TRANSFER CARD — two club crests + arrow, real data only
# ══════════════════════════════════════════════════════════════════

def render_transfer_card(player: str, from_club: str, to_club: str, fee_line: str,
                          from_crest_url: str = "", to_crest_url: str = "") -> str:
    """
    Used for the transfermarkt hourly highlight, where we know both real
    club names. Shows both crests (fetched from ESPN's own badge URLs via
    scraper.get_crest — see module docstring for why this is used instead
    of a scraped player photo). Degrades gracefully to blank badge circles
    when a crest isn't in the cache yet — never shows a broken image.
    """
    img, draw, theme = _base_canvas("transfer")
    W, H = CARD_SIZE
    _category_badge(draw, theme)

    from_crest = _fetch_crest(from_crest_url)
    to_crest   = _fetch_crest(to_crest_url)

    crest_y = 280
    _crest_badge(img, from_crest, (230, crest_y), diameter=210)
    _crest_badge(img, to_crest, (W - 230, crest_y), diameter=210)
    draw = ImageDraw.Draw(img)

    # Arrow between the two crests
    ay = crest_y
    ax1, ax2 = 230 + 130, W - 230 - 130
    draw.line([(ax1, ay), (ax2, ay)], fill=theme["accent"], width=6)
    draw.polygon([(ax2, ay - 16), (ax2 + 26, ay), (ax2, ay + 16)], fill=theme["accent"])

    # Club names under crests
    name_font = _body(28, "SemiBold")
    for name, cx in ((from_club, 230), (to_club, W - 230)):
        ny = crest_y + 140
        for line in textwrap.wrap(name, width=14)[:2]:
            bbox = draw.textbbox((0, 0), line, font=name_font)
            lw = bbox[2] - bbox[0]
            draw.text((cx - lw / 2, ny), line, font=name_font, fill=WHITE)
            ny += 36

    # Player name — the headline
    player_font = _display(72)
    y = crest_y + 250
    for line in textwrap.wrap(player, width=16):
        bbox = draw.textbbox((0, 0), line, font=player_font)
        lw = bbox[2] - bbox[0]
        draw.text(((W - lw) / 2, y), line, font=player_font, fill=WHITE)
        y += (bbox[3] - bbox[1]) + 16

    # Fee pill
    fee_font = _body(34, "Bold")
    bbox = draw.textbbox((0, 0), fee_line, font=fee_font)
    tw = bbox[2] - bbox[0]
    pad_x, pad_y = 30, 16
    y += 20
    box = [(W - tw) / 2 - pad_x, y, (W + tw) / 2 + pad_x, y + (bbox[3] - bbox[1]) + pad_y * 2]
    draw.rounded_rectangle(box, radius=999, fill=theme["accent"])
    draw.text(((W - tw) / 2, y + pad_y - bbox[1]), fee_line, font=fee_font, fill=_hex_to_rgb(theme["bg"]))

    _brand_watermark(draw, W, H)
    return _save(img)
