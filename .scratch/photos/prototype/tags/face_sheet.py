"""按人物的实际位置裁出脸，拼成对照图，供逐位校对发色、发型、瞳色。

缩略图是透明背景的 PNG，行内位置随人物宽窄而变（侧身、有帽子的会偏），
所以先按 alpha 通道求出人物所在的矩形，再从矩形顶端取头部那一块。

    python face_sheet.py            # 全部 28 位
    python face_sheet.py mamimi yuika
"""

import pathlib
import sys
import tomllib

from PIL import Image, ImageDraw

REPO = pathlib.Path(__file__).parents[4]
CONFIG = REPO / "characters" / "characters.toml"
THUMBS = REPO / "corpus" / "stand" / "thumbnails"
OUT = REPO / ".scratch" / "_faces" / "faces.png"

CELL = (440, 470)
COLUMNS = 2
ROWS_PER_SHEET = 4


def head(path: pathlib.Path) -> Image.Image:
    """人物头顶往下约三分之一身高那一块（脸和头发）。"""
    image = Image.open(path).convert("RGBA")
    box = image.getchannel("A").getbbox()
    if box is None:  # 没有 alpha 的全不透明图，退化成整张
        box = (0, 0, *image.size)
    left, top, right, bottom = box
    width, height = right - left, bottom - top
    pad = int(width * 0.12)
    crop = image.crop(
        (
            max(left - pad, 0),
            top,
            min(right + pad, image.width),
            top + int(height * 0.42),
        )
    )
    backdrop = Image.new("RGB", crop.size, (252, 252, 252))
    backdrop.paste(crop, mask=crop.getchannel("A"))
    return backdrop.resize(CELL, Image.LANCZOS)


def main() -> int:
    wanted = set(sys.argv[1:])
    characters = [
        character
        for character in tomllib.loads(CONFIG.read_text(encoding="utf-8"))["characters"]
        if not wanted or character["id"] in wanted
    ]
    per_sheet = COLUMNS * ROWS_PER_SHEET
    for start in range(0, len(characters), per_sheet):
        chunk = characters[start : start + per_sheet]
        rows = (len(chunk) + COLUMNS - 1) // COLUMNS
        sheet = Image.new("RGB", (COLUMNS * CELL[0], rows * (CELL[1] + 18)), (250, 250, 250))
        draw = ImageDraw.Draw(sheet)
        for index, character in enumerate(chunk):
            kind, enza = character["default_outfit"].split("/")
            column, row = index % COLUMNS, index // COLUMNS
            x, y = column * CELL[0], row * (CELL[1] + 18)
            sheet.paste(head(THUMBS / kind / f"{enza}.png"), (x, y))
            draw.text((x + 6, y + CELL[1] + 4), character["id"], fill=(20, 20, 20))
        OUT.parent.mkdir(parents=True, exist_ok=True)
        path = OUT.with_name(f"faces-{start // per_sheet + 1}.png")
        sheet.save(path)
        print(f"{path}  {sheet.width}x{sheet.height}  {len(chunk)} heads")
    return 0


if __name__ == "__main__":
    sys.exit(main())
