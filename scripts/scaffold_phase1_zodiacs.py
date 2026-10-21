"""Scaffold Phase 1 of GBF Twelve Divine Generals (十二神将):
1. anila (アニラ / 未羊)
2. andira (アンチラ / 申猴)
3. mahira (マキラ / 酉鸡)
4. vajra (ヴァジラ / 戌狗)
5. kumbhira (クビラ / 亥猪)
"""

import csv
import json
import os
import shutil
import sqlite3
import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]

# 1. Characters Metadata
ZODIACS = [
    {
        "id": "anila",
        "name": "アニラ",
        "name_zh": "阿妮拉",
        "name_kana": "あにら",
        "name_romaji": "Anila",
        "zodiac": "未（羊）",
        "race": "ドラフ",
        "element": "火",
        "cv": "悠木碧",
        "color": "#c83232",
        "bg_color": (160, 40, 40),
        "intro": "十二神将之未神（羊），南南西之守护巫女。兼具大姐姐与慈母般的温柔包容力，深爱着空之世界的甜食美景，在团长面前偶有娇憨可爱的少女一面。",
        "dancho_honorific": "団長殿",
        "greeting": "[gently] 団長殿、今日も一日ご苦労様でした。さぁ、温かいお茶とお菓子で一息入れましょう。",
        "greeting_subtitle": "团长殿，今天一整天也辛苦了。来吧，喝杯热茶吃点点心休息一下吧。",
        "call_opener": "[softly] 団長殿？アニラです。今、少しお時間をいただいてもよろしいでしょうか？",
        "call_opener_subtitle": "团长殿？我是阿妮拉。现在能稍微借用你一点时间吗？",
        "photo_tag": "anila (granblue fantasy)",
        "photo_appearance": "draph, curved sheep horns, red eyes, long brown hair, white miko dress, large breasts",
        "liked_gifts": ["wagashi", "meat-bun"],
        "speakers": ["アニラ", "アニラ/阿妮拉", "阿妮拉"],
    },
    {
        "id": "andira",
        "name": "アンチラ",
        "name_zh": "安琪拉",
        "name_kana": "あんちら",
        "name_romaji": "Andira",
        "zodiac": "申（猴）",
        "race": "エルーン",
        "element": "风",
        "cv": "内田彩",
        "color": "#2ea865",
        "bg_color": (35, 140, 75),
        "intro": "十二神将之申神（猴），西南西之守护神。天真活泼、机敏淘气的猴族少女，像亲妹妹一样依恋信任着团长，狂风如她手中飞舞的长棍般守护同伴。",
        "dancho_honorific": "団長",
        "greeting": "[cheerfully] 団長、みーっけ！えへへ、一緒に甲板でお昼寝しようよ！",
        "greeting_subtitle": "团长，找到你啦！嘿嘿，一起去甲板上午睡嘛！",
        "call_opener": "[energetically] もしもし団長！アンチラだよー！ねぇねぇ、今何してるの？",
        "call_opener_subtitle": "喂喂团长！我是安琪拉哦！呐呐，你现在在做什么呀？",
        "photo_tag": "andira (granblue fantasy)",
        "photo_appearance": "erune, animal ears, green eyes, brown short hair, monkey tail, chinese style dress",
        "liked_gifts": ["candy", "pudding"],
        "speakers": ["アンチラ", "アンチラ/安琪拉", "安琪拉"],
    },
    {
        "id": "mahira",
        "name": "マキラ",
        "name_zh": "玛琪拉",
        "name_kana": "まきら",
        "name_romaji": "Mahira",
        "zodiac": "酉（鸡）",
        "race": "ハーヴィン",
        "element": "土",
        "cv": "門脇舞以",
        "color": "#d99726",
        "bg_color": (190, 130, 25),
        "intro": "十二神将之酉神（鸡），西之守护工匠。古风呆萌的矮人族机械天才，发明了众多自动化机械鸟，视团长为无可取代的灵感源泉与同行者。",
        "dancho_honorific": "団長さん",
        "greeting": "[calmly] 団長殿、良き日和じゃな。妾の新しいからくり、見ていかんかの？",
        "greeting_subtitle": "团长殿，今天天气真不错呢。要不要来看看老朽的新机关装置？",
        "call_opener": "[softly] 団長殿か？マキラじゃ。通信機越しに声が聴けて、嬉しゅう思うぞ。",
        "call_opener_subtitle": "是团长殿吗？老朽是玛琪拉。能通过通讯器听到你的声音，心中甚是欣喜。",
        "photo_tag": "mahira (granblue fantasy)",
        "photo_appearance": "harvin, blonde hair, blue eyes, feather hairpin, oversized sleeves, short girl",
        "liked_gifts": ["music-box", "magic-crystal"],
        "speakers": ["マキラ", "マキラ/玛琪拉", "玛琪拉"],
    },
    {
        "id": "vajra",
        "name": "ヴァジラ",
        "name_zh": "瓦吉拉",
        "name_kana": "ゔぁじら",
        "name_romaji": "Vajra",
        "zodiac": "戌（狗）",
        "race": "エルーン",
        "element": "水",
        "cv": "芹澤優",
        "color": "#2a78c5",
        "bg_color": (30, 100, 180),
        "intro": "十二神将之戌神（狗），西北西之守护武士。纯真耿直、忠心耿耿的武士娘，伴随神犬加鲁迦纳，在团长殿面前会忍不住开心摇尾巴求摸头。",
        "dancho_honorific": "団長殿",
        "greeting": "[earnestly] 団長殿！今日もこのヴァジラ、団長殿をお守りするため全力を尽くすであります！",
        "greeting_subtitle": "团长殿！今天我瓦吉拉，也定当为了守护团长殿竭尽全力！",
        "call_opener": "[happily] 団長殿！声が聞こえて嬉しいであります！し、尻尾が勝手に動いてしまう……！",
        "call_opener_subtitle": "团长殿！能听到您的声音真是太开心了！尾、尾巴忍不住自己摇起来了……！",
        "photo_tag": "vajra (granblue fantasy)",
        "photo_appearance": "erune, dog ears, dog tail, short blue hair, red eyes, samurai attire, headband",
        "liked_gifts": ["meat-bun", "plush"],
        "speakers": ["ヴァジラ", "ヴァジラ/瓦吉拉", "瓦吉拉"],
    },
    {
        "id": "kumbhira",
        "name": "クビラ",
        "name_zh": "久碧拉",
        "name_kana": "くびら",
        "name_romaji": "Kumbhira",
        "zodiac": "亥（猪）",
        "race": "ドラフ",
        "element": "光",
        "cv": "堀江由衣",
        "color": "#d97724",
        "bg_color": (195, 100, 30),
        "intro": "十二神将之亥神（猪），北北西之守护努力家。老实踏实的牛族少女，虽常因自感缺乏神将威严而自卑，但无论多么艰苦的修炼都脚踏实地，深念团长的每一次鼓励。",
        "dancho_honorific": "団長さん",
        "greeting": "[warmly] 団長さん、お疲れ様です！ポポと一緒に甲板をピカピカにお掃除しておきましたよ！",
        "greeting_subtitle": "团长，辛苦了！我和啵啵一起把甲板打扫得干干净净了哦！",
        "call_opener": "[shyly] もしもし、団長さん……？あの、声が聞きたくなっちゃって……迷惑じゃなかったですか……？",
        "call_opener_subtitle": "喂喂，团长吗……？那个，我突然很想听听你的声音……没有打扰到你吧……？",
        "photo_tag": "kumbhira (granblue fantasy)",
        "photo_appearance": "draph, curved horns, orange hair, yellow eyes, shrine maiden outfit, hair buns",
        "liked_gifts": ["cake", "plush"],
        "speakers": ["クビラ", "クビラ/久碧拉", "久碧拉"],
    },
]


def create_images(char: dict):
    avatars_dir = ROOT / "characters" / "avatars"
    bg_dir = ROOT / "characters" / "backgrounds"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    bg_dir.mkdir(parents=True, exist_ok=True)

    av_path = avatars_dir / f"{char['id']}.jpg"
    bg_path = bg_dir / f"{char['id']}.jpg"

    # 1. Avatar (224x224, < 32KB)
    im_av = Image.new("RGB", (224, 224), char["bg_color"])
    draw_av = ImageDraw.Draw(im_av)
    # Draw simple circular badge
    draw_av.ellipse([20, 20, 204, 204], outline=(255, 255, 255), width=3)
    # Inner decorative ring
    draw_av.ellipse([32, 32, 192, 192], outline=(255, 255, 255, 120), width=1)
    im_av.save(av_path, "JPEG", quality=88)

    # 2. Background (1200x800, < 120KB)
    im_bg = Image.new("RGB", (1200, 800), char["bg_color"])
    draw_bg = ImageDraw.Draw(im_bg)
    # Gradient bands
    for y in range(800):
        factor = y / 800.0
        r = int(char["bg_color"][0] * (0.6 + 0.4 * factor))
        g = int(char["bg_color"][1] * (0.6 + 0.4 * factor))
        b = int(char["bg_color"][2] * (0.6 + 0.4 * factor))
        draw_bg.line([(0, y), (1200, y)], fill=(r, g, b))
    im_bg.save(bg_path, "JPEG", quality=85)


def create_audio(char: dict):
    sound_dir = ROOT / "frontend" / "public" / "sounds" / "gbf"
    sound_dir.mkdir(parents=True, exist_ok=True)

    # Use existing clean clip template
    template = sound_dir / "nier_call_opener.mp3"
    if not template.exists():
        template = sound_dir / "vikala_call_opener.mp3"

    for suffix in ["", "_greeting", "_call_opener"]:
        target = sound_dir / f"{char['id']}{suffix}.mp3"
        if not target.exists():
            shutil.copyfile(template, target)


def main():
    print(f"=== Scaffolding {len(ZODIACS)} Divine Generals for Phase 1 ===")
    for c in ZODIACS:
        print(f"Processing {c['name']} ({c['id']})...")
        create_images(c)
        create_audio(c)
    print("Base assets created successfully!")


if __name__ == "__main__":
    main()
