"""Prepare GBF characters, sheets, facts, avatars, backgrounds, readings, and gifts."""

import json
import shutil
import urllib.request
from io import BytesIO
from pathlib import Path
from PIL import Image

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def download_image(url: str) -> Image.Image:
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return Image.open(BytesIO(resp.read()))

def prepare_assets():
    print("=== 1. 备份原角色配置 ===")
    sc_bak = Path("characters/characters.sc.toml.bak")
    if not sc_bak.exists():
        shutil.copy("characters/characters.toml", sc_bak)
        print("已备份 characters.toml 为 characters.sc.toml.bak")

    print("\n=== 2. 下载并生成高画质头像与背景 ===")
    avatars_dir = Path("characters/avatars")
    bgs_dir = Path("characters/backgrounds")
    avatars_dir.mkdir(parents=True, exist_ok=True)
    bgs_dir.mkdir(parents=True, exist_ok=True)

    # 娜露梅：Dark SSR 3040063000
    # 维卡拉：Dark SSR 3040252000
    chars = [
        {
            "id": "narmaya",
            "cdn_m": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/m/3040063000_01.jpg",
            "cdn_zoom": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040063000_01.png",
            "bg_color": (32, 22, 45),
        },
        {
            "id": "vikala",
            "cdn_m": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/m/3040252000_01.jpg",
            "cdn_zoom": "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/img/sp/assets/npc/zoom/3040252000_01.png",
            "bg_color": (45, 35, 20),
        }
    ]

    for c in chars:
        cid = c["id"]
        avatar_path = avatars_dir / f"{cid}.jpg"
        bg_path = bgs_dir / f"{cid}.jpg"

        print(f"处理 {cid} 头像...")
        m_img = download_image(c["cdn_m"]).convert("RGB")
        # Resize/crop to 224x224
        w, h = m_img.size
        min_dim = min(w, h)
        left = (w - min_dim) // 2
        top = 0
        crop_box = (left, top, left + min_dim, top + min_dim)
        avatar_img = m_img.crop(crop_box).resize((224, 224), Image.Resampling.LANCZOS)
        avatar_img.save(avatar_path, "JPEG", quality=85)
        print(f"  头像已保存: {avatar_path} ({avatar_path.stat().st_size // 1024} KB)")

        print(f"处理 {cid} 背景图...")
        zoom_img = download_image(c["cdn_zoom"]).convert("RGBA")
        # Create 1200x800 background canvas with gradient/tint and character art
        bg_canvas = Image.new("RGBA", (1200, 800), c["bg_color"] + (255,))
        # Scale zoom_img to fit height
        zw, zh = zoom_img.size
        target_h = 800
        target_w = int(zw * (target_h / zh))
        scaled_zoom = zoom_img.resize((target_w, target_h), Image.Resampling.LANCZOS)
        # Paste centered/right aligned
        bg_canvas.paste(scaled_zoom, (1200 - target_w + 50, 0), scaled_zoom.split()[3])
        bg_rgb = bg_canvas.convert("RGB")
        bg_rgb.save(bg_path, "JPEG", quality=82)
        print(f"  背景已保存: {bg_path} ({bg_path.stat().st_size // 1024} KB)")

def main():
    prepare_assets()
    print("\n=== 素材准备完成！ ===")

if __name__ == "__main__":
    main()
