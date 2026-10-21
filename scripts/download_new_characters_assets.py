"""Download official assets for the 14 new characters (Four Saints, Six Dragons, Primal Beasts)."""

import io
import urllib.request
from pathlib import Path
from PIL import Image

NEW_CHARS = {
    # 四圣 (Four Saints)
    "chichiri": {
        "id": "3040525000",
        "bg_color": (115, 30, 45),  # Zhuque vermilion/rose
    },
    "uruki": {
        "id": "3040526000",
        "bg_color": (25, 45, 80),   # Xuanwu deep teal/navy
    },
    "shushuku": {
        "id": "3040527000",
        "bg_color": (95, 65, 30),   # Baihu amber sand
    },
    "ami": {
        "id": "3040528000",
        "bg_color": (25, 75, 50),   # Qinglong emerald green
    },
    # 六龙 (Six Dragons)
    "wilnas": {
        "id": "3040381000",
        "bg_color": (120, 25, 25),  # Fire crimson
    },
    "wamdus": {
        "id": "3040419000",
        "bg_color": (20, 70, 95),   # Water cyan
    },
    "galleon": {
        "id": "3040405000",
        "bg_color": (85, 55, 30),   # Earth amber
    },
    "ewiyar": {
        "id": "3040452000",
        "bg_color": (20, 75, 45),   # Wind emerald
    },
    "luwoh": {
        "id": "3040449000",
        "bg_color": (95, 80, 30),   # Light golden
    },
    "fediel": {
        "id": "3040376000",
        "bg_color": (55, 25, 70),   # Dark onyx purple
    },
    # 星晶兽 (Primal Beasts)
    "yggdrasil": {
        "id": "3040125000",
        "bg_color": (50, 75, 35),   # Forest green
    },
    "europa": {
        "id": "3040190000",
        "bg_color": (30, 65, 95),   # Holy spring azure
    },
    "brodia": {
        "id": "3040158000",
        "bg_color": (65, 40, 25),   # Blade of steel earth
    },
    "grimnir": {
        "id": "3040212000",
        "bg_color": (25, 60, 90),   # Raging gale blue
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

    for cid, conf in NEW_CHARS.items():
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

    print("\nAll 14 new character visual assets downloaded and processed successfully!")

if __name__ == "__main__":
    main()
