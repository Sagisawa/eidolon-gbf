#!/usr/bin/env python3
"""Download and process official visual assets for the 13 new characters:
azusa, orchid, zeta, meg, marippe, zooey, ilsa, tikoh, cupitan, cagliostro, vira, vampy, lyria.
"""

import io
import urllib.request
from pathlib import Path
from PIL import Image

HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}

ASSETS = {
    "azusa": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040359000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040359000_01.png",
        "bg_color": (50, 25, 35),
    },
    "orchid": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040111000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040111000_01.png",
        "bg_color": (35, 32, 55),
    },
    "zeta": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040028000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040028000_01.png",
        "bg_color": (65, 20, 20),
    },
    "meg": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040346000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040346000_01.png",
        "bg_color": (25, 55, 70),
    },
    "marippe": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040482000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040482000_01.png",
        "bg_color": (70, 45, 20),
    },
    "zooey": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040092000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040092000_01.png",
        "bg_color": (20, 38, 65),
    },
    "ilsa": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040148000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040148000_01.png",
        "bg_color": (55, 40, 30),
    },
    "tikoh": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040337000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040337000_01.png",
        "bg_color": (30, 55, 50),
    },
    "cupitan": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040379000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040379000_01.png",
        "bg_color": (25, 50, 75),
    },
    "cagliostro": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040009000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040009000_01.png",
        "bg_color": (70, 35, 50),
    },
    "vira": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040141000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040141000_01.png",
        "bg_color": (50, 20, 50),
    },
    "vampy": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040057000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040057000_01.png",
        "bg_color": (65, 20, 35),
    },
    "lyria": {
        "av_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3030182000_01.jpg",
        "zm_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3030182000_01.png",
        "bg_color": (25, 60, 85),
    },
}


def download(url: str) -> bytes:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as resp:
        return resp.read()


def main():
    av_dir = Path("characters/avatars")
    bg_dir = Path("characters/backgrounds")
    av_dir.mkdir(parents=True, exist_ok=True)
    bg_dir.mkdir(parents=True, exist_ok=True)

    for cid, conf in ASSETS.items():
        print(f"Downloading & processing {cid}...")
        # 1. Avatar (224x224, < 32KB)
        av_bytes = download(conf["av_url"])
        im_av = Image.open(io.BytesIO(av_bytes)).convert("RGB")
        im_av = im_av.resize((224, 224), Image.Resampling.LANCZOS)
        av_out = av_dir / f"{cid}.jpg"
        im_av.save(av_out, "JPEG", quality=85)
        av_size = av_out.stat().st_size
        print(f"  Avatar: {av_out} ({av_size / 1024:.1f} KB)")
        assert av_size <= 32768, f"Avatar {cid} exceeds 32KB: {av_size}"

        # 2. Background (1200x800 canvas with zoom overlay, < 150KB)
        zm_bytes = download(conf["zm_url"])
        im_zm = Image.open(io.BytesIO(zm_bytes)).convert("RGBA")
        bg_rgb = conf["bg_color"]
        canvas = Image.new("RGBA", (1200, 800), bg_rgb + (255,))

        ratio = 760 / im_zm.height
        new_w = int(im_zm.width * ratio)
        new_h = int(im_zm.height * ratio)
        im_scaled = im_zm.resize((new_w, new_h), Image.Resampling.LANCZOS)

        paste_x = (1200 - new_w) // 2
        paste_y = 800 - new_h
        canvas.paste(im_scaled, (paste_x, paste_y), im_scaled)

        bg_out = bg_dir / f"{cid}.jpg"
        canvas.convert("RGB").save(bg_out, "JPEG", quality=80)
        bg_size = bg_out.stat().st_size
        print(f"  Background: {bg_out} ({bg_size / 1024:.1f} KB)")
        assert bg_size <= 150000, f"Background {cid} exceeds 150KB: {bg_size}"

    print("\nAll 13 character visual assets successfully downloaded, processed and verified!")


if __name__ == "__main__":
    main()
