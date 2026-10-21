#!/usr/bin/env python3
"""Download and generate authentic official GBF avatars and background illustrations
for all 11 Divine Generals from Cygames Akamai CDN.
"""

import urllib.request
from io import BytesIO
from pathlib import Path
from PIL import Image

ROOT = Path(__file__).resolve().parent.parent
AVATARS_DIR = ROOT / "characters" / "avatars"
BGS_DIR = ROOT / "characters" / "backgrounds"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

ZODIACS = [
    {
        "id": "anila",
        "asset_id": "3040040000",
        "bg_color": (48, 18, 18),
    },
    {
        "id": "andira",
        "asset_id": "3040071000",
        "bg_color": (16, 42, 22),
    },
    {
        "id": "mahira",
        "asset_id": "3040107000",
        "bg_color": (44, 32, 16),
    },
    {
        "id": "vajra",
        "asset_id": "3040147000",
        "bg_color": (14, 28, 52),
    },
    {
        "id": "kumbhira",
        "asset_id": "3040198000",
        "bg_color": (46, 28, 14),
    },
    {
        "id": "catura",
        "asset_id": "3040312000",
        "bg_color": (18, 34, 48),
    },
    {
        "id": "cindhara",
        "asset_id": "3040378000",
        "bg_color": (48, 22, 10),
    },
    {
        "id": "makora",
        "asset_id": "3040441000",
        "bg_color": (42, 16, 36),
    },
    {
        "id": "haira",
        "asset_id": "3040503000",
        "bg_color": (12, 32, 45),
    },
    {
        "id": "indara",
        "asset_id": "3040569000",
        "bg_color": (32, 14, 46),
    },
    {
        "id": "sanchira",
        "asset_id": "3040633000",
        "bg_color": (48, 16, 16),
    },
]

def download_image(url: str) -> Image.Image:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return Image.open(BytesIO(resp.read()))

def process_zodiac(z: dict):
    cid = z["id"]
    aid = z["asset_id"]
    bg_color = z["bg_color"]

    avatar_path = AVATARS_DIR / f"{cid}.jpg"
    bg_path = BGS_DIR / f"{cid}.jpg"

    s_url = f"https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/{aid}_01.jpg"
    zoom_url = f"https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/{aid}_01.png"

    print(f"Downloading avatar for [{cid}] ({aid})...")
    s_img = download_image(s_url).convert("RGB")
    # Resize 260x260 to 224x224
    avatar_img = s_img.resize((224, 224), Image.Resampling.LANCZOS)
    avatar_img.save(avatar_path, "JPEG", quality=85)
    print(f"  -> Saved avatar: {avatar_path.name} ({avatar_path.stat().st_size} bytes)")

    print(f"Downloading background artwork for [{cid}] ({aid})...")
    zoom_img = download_image(zoom_url).convert("RGBA")
    # Canvas (1200x800) with theme background
    bg_canvas = Image.new("RGBA", (1200, 800), bg_color + (255,))
    zw, zh = zoom_img.size
    target_h = 800
    target_w = int(zw * (target_h / zh))
    scaled_zoom = zoom_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
    # Right-aligned with padding
    bg_canvas.paste(scaled_zoom, (1200 - target_w + 50, 0), scaled_zoom.split()[3])
    bg_rgb = bg_canvas.convert("RGB")
    bg_rgb.save(bg_path, "JPEG", quality=82)
    print(f"  -> Saved background: {bg_path.name} ({bg_path.stat().st_size} bytes)")

def main():
    AVATARS_DIR.mkdir(parents=True, exist_ok=True)
    BGS_DIR.mkdir(parents=True, exist_ok=True)
    for z in ZODIACS:
        process_zodiac(z)
    print("\nAll 11 Zodiac avatars and backgrounds successfully downloaded and generated!")

if __name__ == "__main__":
    main()
