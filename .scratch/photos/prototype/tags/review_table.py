"""生成给用户校对的对照表：每人一行，缩略图 + 角色 tag + 外貌 tag。

输出两样，都在 `.scratch/photos/prototype/tags/`：
- `contact_sheet.png`：28 位的缩略图拼版，编号对应下面的表，对照着看；
- 标准输出：Markdown 表格，贴进票 13 的 Comments 里给用户逐行校对。

    python review_table.py
"""

import json
import pathlib
import sys
import tomllib

from PIL import Image, ImageDraw

HERE = pathlib.Path(__file__).parent
REPO = HERE.parents[3]
CONFIG = REPO / "characters" / "characters.toml"
DRAFT = HERE / "draft.json"
OUT = HERE / "contact_sheet.png"

THUMBS = REPO / "corpus" / "stand" / "thumbnails"
CELL = (300, 375)
COLUMNS = 7


def main() -> int:
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    by_id = {character["id"]: character for character in config["characters"]}

    characters = draft["characters"]
    rows = (len(characters) + COLUMNS - 1) // COLUMNS
    sheet = Image.new("RGB", (COLUMNS * CELL[0], rows * (CELL[1] + 26)), (250, 250, 250))
    draw = ImageDraw.Draw(sheet)

    for index, character in enumerate(characters):
        kind, enza = by_id[character["id"]]["default_outfit"].split("/")
        image = Image.open(THUMBS / kind / f"{enza}.png").convert("RGBA")
        backdrop = Image.new("RGB", image.size, (252, 252, 252))
        backdrop.paste(image, mask=image.getchannel("A"))
        column, row = index % COLUMNS, index // COLUMNS
        x, y = column * CELL[0], row * (CELL[1] + 26)
        sheet.paste(backdrop.resize(CELL, Image.LANCZOS), (x, y))
        draw.text((x + 6, y + CELL[1] + 6), f"{index + 1:02d} {character['id']}", fill=(20, 20, 20))

    sheet.save(OUT)
    print(f"拼版：{OUT}  {sheet.width}x{sheet.height}\n", file=sys.stderr)

    print("| # | 角色 | 缩略图 | 角色 tag | 外貌 tag | 来历 |")
    print("|---|---|---|---|---|---|")
    for index, character in enumerate(characters):
        kind, enza = by_id[character["id"]]["default_outfit"].split("/")
        origin = "票 05 定稿" if character.get("source") == "ticket05" else "本次初稿"
        print(
            f"| {index + 1:02d} | {character['name']} | `{kind}/{enza}.png` "
            f"| `{character['photo_tag']}` | `{character['photo_appearance']}` | {origin} |"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
