"""Download official assets for the 9 remaining Arcarum Evokers."""

import io
import urllib.request
from pathlib import Path
from PIL import Image

EVOKERS = {
    "maria": {
        "id": "3040160000",
        "bg_color": (35, 60, 95),  # Deep justice navy blue
    },
    "fraux": {
        "id": "3040161000",
        "bg_color": (110, 30, 40),  # Devil crimson
    },
    "geisenborger": {
        "id": "3040162000",
        "bg_color": (45, 45, 55),  # Iron grey / star radiance
    },
    "estarriola": {
        "id": "3040163000",
        "bg_color": (40, 75, 60),  # Sage green
    },
    "caim": {
        "id": "3040164000",
        "bg_color": (95, 70, 45),  # Earth amber
    },
    "lobelia": {
        "id": "3040165000",
        "bg_color": (65, 30, 45),  # Tower dark magenta
    },
    "katzelia": {
        "id": "3040166000",
        "bg_color": (40, 70, 75),  # Teal judgement
    },
    "alanaan": {
        "id": "3040167000",
        "bg_color": (120, 50, 30),  # Solar fire orange
    },
    "haaselia": {
        "id": "3040168000",
        "bg_color": (35, 45, 80),  # Moonlight indigo
    },
}

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

def download_file(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()

def main():
    avatars_dir = Path("characters/avatars")
    backgrounds_dir = Path("characters/backgrounds")
    avatars_dir.mkdir(parents=True, exist_ok=True)
    backgrounds_dir.mkdir(parents=True, exist_ok=True)

    for cid, conf in EVOKERS.items():
        aid = conf["id"]
        bg_rgb = conf["bg_color"]

        av_url = f"https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/{aid}_01.jpg"
        zoom_url = f"https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/{aid}_01.png"

        print(f"Downloading {cid} ({aid})...")
        av_bytes = download_file(av_url)
        zoom_bytes = download_file(zoom_url)

        # 1. Process Avatar (strict 224x224, < 32KB)
        im_av = Image.open(io.BytesIO(av_bytes)).convert("RGB")
        im_av = im_av.resize((224, 224), Image.Resampling.LANCZOS)
        av_out = avatars_dir / f"{cid}.jpg"
        im_av.save(av_out, "JPEG", quality=85)
        av_size = av_out.stat().st_size
        print(f"  Avatar: {av_out} ({im_av.width}x{im_av.height}, {av_size/1024:.1f} KB)")
        assert av_size <= 32768, f"Avatar for {cid} too large: {av_size}"

        # 2. Process Background (1200x800 canvas with zoom overlay)
        im_zoom = Image.open(io.BytesIO(zoom_bytes)).convert("RGBA")
        canvas = Image.new("RGBA", (1200, 800), bg_rgb + (255,))

        # Scale zoom to fit nicely into 1200x800 height
        ratio = 760 / im_zoom.height
        new_w = int(im_zoom.width * ratio)
        new_h = int(im_zoom.height * ratio)
        im_scaled = im_zoom.resize((new_w, new_h), Image.Resampling.LANCZOS)

        # Paste centered horizontally, aligned towards bottom
        paste_x = (1200 - new_w) // 2
        paste_y = 800 - new_h
        canvas.paste(im_scaled, (paste_x, paste_y), im_scaled)

        bg_out = backgrounds_dir / f"{cid}.jpg"
        canvas.convert("RGB").save(bg_out, "JPEG", quality=85)
        bg_size = bg_out.stat().st_size
        print(f"  Background: {bg_out} ({canvas.width}x{canvas.height}, {bg_size/1024:.1f} KB)")

    print("\nAll 9 Evokers assets downloaded and processed successfully!")

if __name__ == "__main__":
    main()
