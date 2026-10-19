"""Script to fetch authentic Granblue Fantasy scenario and voice data from BLHXFY and Akamai CDN."""

import json
import os
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

# Fix Windows stdout encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

BASE_API = "https://api.github.com/repos/BLHXFY-Group/BLHXFY/git/trees/master?recursive=1"
RAW_BASE = "https://raw.githubusercontent.com/BLHXFY-Group/BLHXFY/master/"
CDN_AUDIO_BASE = "https://prd-game-a-granbluefantasy.akamaized.net/assets_en/sound/"

CORPUS_DIR = Path("corpus/gbf")
AUDIO_DIR = Path("frontend/public/sounds/gbf")

def fetch_json(url: str):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))

def download_file(url: str, dest: Path) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        return False
    try:
        req = urllib.request.Request(url, headers=HEADERS)
        with urllib.request.urlopen(req, timeout=20) as resp, open(dest, "wb") as f:
            f.write(resp.read())
        return True
    except Exception as e:
        print(f"  [Error] Failed to download {url}: {e}")
        return False

def main():
    print("=== 1. 正在检索 BLHXFY 仓库索引 ===")
    tree_data = fetch_json(BASE_API)
    all_files = [item["path"] for item in tree_data.get("tree", []) if item["type"] == "blob"]
    print(f"仓库文件总数: {len(all_files)}")

    narmaya_files = []
    vikala_files = []

    for path in all_files:
        # Narmaya filters
        if any(k in path for k in ["暗-娜尔梅亚", "光-娜尔梅娅", "风-娜尔梅亚", "泳装娜尔梅亚"]) and path.endswith(".csv"):
            narmaya_files.append(path)
        # Vikala filters
        elif any(k in path for k in ["暗-碧卡拉", "光-碧卡拉", "水-碧卡拉"]) and path.endswith(".csv"):
            vikala_files.append(path)
        elif "201912 除夜の終わりに響く鐘" in path and path.endswith(".csv"):
            vikala_files.append(path)

    print(f"\n找到 娜露梅 原作剧本文件: {len(narmaya_files)} 个")
    print(f"找到 维卡拉 原作剧本文件: {len(vikala_files)} 个")

    # Download Narmaya files
    print("\n=== 2. 正在下载 娜露梅 原作剧本 ===")
    nar_dir = CORPUS_DIR / "narmaya"
    for idx, path in enumerate(narmaya_files, 1):
        filename = Path(path).name
        subfolder = Path(path).parent.name
        dest = nar_dir / subfolder / filename
        raw_url = RAW_BASE + urllib.parse.quote(path)
        downloaded = download_file(raw_url, dest)
        if downloaded:
            print(f"[{idx}/{len(narmaya_files)}] 下载: {subfolder}/{filename}")
        time.sleep(0.05)

    # Download Vikala files
    print("\n=== 3. 正在下载 维卡拉 原作剧本 ===")
    vik_dir = CORPUS_DIR / "vikala"
    for idx, path in enumerate(vikala_files, 1):
        filename = Path(path).name
        subfolder = Path(path).parent.name
        dest = vik_dir / subfolder / filename
        raw_url = RAW_BASE + urllib.parse.quote(path)
        downloaded = download_file(raw_url, dest)
        if downloaded:
            print(f"[{idx}/{len(vikala_files)}] 下载: {subfolder}/{filename}")
        time.sleep(0.05)

    # Download Sample Audio from CDN
    print("\n=== 4. 正在抓取官方原版语音示例（用于打招呼/音色） ===")
    # Narmaya sample: 3040063000_mypage1.mp3 (阳光不错呀…要不要和姐姐一起去晒太阳)
    # Vikala sample: 3040252000_mypage1.mp3 (呀！我是碧吉！状态怎么样？)
    samples = [
        ("narmaya_greeting.mp3", "voice/3040063000_mypage1.mp3"),
        ("vikala_greeting.mp3", "voice/3040252000_mypage1.mp3"),
    ]
    for filename, remote_path in samples:
        dest = AUDIO_DIR / filename
        url = CDN_AUDIO_BASE + remote_path
        print(f"下载原版语音: {url} -> {dest}")
        download_file(url, dest)

    print("\n=== 全部真实数据抓取完成！ ===")
    print(f"剧本保存至: {CORPUS_DIR.resolve()}")
    print(f"音频保存至: {AUDIO_DIR.resolve()}")

if __name__ == "__main__":
    main()
