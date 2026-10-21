"""Update test_characters.py assertions for the 14 new characters."""

import re
import hashlib
from pathlib import Path

test_file = Path("backend/tests/test_characters.py")
content = test_file.read_text(encoding="utf-8")

# 1. Voice IDs
voice_entries = f"""        "haaselia": "19191919191919191919191919191919",
        "chichiri": "{hashlib.md5(b'gbf-chichiri').hexdigest()}",
        "uruki": "{hashlib.md5(b'gbf-uruki').hexdigest()}",
        "shushuku": "{hashlib.md5(b'gbf-shushuku').hexdigest()}",
        "ami": "{hashlib.md5(b'gbf-ami').hexdigest()}",
        "wilnas": "{hashlib.md5(b'gbf-wilnas').hexdigest()}",
        "wamdus": "{hashlib.md5(b'gbf-wamdus').hexdigest()}",
        "galleon": "{hashlib.md5(b'gbf-galleon').hexdigest()}",
        "ewiyar": "{hashlib.md5(b'gbf-ewiyar').hexdigest()}",
        "luwoh": "{hashlib.md5(b'gbf-luwoh').hexdigest()}",
        "fediel": "{hashlib.md5(b'gbf-fediel').hexdigest()}",
        "yggdrasil": "{hashlib.md5(b'gbf-yggdrasil').hexdigest()}",
        "europa": "{hashlib.md5(b'gbf-europa').hexdigest()}",
        "brodia": "{hashlib.md5(b'gbf-brodia').hexdigest()}",
        "grimnir": "{hashlib.md5(b'gbf-grimnir').hexdigest()}",
    }}"""
content = re.sub(r'        "haaselia": "19191919191919191919191919191919",\s*\}', voice_entries, content, count=1)

# 2. Names
name_entries = """        "haaselia": "ハーゼリーラ",
        "chichiri": "チチリ",
        "uruki": "ウルキ",
        "shushuku": "シュシュク",
        "ami": "アミ",
        "wilnas": "ウィルナス",
        "wamdus": "ワムデュス",
        "galleon": "ガレヲン",
        "ewiyar": "イーウィヤ",
        "luwoh": "ル・オー",
        "fediel": "フェディエル",
        "yggdrasil": "ユグドラシル",
        "europa": "エウロペ",
        "brodia": "ブローディア",
        "grimnir": "グリームニル",
    }"""
content = re.sub(r'        "haaselia": "ハーゼリーラ",\s*\}', name_entries, content, count=1)

# 3. Speakers
speakers_entries = """        "haaselia": ("ハーゼリーラ", "ハーゼリーラ/哈洁莉拉", "ハーゼ", "哈洁莉拉"),
        "chichiri": ("チチリ", "チチリ/茜茜莉", "茜茜莉"),
        "uruki": ("ウルキ", "ウルキ/乌鲁姬", "乌鲁姬"),
        "shushuku": ("シュシュク", "シュシュク/修修库", "修修库"),
        "ami": ("アミ", "アミ/阿蜜", "阿蜜"),
        "wilnas": ("ウィルナス", "ウィルナス/维尔纳斯", "维尔纳斯"),
        "wamdus": ("ワムデュス", "ワムデュス/瓦姆杜斯", "瓦姆杜斯"),
        "galleon": ("ガレヲン", "ガレヲン/迦列翁", "迦列翁"),
        "ewiyar": ("イーウィヤ", "イーウィヤ/艾维亚", "艾维亚"),
        "luwoh": ("ル・オー", "ル・オー/鲁欧", "鲁欧"),
        "fediel": ("フェディエル", "フェディエル/菲迪尔", "菲迪尔"),
        "yggdrasil": ("ユグドラシル", "ユグドラシル/尤古多拉希尔", "尤古多拉希尔"),
        "europa": ("エウロペ", "エウロペ/欧罗巴", "欧罗巴"),
        "brodia": ("ブローディア", "ブローディア/布罗迪亚", "布罗迪亚", "神立之剑"),
        "grimnir": ("グリームニル", "グリームニル/格里姆尼尔", "格里姆尼尔", "军神"),
    }"""
content = re.sub(r'        "haaselia": \("ハーゼリーラ", "ハーゼリーラ/哈洁莉拉", "ハーゼ", "哈洁莉拉"\),\s*\}', speakers_entries, content, count=1)

# 4. Colors
color_entries = """        "haaselia": "#1e3a8a",
        "chichiri": "#e11d48",
        "uruki": "#0284c7",
        "shushuku": "#d97706",
        "ami": "#10b981",
        "wilnas": "#dc2626",
        "wamdus": "#06b6d4",
        "galleon": "#b45309",
        "ewiyar": "#15803d",
        "luwoh": "#eab308",
        "fediel": "#6b21a8",
        "yggdrasil": "#84cc16",
        "europa": "#38bdf8",
        "brodia": "#78350f",
        "grimnir": "#0284c7",
    }"""
content = re.sub(r'        "haaselia": "#1e3a8a",\s*\}', color_entries, content, count=1)

test_file.write_text(content, encoding="utf-8")
print("test_characters.py patched successfully!")
