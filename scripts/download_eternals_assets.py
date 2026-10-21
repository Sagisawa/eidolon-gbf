#!/usr/bin/env python3
"""Download and generate canonical GBF avatars and background artwork
for all 10 Eternals (十天衆) from Cygames Akamai CDN.
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

ETERNALS = [
    {"id": "uno", "asset_id": "3040030000", "bg_color": (16, 28, 48)},
    {"id": "song", "asset_id": "3040031000", "bg_color": (32, 22, 48)},
    {"id": "sarasa", "asset_id": "3040032000", "bg_color": (46, 20, 18)},
    {"id": "quatre", "asset_id": "3040033000", "bg_color": (14, 38, 40)},
    {"id": "funf", "asset_id": "3040034000", "bg_color": (48, 42, 18)},
    {"id": "seox", "asset_id": "3040035000", "bg_color": (26, 16, 40)},
    {"id": "seofon", "asset_id": "3040036000", "bg_color": (18, 32, 46)},
    {"id": "eahta", "asset_id": "3040037000", "bg_color": (40, 24, 16)},
    {"id": "niyon", "asset_id": "3040038000", "bg_color": (16, 38, 28)},
    {"id": "tien", "asset_id": "3040039000", "bg_color": (46, 20, 24)},
]

def download_image(url: str) -> Image.Image:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return Image.open(BytesIO(resp.read()))

def process_eternal(e: dict):
    cid = e["id"]
    aid = e["asset_id"]
    bg_color = e["bg_color"]

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
    for e in ETERNALS:
        process_eternal(e)
    print("\nAll 10 Eternals avatars and backgrounds successfully downloaded and generated!")

if __name__ == "__main__":
    main()
