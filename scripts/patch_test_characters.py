from pathlib import Path

test_path = Path("backend/tests/test_characters.py")
text = test_path.read_text(encoding="utf-8")

# 1. Correct order for voice_id
wrong_voice_block = """        "olivia": "327ba4398988e45cf50bf936b1620dc6",
        "lyria": "d294288c1e1fb85dbbcfd14af4a0f06a",
        "vampy": "75f2a8032c5599be5578f0ea0c4c40e3",
        "vira": "ab5df814e522f40bda413b8da1929412",
        "cagliostro": "c2f9d6e3ca613ddf07b5e0b08789dc1d",
        "cupitan": "d26ff295cb9f87e876e98151533b84e1",
        "tikoh": "027933dab7e7397789f03cea77cdec00",
        "ilsa": "88c707beb08672e15a4d4a850b56dcc9",
        "zooey": "12d20e61bc0fe3126cbc23984bc9a622",
        "marippe": "66e08d076004dc38c9394b4c54dfe119",
        "meg": "2ef4dd3ce7a1883e2b8e193753399ea0",
        "zeta": "ccada9c548c52840891925aae64e1f8e",
        "orchid": "73de8aea077d71dc2c4cb001ed998c7f",
        "azusa": "ddba4cf178079fab2fc7edb303e166fe",
    }"""

correct_voice_block = """        "olivia": "327ba4398988e45cf50bf936b1620dc6",
        "azusa": "ddba4cf178079fab2fc7edb303e166fe",
        "orchid": "73de8aea077d71dc2c4cb001ed998c7f",
        "zeta": "ccada9c548c52840891925aae64e1f8e",
        "meg": "2ef4dd3ce7a1883e2b8e193753399ea0",
        "marippe": "66e08d076004dc38c9394b4c54dfe119",
        "zooey": "12d20e61bc0fe3126cbc23984bc9a622",
        "ilsa": "88c707beb08672e15a4d4a850b56dcc9",
        "tikoh": "027933dab7e7397789f03cea77cdec00",
        "cupitan": "d26ff295cb9f87e876e98151533b84e1",
        "cagliostro": "c2f9d6e3ca613ddf07b5e0b08789dc1d",
        "vira": "ab5df814e522f40bda413b8da1929412",
        "vampy": "75f2a8032c5599be5578f0ea0c4c40e3",
        "lyria": "d294288c1e1fb85dbbcfd14af4a0f06a",
    }"""

assert wrong_voice_block in text, "wrong_voice_block not found"
text = text.replace(wrong_voice_block, correct_voice_block)

# 2. Correct order for name
wrong_name_block = """        "olivia": "オリヴィエ",
        "lyria": "ルリア",
        "vampy": "ヴァンピィ",
        "vira": "ヴィーラ",
        "cagliostro": "カリオストロ",
        "cupitan": "クピタン",
        "tikoh": "ティコ",
        "ilsa": "イルザ",
        "zooey": "ゾーイ",
        "marippe": "まりっぺ",
        "meg": "メグ",
        "zeta": "ゼタ",
        "orchid": "オーキス",
        "azusa": "アズサ",
    }"""

correct_name_block = """        "olivia": "オリヴィエ",
        "azusa": "アズサ",
        "orchid": "オーキス",
        "zeta": "ゼタ",
        "meg": "メグ",
        "marippe": "まりっぺ",
        "zooey": "ゾーイ",
        "ilsa": "イルザ",
        "tikoh": "ティコ",
        "cupitan": "クピタン",
        "cagliostro": "カリオストロ",
        "vira": "ヴィーラ",
        "vampy": "ヴァンピィ",
        "lyria": "ルリア",
    }"""

assert wrong_name_block in text, "wrong_name_block not found"
text = text.replace(wrong_name_block, correct_name_block)

# 3. Speakers block
old_speakers_end = """        "olivia": ("オリヴィエ", "オリヴィエ/奥利维尔", "奥利维尔", "堕天司"),
    }"""

new_speakers_end = """        "olivia": ("オリヴィエ", "オリヴィエ/奥利维尔", "奥利维尔", "堕天司"),
        "azusa": ("アズサ", "アズサ/阿梓", "阿梓"),
        "orchid": ("オーキス", "オーキス/欧契斯", "欧契斯"),
        "zeta": ("ゼタ", "ゼタ/泽塔", "泽塔"),
        "meg": ("メグ", "メグ/梅格", "梅格"),
        "marippe": ("まりっぺ", "まりっぺ/玛莉沛", "玛莉沛", "マリ"),
        "zooey": ("ゾーイ", "ゾーイ/佐伊", "佐伊"),
        "ilsa": ("イルザ", "イルザ/艾尔莎", "艾尔莎"),
        "tikoh": ("ティコ", "ティコ/蒂子", "蒂子"),
        "cupitan": ("クピタン", "クピタン/库皮坦", "库皮坦"),
        "cagliostro": ("カリオストロ", "カリオストロ/卡莉奥丝特罗", "卡莉奥丝特罗"),
        "vira": ("ヴィーラ", "ヴィーラ/维拉", "维拉"),
        "vampy": ("ヴァンピィ", "ヴァンピィ/斑比", "斑比"),
        "lyria": ("ルリア", "ルリア/露莉亚", "露莉亚"),
    }"""

assert old_speakers_end in text, "old_speakers_end not found"
text = text.replace(old_speakers_end, new_speakers_end)

# 4. Color block
old_color_end = """        "olivia": "#581c87",
    }"""

new_color_end = """        "olivia": "#581c87",
        "azusa": "#532938",
        "orchid": "#48446b",
        "zeta": "#c03535",
        "meg": "#2f718f",
        "marippe": "#e58238",
        "zooey": "#244b7d",
        "ilsa": "#7c5643",
        "tikoh": "#3d7a6e",
        "cupitan": "#3679a8",
        "cagliostro": "#c9688b",
        "vira": "#7a3272",
        "vampy": "#b82e56",
        "lyria": "#3a9fd8",
    }"""

assert old_color_end in text, "old_color_end not found"
text = text.replace(old_color_end, new_color_end)

test_path.write_text(text, encoding="utf-8")
print("Patched backend/tests/test_characters.py successfully")
