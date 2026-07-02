"""
transfers.py — Multi-source Transfer News & Image Engine
======================================================
Aggregates news, handles strict duplicate caching, strips links,
and automatically compiles graphical transfer cards for Facebook.
"""

import os
import re
import time
import requests
from PIL import Image, ImageDraw, ImageFont

# ── SYSTEM PATH SETUP (CROSS-PLATFORM SAFE) ───────────────────────
IMAGE_OUTPUT_DIR = os.path.join("images", "transfers")
CACHE_FILE = "transfer_cache.txt"
os.makedirs(IMAGE_OUTPUT_DIR, exist_ok=True)

FONT_NAME = "Arial.ttf"
try:
    FONT_PATH = os.path.join("assets", "fonts", "Roboto-Bold.ttf")
    if not os.path.exists(FONT_PATH):
        FONT_PATH = FONT_NAME
except Exception:
    FONT_PATH = FONT_NAME

ESPN_FEED = "https://site.api.espn.com/apis/site/v2/sports/soccer/news"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

def load_posted_cache() -> set:
    if not os.path.exists(CACHE_FILE):
        return set()
    with open(CACHE_FILE, "r", encoding="utf-8") as f:
        return set(line.strip() for line in f if line.strip())

def save_to_cache(story_id: str):
    with open(CACHE_FILE, "a", encoding="utf-8") as f:
        f.write(f"{story_id}\n")

def create_player_transfer_card(headline: str, description: str, output_filename: str) -> str | None:
    try:
        img = Image.new("RGB", (1200, 630), color=(15, 23, 42)) 
        draw = ImageDraw.Draw(img)
        
        try:
            title_font = ImageFont.truetype(FONT_PATH, 48)
            body_font = ImageFont.truetype(FONT_PATH, 28)
            brand_font = ImageFont.truetype(FONT_PATH, 24)
        except IOError:
            title_font = ImageFont.load_default()
            body_font = ImageFont.load_default()
            brand_font = ImageFont.load_default()

        draw.rectangle([0, 0, 1200, 15], fill=(234, 179, 8)) 
        draw.text((50, 40), "🔄 TRANSFER HUB DAILY", fill=(234, 179, 8), font=brand_font)
        draw.text((1000, 40), "SCORELINE LIVE", fill=(100, 116, 139), font=brand_font)

        words = headline.split()
        lines = []
        current_line = []
        for word in words:
            current_line.append(word)
            if len(" ".join(current_line)) > 40:
                current_line.pop()
                lines.append(" ".join(current_line))
                current_line = [word]
        lines.append(" ".join(current_line))

        y_cursor = 150
        for line in lines[:3]:
            draw.text((50, y_cursor), line.upper(), fill=(255, 255, 255), font=title_font)
            y_cursor += 65

        draw.line([(50, y_cursor + 20), (350, y_cursor + 20)], fill=(51, 65, 85), width=3)
        y_cursor += 50

        desc_words = description.split()
        desc_lines = []
        curr_desc = []
        for d_word in desc_words:
            curr_desc.append(d_word)
            if len(" ".join(curr_desc)) > 65:
                curr_desc.pop()
                desc_lines.append(" ".join(curr_desc))
                curr_desc = [d_word]
        desc_lines.append(" ".join(curr_desc))

        for d_line in desc_lines[:4]:
            draw.text((50, y_cursor), d_line, fill=(148, 163, 184), font=body_font)
            y_cursor += 40

        dest_path = os.path.join(IMAGE_OUTPUT_DIR, output_filename)
        img.save(dest_path, "JPEG", quality=95)
        return dest_path

    except Exception as e:
        print(f"[TRANSFERS] ❌ Image Compiler crashed: {e}")
        return None

# ── FIXED INTERFACE METHOD FOR BOT.PY ──────────────────────────────
def check_new() -> dict | None:
    """
    Core entry called by bot.py. Scrapes news, filters duplicates,
    strips links, and builds transfer graphics card payloads.
    """
    posted_cache = load_posted_cache()
    
    try:
        response = requests.get(ESPN_FEED, headers=HEADERS, timeout=10)
        if response.status_code != 200:
            return None
        
        data = response.json()
        articles = data.get("articles", [])
        
        for article in articles:
            story_id = str(article.get("id", "")) or str(hash(article.get("headline", "")))
            
            if story_id in posted_cache:
                continue
                
            headline = article.get("headline", "")
            description = article.get("description", article.get("images", [{}])[0].get("caption", ""))
            
            transfer_keywords = ["transfer", "sign", "deal", "bid", "loan", "agree", "medical", "fee", "contract"]
            is_transfer = any(kw in headline.lower() or kw in description.lower() for kw in transfer_keywords)
            
            if not is_transfer:
                continue
                
            # Strip links cleanly
            clean_description = re.sub(r'https?://\S+', '', description).strip()
            
            filename = f"transfer_{story_id}_{int(time.time())}.jpg"
            image_path = create_player_transfer_card(headline, clean_description, filename)
            
            if not image_path:
                continue
                
            save_to_cache(story_id)
            print(f"[TRANSFERS] 🔥 Fresh news found! Card saved at: {image_path}")
            
            return {
                "message": f"🚨 TRANSFER UPDATE 🚨\n\n⚽ {headline.upper()}\n\n📊 {clean_description}\n\n#Transfers #TransferNews #ScoreLineLive",
                "image_path": image_path
            }
            
    except Exception as e:
        print(f"[TRANSFERS] ⚠️ Exception encountered: {e}")
        
    return None
