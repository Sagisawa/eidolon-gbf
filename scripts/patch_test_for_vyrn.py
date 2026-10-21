import sys
from pathlib import Path

p = Path("backend/tests/test_characters.py")
txt = p.read_text(encoding="utf-8")

# 1. Voice ID
target1 = """        "lyria": "d294288c1e1fb85dbbcfd14af4a0f06a",
    }"""
repl1 = """        "lyria": "d294288c1e1fb85dbbcfd14af4a0f06a",
        "vyrn": "cee2d4cc44223ea9c34fd1f9e8125cdf",
    }"""
assert target1 in txt, "target1 not found"
txt = txt.replace(target1, repl1)

# 2. Name
target2 = """        "lyria": "ルリア",
    }"""
repl2 = """        "lyria": "ルリア",
        "vyrn": "ビィ",
    }"""
assert target2 in txt, "target2 not found"
txt = txt.replace(target2, repl2)

# 3. Speakers
target3 = """        "lyria": ("ルリア", "ルリア/露莉亚", "露莉亚"),
    }"""
repl3 = """        "lyria": ("ルリア", "ルリア/露莉亚", "露莉亚"),
        "vyrn": ("ビィ", "ビィ/碧", "碧", "相棒"),
    }"""
assert target3 in txt, "target3 not found"
txt = txt.replace(target3, repl3)

# 4. Color
target4 = """        "lyria": "#3a9fd8",
    }"""
repl4 = """        "lyria": "#3a9fd8",
        "vyrn": "#d93829",
    }"""
assert target4 in txt, "target4 not found"
txt = txt.replace(target4, repl4)

p.write_text(txt, encoding="utf-8")
print("backend/tests/test_characters.py patched for vyrn successfully!")
