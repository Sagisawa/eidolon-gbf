"""Download official assets for the 9 Archangels / Astrals / Primarchs.
(Sandalphon, Lucifer, Lucilius, Lucio, Beelzebub, Belial, Helel ben Shalem, Raziel, Olivia)
"""

import io
import urllib.request
from pathlib import Path
from PIL import Image

CHARACTERS_ASSETS = {
    "sandalphon": {
        "zoom_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040153000_01.png",
        "avatar_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040153000_01.jpg",
        "bg_color": (35, 50, 75),  # Deep azure
    },
    "lucifer": {
        "zoom_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/summon/b/2040056000.png",
        "crop_avatar": (170, 60, 470, 360),
        "bg_color": (30, 45, 75),  # Celestial archangel white-blue
    },
    "lucilius": {
        "zoom_url": "https://gbf.wiki/images/d/d6/Npc_zoom_3991054000_01.png",
        "crop_avatar": (350, 0, 590, 240),
        "bg_color": (20, 15, 35),  # Dark Rapture midnight void
    },
    "lucio": {
        "zoom_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040106000_01.png",
        "avatar_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040106000_01.jpg",
        "bg_color": (60, 50, 20),  # Sahar golden amber
    },
    "beelzebub": {
        "zoom_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3991053000_01.png",
        "crop_avatar": (295, 0, 535, 240),
        "bg_color": (40, 15, 25),  # Chaos crimson
    },
    "belial": {
        "zoom_url": "https://gbf.wiki/images/4/4a/Npc_zoom_3991047000_01.png",
        "crop_avatar": (340, 30, 620, 310),
        "bg_color": (45, 20, 25),  # Decadent scarlet
    },
    "shalem": {
        "zoom_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040251000_01.png",
        "avatar_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040251000_01.jpg",
        "bg_color": (35, 20, 55),  # Dusk violet
    },
    "raziel": {
        "zoom_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040538000_01.png",
        "avatar_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040538000_01.jpg",
        "bg_color": (20, 50, 30),  # Wisdom emerald
    },
    "olivia": {
        "zoom_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040145000_01.png",
        "avatar_url": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/s/3040145000_01.jpg",
        "bg_color": (40, 20, 50),  # Fallen dark plum
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

    for cid, conf in CHARACTERS_ASSETS.items():
        bg_rgb = conf["bg_color"]

        print(f"Processing {cid}...")
        zoom_bytes = download_file(conf["zoom_url"])
        im_zoom = Image.open(io.BytesIO(zoom_bytes)).convert("RGBA")

        # 1. Process Avatar (strict 224x224, < 32KB)
        av_out = avatars_dir / f"{cid}.jpg"
        if "avatar_url" in conf:
            av_bytes = download_file(conf["avatar_url"])
            im_av = Image.open(io.BytesIO(av_bytes)).convert("RGB")
            im_av = im_av.resize((224, 224), Image.Resampling.LANCZOS)
            im_av.save(av_out, "JPEG", quality=85)
        else:
            crop_box = conf["crop_avatar"]
            im_face = im_zoom.crop(crop_box)
            bg = Image.new("RGB", (crop_box[2] - crop_box[0], crop_box[3] - crop_box[1]), bg_rgb)
            bg.paste(im_face, (0, 0), im_face)
            im_av = bg.resize((224, 224), Image.Resampling.LANCZOS)
            im_av.save(av_out, "JPEG", quality=85)

        av_size = av_out.stat().st_size
        print(f"  Avatar: {av_out} ({im_av.width}x{im_av.height}, {av_size/1024:.1f} KB)")
        assert av_size <= 32768, f"Avatar for {cid} exceeds 32KB: {av_size}"

        # 2. Process Background (1200x800 canvas with zoom overlay)
        canvas = Image.new("RGBA", (1200, 800), bg_rgb + (255,))
        ratio = 760 / im_zoom.height
        new_w = int(im_zoom.width * ratio)
        new_h = int(im_zoom.height * ratio)
        im_scaled = im_zoom.resize((new_w, new_h), Image.Resampling.LANCZOS)

        paste_x = (1200 - new_w) // 2
        paste_y = 800 - new_h
        canvas.paste(im_scaled, (paste_x, paste_y), im_scaled)

        bg_out = backgrounds_dir / f"{cid}.jpg"
        canvas.convert("RGB").save(bg_out, "JPEG", quality=80)
        bg_size = bg_out.stat().st_size
        print(f"  Background: {bg_out} ({canvas.width}x{canvas.height}, {bg_size/1024:.1f} KB)")
        assert bg_size <= 150000, f"Background for {cid} exceeds 150KB: {bg_size}"

    print("\nAll 9 Archangels/Astrals visual assets downloaded and processed successfully!")


if __name__ == "__main__":
    main()
