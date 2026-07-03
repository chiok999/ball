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
import textwrap
import requests
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageFilter

CARD_SIZE = (1080, 1080)
OUT_DIR = "cards"
os.makedirs(OUT_DIR, exist_ok=True)

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
    "stats":    "#312E81",  # indigo (World Cup filler cards)
}

# Badge (pill) style per category — drawn, never emoji.
BADGES = {
    "default":  ("MATCH UPDATE",  "#14532D"),
    "goal":     ("GOAL",          "#B45309"),
    "kickoff":  ("KICK-OFF",      "#15803D"),
    "fulltime": ("FULL TIME",     "#1E3A5F"),
    "var":      ("VAR REVIEW",    "#7A1F1F"),
    "transfer": ("BREAKING NEWS", "#C2410C"),
    "stats":    ("STATS",         "#4338CA"),
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


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont:
    # Pillow's scalable default font only ships one weight; we fake a
    # bolder look elsewhere via stroke_width rather than a second family,
    # so every card looks consistent without shipping font files.
    return ImageFont.load_default(size=size)


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


def _initials_avatar(name: str, size=(170, 170)):
    """Fallback when a crest URL is missing or fails to download — a
    colored circle with the team's initials, so the card never just
    shows a blank gap where a badge should be."""
    initials = "".join(w[0] for w in name.split()[:2]).upper() or "?"
    idx = sum(ord(c) for c in name) % len(_AVATAR_PALETTE)
    color = _AVATAR_PALETTE[idx]
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.ellipse([0, 0, size[0], size[1]], fill=_hex_to_rgb(color))
    font = _font(int(size[1] * 0.4))
    w = _text_w(draw, initials, font)
    draw.text(((size[0] - w) / 2, size[1] * 0.28), initials, font=font, fill=WHITE)
    return img


def _crest_or_avatar(url: str, name: str, size=(170, 170)):
    crest = _fetch_crest(url, size)
    if crest is not None:
        # White ring behind the crest so logos on transparent PNGs
        # (dark or light) both sit on a consistent, clean disc.
        ring = Image.new("RGBA", size, (0, 0, 0, 0))
        rdraw = ImageDraw.Draw(ring)
        rdraw.ellipse([0, 0, size[0], size[1]], fill=(255, 255, 255, 235))
        cx = (size[0] - crest.width) // 2
        cy = (size[1] - crest.height) // 2
        ring.paste(crest, (cx, cy), crest)
        return ring
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

    # Scoreline inside its own rounded chip so it reads as the focal
    # point rather than floating text on a gradient.
    score_text = f"{home_score}  -  {away_score}"
    score_font = _font(96)
    tw = _text_w(draw, score_text, score_font)
    chip_w, chip_h = tw + 90, 130
    chip_x = (W - chip_w) / 2
    chip_y = crest_y + 30
    draw.rounded_rectangle([chip_x, chip_y, chip_x + chip_w, chip_y + chip_h],
                            radius=24, fill=(0, 0, 0, 90))
    draw.text((chip_x + 45, chip_y + 14), score_text, font=score_font, fill=WHITE)

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
        pw = _text_w(draw, status_label, font) + (44 if show_pulse else 36)
        px = (W - pw) / 2
        draw.rounded_rectangle([px, 104, px + pw, 104 + 46], radius=23, fill=(0, 0, 0, 160))
        text_x = px + 16
        if show_pulse:
            draw.ellipse([px + 16, 122, px + 26, 132], fill="#EF4444")
            text_x = px + 36
        draw.text((text_x, 114), status_label, font=font, fill=WHITE)

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




def _draw_arrow(draw, x1, y, x2, color, width=4):
    """Simple vector arrow (line + triangle head) — deliberately not a
    unicode arrow glyph, since Aileron's coverage of those is spotty
    and an arrow rendered as a tofu box looks worse than no arrow."""
    draw.line([(x1, y), (x2 - 14, y)], fill=color, width=width)
    draw.polygon([(x2, y), (x2 - 16, y - 9), (x2 - 16, y + 9)], fill=color)


def render_transfer_flashback_card(player: str, from_club: str, to_club: str,
                                    fee_line: str, date_line: str = "") -> str:
    """
    Premium stadium-styled replacement for the old flat transfer-
    flashback card — matches the kickoff/goal/full-time look instead
    of feeling like a separate, more basic template. No live crests
    exist for this historical-dataset content, so both clubs get the
    colored initials-avatar treatment consistently.
    """
    img, draw = _stadium_canvas("transfer")
    W, H = CARD_SIZE

    header = "TRANSFER FLASHBACK"
    header_font = _font(28)
    hw_est = sum(_text_w(draw, c, header_font) + 6 for c in header)
    _spaced_text(draw, ((W - hw_est) / 2, 56), header, header_font, "#D4AF6A", tracking=6)

    club_size = (170, 170)
    club_y = 210
    from_avatar = _initials_avatar(from_club, club_size)
    to_avatar = _initials_avatar(to_club, club_size)
    img.paste(from_avatar, (140, club_y), from_avatar)
    img.paste(to_avatar, (W - 140 - club_size[0], club_y), to_avatar)
    draw = ImageDraw.Draw(img)
    _draw_arrow(draw, 140 + club_size[0] + 30, club_y + club_size[1] // 2,
                W - 140 - club_size[0] - 30, "#D4AF6A", width=6)

    name_font = _font(30)
    for name, cx in ((from_club, 225), (to_club, W - 225)):
        ty = club_y + club_size[1] + 18
        for i, line in enumerate(textwrap.wrap(name, width=15)[:2]):
            lw = _text_w(draw, line, name_font)
            draw.text((cx - lw / 2, ty + i * 38), line, font=name_font, fill=WHITE)

    player_font = _font(58)
    pw = _text_w(draw, player, player_font)
    _shadow_text(draw, ((W - pw) / 2, club_y + club_size[1] + 110), player, player_font, fill=WHITE)

    fee_font = _font(48)
    fw = _text_w(draw, fee_line, fee_font)
    _shadow_text(draw, ((W - fw) / 2, club_y + club_size[1] + 190), fee_line, fee_font, fill="#D4AF6A")

    if date_line:
        draw.text((60, H - 150), date_line, font=_font(26), fill="#B8BEC7")

    _draw_brand_ribbon(img, draw)
    return _save(img)


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
