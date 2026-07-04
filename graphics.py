"""
graphics.py — Branded image cards for Facebook photo posts
==============================================================
Facebook's algorithm meaningfully favors photo posts over plain text.
This renders on-brand PNGs so bot.py can use poster.post_photo()
instead of poster.post() — no external image APIs, no stock-photo
licensing.

IMPORTANT DESIGN NOTE (read before touching marker/badge text):
Pillow's bundled default font ("Aileron") has NO emoji glyphs. Any
emoji character drawn with ImageFont.load_default() renders as a
blank box, not the emoji. So this file never draws emoji onto the
canvas — every "marker" is a real vector badge (colored pill +
plain-text label) instead. Emoji are still fine in the Facebook
*caption* (poster.py), since Facebook's own renderer draws those,
not Pillow.

Two families of card:
  render_card         — generic stat/news card (title + body lines)
  render_score_card    — kickoff / goal / full-time, two-team layout
  render_photo_card    — NEW: wraps a real downloaded photo (e.g. a
                          player photo from a transfer headline) with
                          the same badge/ribbon branding, instead of
                          generating a text-only card. Falls back to
                          render_card automatically if no usable image
                          is available.
"""

import os
import time
import math
import textwrap
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter

CARD_SIZE = (1080, 1080)
OUT_DIR = "cards"
os.makedirs(OUT_DIR, exist_ok=True)

# ── Real bundled font (Poppins, OFL-licensed via Google Fonts) ─────────
# Pillow's load_default() only ships one thin weight, which is the #1
# reason generated cards read as "generic/flat" next to a template made
# in Canva. Poppins ships ExtraBold/Bold/SemiBold/Regular, so headlines,
# scores and body text can each get the right weight instead of every
# line looking the same thickness. Ship these four .ttf files in a
# "fonts/" folder next to graphics.py. If they're missing (e.g. a fresh
# clone before committing the fonts folder), everything falls back to
# Pillow's default font automatically — nothing crashes.
FONTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")
_FONT_FILES = {
    "extrabold": "Poppins-ExtraBold.ttf",
    "bold":      "Poppins-Bold.ttf",
    "semibold":  "Poppins-SemiBold.ttf",
    "regular":   "Poppins-Regular.ttf",
}
_font_cache: dict = {}

BRAND_NAME = "MATCH CORNA LIVE"
BRAND_TAGLINE = "Follow the page for live scores"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/131.0.0.0 Safari/537.36",
}

# Background color per post category
ACCENTS = {
    "default":  "#14532D",  # pitch green
    "goal":     "#14532D",
    "kickoff":  "#166534",
    "fulltime": "#1E3A5F",  # deep blue
    "var":      "#7A1F1F",  # red
    "transfer": "#7C2D12",  # burnt orange/red — matches breaking-news urgency
    "manager":  "#0C4A6E",  # deep sky blue — distinct from transfer red
    "worldcup": "#065F46",  # emerald — ties to World Cup branding
    "interview": "#4C1D95", # violet — distinct "reaction" feel
    "stats":    "#312E81",  # indigo (World Cup filler cards)
}

# Badge (pill) style per category — drawn, never emoji.
BADGES = {
    "default":  ("MATCH UPDATE",     "#14532D"),
    "goal":     ("GOAL",             "#B45309"),
    "kickoff":  ("KICK-OFF",         "#15803D"),
    "fulltime": ("FULL TIME",        "#1E3A5F"),
    "var":      ("VAR REVIEW",       "#7A1F1F"),
    "transfer": ("BREAKING NEWS",    "#C2410C"),
    "manager":  ("MANAGER NEWS",     "#0369A1"),
    "worldcup": ("WORLD CUP",        "#059669"),
    "interview": ("REACTION",        "#6D28D9"),
    "stats":    ("STATS",            "#4338CA"),
}

GOLD  = "#FFD400"
WHITE = "#FFFFFF"
INK   = "#0B0F0C"

# Deterministic palette used for initials-avatar fallback when a crest
# can't be fetched — keeps team "identity" visually consistent run to run.
_AVATAR_PALETTE = [
    "#EF4444", "#F59E0B", "#10B981", "#3B82F6",
    "#8B5CF6", "#EC4899", "#14B8A6", "#F97316",
]


def _hex_to_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def _font(size: int, weight: str = "semibold") -> ImageFont.FreeTypeFont:
    """Loads the bundled Poppins weight at `size`, cached per (weight,
    size) pair. `weight` is one of "extrabold"/"bold"/"semibold"/
    "regular". Falls back to Pillow's built-in font if the .ttf files
    haven't been shipped (so this never crashes a deploy)."""
    key = (weight, size)
    if key in _font_cache:
        return _font_cache[key]
    filename = _FONT_FILES.get(weight, _FONT_FILES["semibold"])
    path = os.path.join(FONTS_DIR, filename)
    try:
        font = ImageFont.truetype(path, size)
    except Exception:
        font = ImageFont.load_default(size=size)
    _font_cache[key] = font
    return font


def _text_w(draw, text, font) -> int:
    bbox = draw.textbbox((0, 0), text, font=font)
    return bbox[2] - bbox[0]


def _shadow_text(draw, xy, text, font, fill=WHITE, stroke_width=0,
                  shadow=(0, 0, 0, 130), offset=(0, 3)):
    """Draws a soft drop shadow behind text so it stays readable over
    photos or busy gradients, then the text itself on top."""
    x, y = xy
    draw.text((x + offset[0], y + offset[1]), text, font=font, fill=shadow)
    draw.text((x, y), text, font=font, fill=fill, stroke_width=stroke_width,
               stroke_fill=fill)


def _fetch_image(url: str, timeout: int = 8):
    """Best-effort image fetch (crest, photo, etc). Returns a PIL Image
    in RGBA, or None on any failure — callers must have a fallback."""
    if not url:
        return None
    try:
        r = requests.get(url, headers=HEADERS, timeout=timeout)
        if r.status_code != 200:
            return None
        return Image.open(BytesIO(r.content)).convert("RGBA")
    except Exception:
        return None


# Kept for backwards-compat call sites (bot.py imports this name).
def _fetch_crest(url: str, max_size=(170, 170)):
    img = _fetch_image(url)
    if img is None:
        return None
    img.thumbnail(max_size)
    return img


def _save(img) -> str:
    path = os.path.join(OUT_DIR, f"card_{int(time.time() * 1000)}.png")
    img.convert("RGB").save(path, "PNG")
    return path


# ══════════════════════════════════════════════════════════════════
# SHARED CHROME — background, badge pill, brand ribbon
# ══════════════════════════════════════════════════════════════════

def _draw_light_rays(img, n_rays: int = 6, spread: int = 46,
                      length: int = 980, color=(255, 255, 255), max_alpha: int = 30):
    """Stadium floodlight fan, beamed down from both top corners — the
    crisscross rays seen in broadcast-style scoreboard templates. Each
    ray is a thin blurred triangle; overlapping rays near the corner
    naturally brighten, exactly like real floodlight banks."""
    W, H = img.size
    layer = Image.new("RGBA", img.size, (0, 0, 0, 0))
    ldraw = ImageDraw.Draw(layer)
    for corner_x, base_angle in ((0, 55), (W, 125)):
        for i in range(n_rays):
            angle = base_angle + (i - (n_rays - 1) / 2) * (spread / n_rays)
            rad = math.radians(angle)
            dx, dy = math.cos(rad) * length, math.sin(rad) * length
            half_w = 34
            perp = math.radians(angle + 90)
            ox, oy = math.cos(perp) * half_w, math.sin(perp) * half_w
            p1 = (corner_x - ox, -oy)
            p2 = (corner_x + ox, oy)
            p3 = (corner_x + dx, dy)
            ldraw.polygon([p1, p2, p3], fill=(*color, max_alpha))
    layer = layer.filter(ImageFilter.GaussianBlur(10))
    return Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB")


def _base_canvas(accent_key: str):
    color = ACCENTS.get(accent_key, ACCENTS["default"])
    top = _hex_to_rgb(color)
    bottom = tuple(max(0, c - 40) for c in top)
    img = Image.new("RGB", CARD_SIZE, top)
    draw = ImageDraw.Draw(img)
    for y in range(CARD_SIZE[1]):
        t = y / CARD_SIZE[1]
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (CARD_SIZE[0], y)], fill=row)

    # Subtle diagonal texture stripes — cheap way to make a flat gradient
    # look like a designed template instead of a solid color fill.
    stripe = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(stripe)
    W, H = CARD_SIZE
    step = 90
    for x in range(-H, W, step):
        sdraw.line([(x, H), (x + H, 0)], fill=(255, 255, 255, 10), width=26)
    img = Image.alpha_composite(img.convert("RGBA"), stripe).convert("RGB")

    # Floodlight beam fans from both top corners — the same broadcast
    # scoreboard cue used across the stadium-canvas cards, so every
    # card family (not just kickoff/goal/full-time) shares the look.
    img = _draw_light_rays(img)
    return img, ImageDraw.Draw(img)


def _draw_badge_pill(draw, text: str, accent_hex: str, xy=(60, 56)):
    """Solid colored pill with bold-ish text — the vector replacement
    for an emoji marker, guaranteed to render on every platform."""
    font = _font(30)
    pad_x, pad_y = 26, 14
    tw = _text_w(draw, text, font)
    x, y = xy
    w, h = tw + pad_x * 2, 30 + pad_y * 2 - 12
    draw.rounded_rectangle([x, y, x + w, y + h], radius=h // 2, fill=WHITE)
    draw.text((x + pad_x, y + pad_y - 6), text, font=font, fill=accent_hex, stroke_width=1, stroke_fill=accent_hex)
    return y + h  # bottom edge, for layout below it


def _draw_ribbon_badge(draw, cx: float, cy: float, text: str, font,
                        fill="#0B0F0C", text_color=WHITE,
                        pad_x: int = 34, pad_y: int = 16, notch: int = 20):
    """A pointed-end ribbon/chevron badge, centered at (cx, cy) — the
    angular banner shape used for scorelines and status labels on
    broadcast scoreboard templates, instead of a plain rounded pill.
    Returns (width, height) of the drawn badge."""
    tw = _text_w(draw, text, font)
    ascent, descent = font.getmetrics()
    th = ascent + descent
    w = tw + pad_x * 2
    h = th + pad_y * 2
    x0, x1 = cx - w / 2, cx + w / 2
    y0, y1 = cy - h / 2, cy + h / 2
    pts = [
        (x0, y0), (x1, y0), (x1 + notch, cy), (x1, y1),
        (x0, y1), (x0 - notch, cy),
    ]
    fill_rgb = _hex_to_rgb(fill) if isinstance(fill, str) else fill
    draw.polygon(pts, fill=fill_rgb)
    draw.text((cx - tw / 2, cy - th / 2), text, font=font, fill=text_color)
    return w, h


def _draw_wordmark(draw, xy=(60, 50)):
    draw.text(xy, BRAND_NAME, font=_font(30), fill=GOLD)


def _draw_brand_ribbon(img, draw):
    """Solid footer ribbon spanning the width — replaces the old loose
    corner caption, reads as an intentional template element."""
    W, H = img.size
    ribbon_h = 84
    overlay = Image.new("RGBA", (W, ribbon_h), (0, 0, 0, 150))
    img.paste(Image.alpha_composite(img.crop((0, H - ribbon_h, W, H)).convert("RGBA"), overlay), (0, H - ribbon_h))
    draw = ImageDraw.Draw(img)
    draw.text((44, H - ribbon_h + 16), BRAND_NAME, font=_font(30), fill=GOLD)
    draw.text((44, H - ribbon_h + 50), BRAND_TAGLINE, font=_font(22), fill="#E5E7EB")
    return draw


def _hexagon_points(size, inset: float = 0.0, orientation: str = "vertical"):
    """Hexagon vertices inscribed in `size`. `orientation="vertical"`
    gives a flat-top hex (points at top/bottom, flat left/right sides)
    — used for crest/flag badges. `orientation="horizontal"` gives a
    hex pointed on the left/right, flat top/bottom — the wide shape
    used for a scoreline container. `inset` shrinks the hexagon inward
    by that many pixels — used to draw a slightly smaller hexagon for
    a border ring effect."""
    w, h = size
    cx, cy = w / 2, h / 2
    r_x = w / 2 - inset
    r_y = h / 2 - inset
    start = 90 if orientation == "vertical" else 0
    pts = []
    for i in range(6):
        angle = math.radians(start + 60 * i)
        pts.append((cx + r_x * math.cos(angle), cy + r_y * math.sin(angle)))
    return pts


def _hex_badge_frame(size=(170, 170), border_hex: str = "#8FD3E8", fill_hex: str = WHITE):
    """The hexagon 'frame' behind a crest/flag/initials — a light
    border hexagon with a white hexagon inset, so any logo dropped on
    top (dark or light) sits on a clean, consistent hex badge, same
    idea as the reference scoreboard template's logo hexagons."""
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.polygon(_hexagon_points(size), fill=_hex_to_rgb(border_hex))
    draw.polygon(_hexagon_points(size, inset=size[0] * 0.06), fill=_hex_to_rgb(fill_hex))
    return img


def _initials_avatar(name: str, size=(170, 170)):
    """Fallback when a crest URL is missing or fails to download — a
    colored hexagon badge with the team's initials, so the card never
    just shows a blank gap where a badge should be."""
    initials = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    idx = sum(ord(c) for c in name) % len(_AVATAR_PALETTE)
    color = _AVATAR_PALETTE[idx]
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.polygon(_hexagon_points(size), fill=_hex_to_rgb(color))
    font = _font(int(size[1] * 0.4))
    w = _text_w(draw, initials, font)
    draw.text(((size[0] - w) / 2, size[1] * 0.28), initials, font=font, fill=WHITE)
    return img


def _crest_or_avatar(url: str, name: str, size=(170, 170)):
    crest = _fetch_crest(url, size)
    if crest is not None:
        # Hexagon badge frame behind the crest so logos on transparent
        # PNGs (dark or light) both sit on a consistent, clean hex
        # badge instead of a plain circle.
        badge = _hex_badge_frame(size)
        cx = (size[0] - crest.width) // 2
        cy = (size[1] - crest.height) // 2
        badge.paste(crest, (cx, cy), crest)
        return badge
    return _initials_avatar(name, size)


# ══════════════════════════════════════════════════════════════════
# GENERIC CARD — VAR, transfer flashback, top scorers, win probability
# ══════════════════════════════════════════════════════════════════

def render_card(kind: str, marker: str, title: str, lines: list, source: str = None) -> str:
    """`marker` is accepted for backwards compatibility with existing
    call sites but is intentionally unused for on-image rendering
    (see module docstring) — the badge pill below replaces it."""
    img, draw = _base_canvas(kind)
    W, H = CARD_SIZE
    badge_text, accent = BADGES.get(kind, BADGES["default"])
    badge_bottom = _draw_badge_pill(draw, badge_text, accent)

    y = badge_bottom + 50
    title_font = _font(56)
    for line in textwrap.wrap(title, width=22):
        _shadow_text(draw, (60, y), line, title_font, fill=WHITE)
        y += 68

    y += 24
    # Ranked-list detection ("1. Player - 6") gets a numbered chip;
    # everything else gets a small square bullet. Both read as
    # intentional list styling instead of raw wrapped paragraphs.
    body_font = _font(38)
    for i, line in enumerate(lines):
        rank = None
        rest = line
        parts = line.split(".", 1)
        if len(parts) == 2 and parts[0].strip().isdigit():
            rank, rest = parts[0].strip(), parts[1].strip()

        chip_x = 60
        if rank:
            chip_d = 46
            draw.ellipse([chip_x, y - 4, chip_x + chip_d, y - 4 + chip_d], fill=GOLD)
            rw = _text_w(draw, rank, body_font)
            draw.text((chip_x + (chip_d - rw) / 2, y - 2), rank, font=body_font, fill=INK)
            text_x = chip_x + chip_d + 20
        else:
            draw.rectangle([chip_x, y + 14, chip_x + 14, y + 28], fill=GOLD)
            text_x = chip_x + 34

        for j, wrapped in enumerate(textwrap.wrap(rest, width=26) or [""]):
            draw.text((text_x, y + j * 46), wrapped, font=body_font, fill=WHITE)
        y += max(54, 46 * len(textwrap.wrap(rest, width=26) or [""])) + 16

    if source:
        draw.text((60, y + 10), f"Source: {source}", font=_font(26), fill="#D1D5DB")

    _draw_brand_ribbon(img, draw)
    return _save(img)


# ══════════════════════════════════════════════════════════════════
# SCORE CARD — kickoff / goal / fulltime, with crest logos (or
# initials-avatar fallback so a missing crest never leaves a gap)
# ══════════════════════════════════════════════════════════════════

def render_score_card(kind: str, marker: str, home_name: str, away_name: str,
                       home_score, away_score, event_line: str = "",
                       home_crest_url: str = "", away_crest_url: str = "") -> str:
    img, draw = _base_canvas(kind)
    W, H = CARD_SIZE
    badge_text, accent = BADGES.get(kind, BADGES["default"])
    _draw_badge_pill(draw, badge_text, accent)
    _draw_wordmark(draw, xy=(W - 300, 62))

    crest_size = (190, 190)
    crest_y = 260
    home_crest = _crest_or_avatar(home_crest_url, home_name, crest_size)
    away_crest = _crest_or_avatar(away_crest_url, away_name, crest_size)
    img.paste(home_crest, (110, crest_y), home_crest)
    img.paste(away_crest, (W - 110 - crest_size[0], crest_y), away_crest)
    draw = ImageDraw.Draw(img)

    # Scoreline inside an angular ribbon badge (pointed ends) instead of
    # a plain rounded chip — the same broadcast-scoreboard styling used
    # across the premium cards, so it reads as a designed banner.
    score_text = f"{home_score}  -  {away_score}"
    score_font = _font(90)
    _draw_ribbon_badge(draw, W / 2, crest_y + 95, score_text, score_font,
                        fill="#0B0F0C", text_color=WHITE, pad_x=48, pad_y=18, notch=26)

    # Thin divider under the crests to visually separate identity from
    # the event line below, like a real scoreboard graphic.
    name_font = _font(34)
    for name, cx in ((home_name, 205), (away_name, W - 205)):
        ty = crest_y + crest_size[1] + 26
        for i, line in enumerate(textwrap.wrap(name, width=14)[:2]):
            lw = _text_w(draw, line, name_font)
            draw.text((cx - lw / 2, ty + i * 42), line, font=name_font, fill=WHITE)

    divider_y = crest_y + crest_size[1] + 120
    draw.line([(120, divider_y), (W - 120, divider_y)], fill=(255, 255, 255, 90), width=2)

    if event_line:
        ev_font = _font(44)
        y = divider_y + 34
        for raw_line in event_line.split("\n"):
            for line in textwrap.wrap(raw_line, width=30) or [""]:
                lw = _text_w(draw, line, ev_font)
                _shadow_text(draw, ((W - lw) / 2, y), line, ev_font, fill=GOLD)
                y += 54

    _draw_brand_ribbon(img, draw)
    return _save(img)


def _spaced_text(draw, xy, text, font, fill, tracking=6):
    """Draws text with extra letter-spacing (Pillow has no native
    tracking control) — this is what makes a header like
    'INTERNATIONAL FRIENDLY' read as sleek/broadcast instead of a
    plain wrapped string."""
    x, y = xy
    for ch in text:
        draw.text((x, y), ch, font=font, fill=fill)
        x += _text_w(draw, ch, font) + tracking
    return x  # right edge, if the caller needs it


def _stadium_canvas(accent_key: str):
    """Night-stadium backdrop: soft floodlight glows, a dark vignette,
    and a faint blurred pitch texture — built entirely with Pillow
    (gradients + gaussian blur), so it's instant, free, and has zero
    risk of hallucinated text/flags the way a generative image would.
    """
    W, H = CARD_SIZE
    base_dark = (10, 14, 12)
    img = Image.new("RGB", CARD_SIZE, base_dark)

    # Floodlight glows — a few large soft-edged bright ellipses, blurred
    # heavily, positioned like stadium floodlights from above.
    glow_layer = Image.new("RGB", CARD_SIZE, (0, 0, 0))
    gdraw = ImageDraw.Draw(glow_layer)
    accent_rgb = _hex_to_rgb(ACCENTS.get(accent_key, ACCENTS["default"]))
    for cx, cy, r, color in [
        (170, 60, 260, (255, 244, 214)),
        (W - 170, 60, 260, tuple(min(255, c + 60) for c in accent_rgb)),
        (W // 2, H + 80, 520, accent_rgb),
    ]:
        gdraw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=color)
    glow_layer = glow_layer.filter(ImageFilter.GaussianBlur(120))
    img = Image.blend(img, glow_layer, 0.55)

    # Faint blurred "pitch" texture along the bottom third — soft
    # diagonal stripes suggesting mown grass, kept subtle so it never
    # competes with the scoreboard.
    pitch = Image.new("RGB", CARD_SIZE, base_dark)
    pdraw = ImageDraw.Draw(pitch)
    stripe_w = 70
    for i, x in enumerate(range(-H, W, stripe_w)):
        shade = (20, 46, 30) if i % 2 == 0 else (16, 38, 24)
        pdraw.polygon([(x, H), (x + H, 0), (x + H + stripe_w, 0), (x + stripe_w, H)], fill=shade)
    pitch = pitch.filter(ImageFilter.GaussianBlur(8))
    mask = Image.new("L", CARD_SIZE, 0)
    mdraw = ImageDraw.Draw(mask)
    mdraw.rectangle([0, int(H * 0.62), W, H], fill=140)
    img = Image.composite(pitch, img, mask)

    # Dark vignette so the edges recede and the scoreboard stays the
    # clear focal point.
    vignette = Image.new("L", CARD_SIZE, 0)
    vdraw = ImageDraw.Draw(vignette)
    vdraw.ellipse([-260, -260, W + 260, H + 260], fill=255)
    vignette = vignette.filter(ImageFilter.GaussianBlur(180))
    black = Image.new("RGB", CARD_SIZE, (0, 0, 0))
    img = Image.composite(img, black, vignette)

    # Crisp floodlight beam fans on top of the soft glow blobs above —
    # this is the detail that reads as "broadcast template" rather
    # than "gradient with blur", matching a proper stadium scoreboard.
    img = _draw_light_rays(img, n_rays=7, spread=52, max_alpha=22)

    return img, ImageDraw.Draw(img)


def render_score_card_premium(kind: str, home_name: str, away_name: str,
                               home_score, away_score, competition: str = "",
                               event_line: str = "", status_label: str = "",
                               show_pulse: bool = False,
                               home_crest_url: str = "", away_crest_url: str = "") -> str:
    """
    Stadium-night styled variant of render_score_card — same exact,
    instantly-computed score/scorer text (no generative model in the
    loop, so nothing here can misspell a name or draw a wrong flag),
    just a more premium/cinematic backdrop for kickoff/goal/full-time.

    status_label examples: "KICK-OFF", "72' \u2022 LIVE", "FULL TIME (AET)".
    show_pulse draws the small red live-dot — use for kickoff/goal,
    leave off for full-time.
    """
    img, draw = _stadium_canvas(kind)
    W, H = CARD_SIZE

    if competition:
        header_font = _font(28)
        header = competition.upper()
        hw_est = sum(_text_w(draw, c, header_font) + 6 for c in header)
        _spaced_text(draw, ((W - hw_est) / 2, 56), header, header_font, "#D4AF6A", tracking=6)

    if status_label:
        font = _font(26)
        label_text = f"\u25CF {status_label}" if show_pulse else status_label
        badge_w, badge_h = _draw_ribbon_badge(
            draw, W / 2, 128, label_text, font,
            fill="#0B0F0C", text_color=WHITE, pad_x=30, pad_y=12, notch=16,
        )
        if show_pulse:
            # Recolor just the pulse dot glyph red by overdrawing a small
            # circle in place of the plain-text bullet drawn above.
            dot_x = W / 2 - _text_w(draw, label_text, font) / 2 + 4
            draw.ellipse([dot_x, 118, dot_x + 18, 136], fill="#EF4444")

    crest_size = (200, 200)
    crest_y = 230
    home_crest = _crest_or_avatar(home_crest_url, home_name, crest_size)
    away_crest = _crest_or_avatar(away_crest_url, away_name, crest_size)
    img.paste(home_crest, (120, crest_y), home_crest)
    img.paste(away_crest, (W - 120 - crest_size[0], crest_y), away_crest)
    draw = ImageDraw.Draw(img)

    score_text = f"{home_score}   -   {away_score}"
    score_font = _font(110)
    tw = _text_w(draw, score_text, score_font)
    _shadow_text(draw, ((W - tw) / 2, crest_y + 50), score_text, score_font, fill=WHITE, offset=(0, 6))

    name_font = _font(34)
    for name, cx in ((home_name, 220), (away_name, W - 220)):
        ty = crest_y + crest_size[1] + 20
        for i, line in enumerate(textwrap.wrap(name, width=14)[:2]):
            lw = _text_w(draw, line, name_font)
            draw.text((cx - lw / 2, ty + i * 42), line, font=name_font, fill=WHITE)

    if event_line:
        ev_font = _font(40)
        y = crest_y + crest_size[1] + 150
        for raw_line in event_line.split("\n"):
            for line in textwrap.wrap(raw_line, width=34) or [""]:
                lw = _text_w(draw, line, ev_font)
                _shadow_text(draw, ((W - lw) / 2, y), line, ev_font, fill="#D4AF6A")
                y += 50

    _draw_brand_ribbon(img, draw)
    return _save(img)




# ══════════════════════════════════════════════════════════════════
# SCOREBOARD CARD — flat navy/cyan "match-result" template style
# (kickoff / goal / full-time). This is the requested redesign:
# solid navy background, one loud accent color reserved for the
# score container, real bold type instead of Pillow's default font.
# ══════════════════════════════════════════════════════════════════

SCOREBOARD_NAVY_TOP    = "#152B6B"
SCOREBOARD_NAVY_BOTTOM = "#0C1B4A"
SCOREBOARD_INK         = "#0B1E4D"   # score text color (dark navy on bright accent)

# One bright accent per card kind — this is the ONLY loud color on the
# card (everything else is navy/white), which is exactly what makes
# the reference template's score hexagon pop instead of blending in.
SCOREBOARD_ACCENTS = {
    "default":   "#3FD3E8",
    "kickoff":   "#3FD3E8",   # bright cyan
    "goal":      "#FFC93C",   # bright gold
    "fulltime":  "#3FD3E8",
    "var":       "#FF5C5C",   # bright red
    "transfer":  "#FF8A3D",   # bright orange
    "manager":   "#3FD3E8",
    "worldcup":  "#3FD3E8",
    "interview": "#C084FC",
    "stats":     "#818CF8",
}

SCOREBOARD_HEADERS = {
    "default":  ("MATCH UPDATE", ""),
    "kickoff":  ("MATCH UPDATE", "KICK-OFF"),
    "goal":     ("MATCH UPDATE", "GOAL"),
    "fulltime": ("MATCH RESULT", "FULL TIME"),
    "var":      ("MATCH UPDATE", "VAR REVIEW"),
}


def _scoreboard_canvas(accent_hex: str):
    """Flat navy gradient + a very faint diagonal chevron texture —
    deliberately calm/flat (no floodlight rays, no vignette) so the
    score hexagon is the only thing competing for attention, the way
    a clean template card reads instead of a busy broadcast graphic."""
    W, H = CARD_SIZE
    top = _hex_to_rgb(SCOREBOARD_NAVY_TOP)
    bottom = _hex_to_rgb(SCOREBOARD_NAVY_BOTTOM)
    img = Image.new("RGB", CARD_SIZE, top)
    draw = ImageDraw.Draw(img)
    for y in range(H):
        t = y / H
        row = tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        draw.line([(0, y), (W, y)], fill=row)

    # Faint diagonal stripes, very low opacity — a texture cue, not a
    # pattern that competes with the foreground like the reference.
    stripe = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    sdraw = ImageDraw.Draw(stripe)
    step = 64
    for x in range(-H, W, step):
        sdraw.line([(x, H), (x + H, 0)], fill=(255, 255, 255, 12), width=18)
    img = Image.alpha_composite(img.convert("RGBA"), stripe).convert("RGB")
    return img, ImageDraw.Draw(img)


def _draw_score_hexagon(img, draw, cx: float, cy: float, home_score, away_score,
                         accent_hex: str, w: int = 640, h: int = 300):
    """The wide, pointed-left/right hexagon that holds the scoreline —
    the single loud-color focal point of the card."""
    box = (int(w), int(h))
    hexlayer = Image.new("RGBA", box, (0, 0, 0, 0))
    hdraw = ImageDraw.Draw(hexlayer)
    hdraw.polygon(_hexagon_points(box, orientation="horizontal"), fill=_hex_to_rgb(accent_hex))
    img.paste(hexlayer, (int(cx - w / 2), int(cy - h / 2)), hexlayer)
    draw = ImageDraw.Draw(img)

    score_text = f"{home_score} - {away_score}"
    score_font = _font(120, "extrabold")
    tw = _text_w(draw, score_text, score_font)
    ascent, descent = score_font.getmetrics()
    draw.text((cx - tw / 2, cy - (ascent + descent) / 2 - 6), score_text,
              font=score_font, fill=SCOREBOARD_INK)
    return draw


def render_scoreboard_card(kind: str, home_name: str, away_name: str,
                            home_score, away_score, competition: str = "",
                            event_line: str = "", status_label: str = "",
                            home_crest_url: str = "", away_crest_url: str = "",
                            show_pulse: bool = False) -> str:
    """
    Match-result template card for kickoff / goal / full-time — solid
    navy background, one bright accent color reserved for the score
    hexagon, real Poppins weights instead of Pillow's thin default
    font. Layout mirrors a clean scoreboard template: two-tier header,
    team crest + score hexagon + team crest in a row, team names under
    the crests, optional event line (goal scorer/minute) below, brand
    footer at the bottom.
    """
    accent = SCOREBOARD_ACCENTS.get(kind, SCOREBOARD_ACCENTS["default"])
    img, draw = _scoreboard_canvas(accent)
    W, H = CARD_SIZE

    top_line, bottom_line = SCOREBOARD_HEADERS.get(kind, SCOREBOARD_HEADERS["default"])
    if status_label:
        bottom_line = status_label

    header_font = _font(50, "extrabold")
    header_text = top_line
    hw = _text_w(draw, header_text, header_font)
    draw.text((W / 2 - hw / 2, 64), header_text, font=header_font, fill="#FFFFFF")

    if bottom_line:
        sub_font = _font(30, "semibold")
        sub_text = bottom_line
        sw = sum(_text_w(draw, c, sub_font) + 5 for c in sub_text)
        _spaced_text(draw, (W / 2 - sw / 2, 134), sub_text, sub_font, accent, tracking=5)

    if competition:
        comp_font = _font(24, "regular")
        comp_text = competition.upper()
        cw = _text_w(draw, comp_text, comp_font)
        draw.text((W / 2 - cw / 2, 182), comp_text, font=comp_font, fill="#93A3D1")

    # Row: crest — hexagon score — crest. The hexagon is widest exactly
    # at its vertical center, which is also where the crests sit, so
    # there must be real clearance between crest-edge and hex-edge or
    # they visually collide — sized/positioned with a 40px gap on each
    # side to guarantee that.
    crest_size = (140, 140)
    row_cy = 420
    hex_w, hex_h = 560, 270
    crest_x_left = 90
    crest_x_right = W - 90 - crest_size[0]
    home_crest = _crest_or_avatar(home_crest_url, home_name, crest_size)
    away_crest = _crest_or_avatar(away_crest_url, away_name, crest_size)
    img.paste(home_crest, (crest_x_left, int(row_cy - crest_size[1] / 2)), home_crest)
    img.paste(away_crest, (crest_x_right, int(row_cy - crest_size[1] / 2)), away_crest)
    draw = ImageDraw.Draw(img)

    draw = _draw_score_hexagon(img, draw, W / 2, row_cy, home_score, away_score,
                                accent, w=hex_w, h=hex_h)

    # Team names under each crest
    name_font = _font(32, "semibold")
    for name, cx in ((home_name, crest_x_left + crest_size[0] / 2), (away_name, crest_x_right + crest_size[0] / 2)):
        ty = row_cy + crest_size[1] / 2 + 24
        lines = textwrap.wrap(name.upper(), width=13)[:2]
        for i, line in enumerate(lines):
            lw = _text_w(draw, line, name_font)
            draw.text((cx - lw / 2, ty + i * 38), line, font=name_font, fill="#FFFFFF")

    # Optional event line (e.g. "⚽ Player Name  73'") under the row
    if event_line:
        ev_font = _font(34, "semibold")
        y = row_cy + hex_h / 2 + 90
        for raw_line in event_line.split("\n"):
            for line in textwrap.wrap(raw_line, width=32) or [""]:
                lw = _text_w(draw, line, ev_font)
                draw.text((W / 2 - lw / 2, y), line, font=ev_font, fill="#FFFFFF")
                y += 44

    _draw_brand_ribbon_v2(img, draw, accent)
    return _save(img)


def _draw_brand_ribbon_v2(img, draw, accent_hex: str):
    """Footer bar matching the scoreboard template's flat bottom band —
    solid dark navy strip, brand name in the accent color, tagline in
    light gray, both in real Poppins weights."""
    W, H = img.size
    ribbon_h = 76
    band = Image.new("RGBA", (W, ribbon_h), (*_hex_to_rgb(SCOREBOARD_NAVY_BOTTOM), 235))
    img.paste(Image.alpha_composite(img.crop((0, H - ribbon_h, W, H)).convert("RGBA"), band), (0, H - ribbon_h))
    draw = ImageDraw.Draw(img)
    draw.text((44, H - ribbon_h + 14), BRAND_NAME, font=_font(28, "extrabold"), fill=accent_hex)
    draw.text((44, H - ribbon_h + 46), BRAND_TAGLINE, font=_font(20, "regular"), fill="#C7D0E8")
    return draw


# Two thresholds instead of one hard cutoff:
#  >= STANDARD_MIN         -> crisp, full-detail treatment
#  HARD_MIN..STANDARD_MIN  -> "standard" treatment: a mild blur pass
#                             smooths blocky upscaling artifacts, then
#                             an unsharp mask restores perceived edge
#                             crispness — the same soften-then-sharpen
#                             trick used to clean up any low-res photo.
#                             Still a real photo, just not pin-sharp.
#  <  HARD_MIN             -> too small/likely an icon — generated
#                             card is more honest than a mangled photo
HARD_MIN = 150
STANDARD_MIN = 480


def render_photo_card(kind: str, headline: str, image_url: str,
                       source: str = None, sub_line: str = None) -> str | None:
    """
    Builds a branded card from a REAL photo pulled from the news
    source (e.g. the player/club photo attached to the ESPN/BBC/Sky
    article), instead of a text-only generated card. This is what
    transfer-news posts should use: people want to see who the player
    is, and a solid-color text card can't show that.

    Returns None only if the image can't be downloaded/decoded, or is
    below HARD_MIN in its shortest dimension — the caller should fall
    back to render_card() in that case. Anything above HARD_MIN gets
    used (see tiers above), so a small-but-real photo is still
    preferred over a fallback text card whenever reasonably possible.
    """
    photo = _fetch_image(image_url)
    if photo is None:
        return None
    source_dim = min(photo.size)
    if source_dim < HARD_MIN:
        print(f"[GRAPHICS] Source image {photo.size} below {HARD_MIN}px — using generated card instead")
        return None
    needs_softening = source_dim < STANDARD_MIN
    if needs_softening:
        print(f"[GRAPHICS] Source image {photo.size} below {STANDARD_MIN}px — using standard-quality treatment")

    W, H = CARD_SIZE
    # Center-crop to a square so any source aspect ratio fills the card
    # without letterboxing, then upscale/downscale to CARD_SIZE.
    pw, ph = photo.size
    side = min(pw, ph)
    left = (pw - side) // 2
    top = (ph - side) // 2
    photo = photo.crop((left, top, left + side, top + side)).resize(CARD_SIZE, Image.LANCZOS)

    if needs_softening:
        # Soften-then-sharpen: a light blur smooths the blocky edges an
        # upscale produces from a small source, then an unsharp mask
        # brings back perceived edge crispness on top of the smoothed
        # base — a real photo that reads as "acceptable web quality"
        # rather than visibly pixelated.
        photo = photo.filter(ImageFilter.GaussianBlur(1.4))
        photo = photo.filter(ImageFilter.UnsharpMask(radius=2, percent=130, threshold=2))

    photo = photo.convert("RGBA")

    # Bottom-weighted gradient so the headline block is always legible
    # regardless of how bright/busy the source photo is, while the top
    # of the photo (the player's face) stays untouched. Slightly darker
    # overall on the standard tier — a touch more shadow helps hide any
    # remaining softness without hiding the subject.
    base_darken = 40 if needs_softening else 0
    if base_darken:
        dark = Image.new("RGBA", CARD_SIZE, (0, 0, 0, base_darken))
        photo = Image.alpha_composite(photo, dark)
    overlay = Image.new("RGBA", CARD_SIZE, (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)
    for y in range(H):
        t = max(0, (y - H * 0.40) / (H * 0.60))
        alpha = int(220 * t)
        if alpha > 0:
            odraw.line([(0, y), (W, y)], fill=(0, 0, 0, alpha))
    img = Image.alpha_composite(photo, overlay)
    draw = ImageDraw.Draw(img)

    badge_text, accent = BADGES.get(kind, BADGES["transfer"])
    _draw_badge_pill(draw, badge_text, accent)

    title_font = _font(52)
    y = H - 250
    wrapped_lines = textwrap.wrap(headline, width=28)[:4]
    y -= 68 * (len(wrapped_lines) - 1)
    for line in wrapped_lines:
        _shadow_text(draw, (60, y), line, title_font, fill=WHITE)
        y += 68

    if sub_line:
        draw.text((60, y + 6), sub_line, font=_font(30), fill=GOLD)

    _draw_brand_ribbon(img, draw)
    return _save(img)
