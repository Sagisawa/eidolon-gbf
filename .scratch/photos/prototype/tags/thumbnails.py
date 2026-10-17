"""把默认衣装缩略图铺到浅色底上，供拼图脚本共用。

缩略图是透明背景 PNG，直接贴到白底上会有黑边，这里按 alpha 合成。
"""

import pathlib

from PIL import Image

REPO = pathlib.Path(__file__).parents[4]
CONFIG = REPO / "characters" / "characters.toml"
THUMBS = REPO / "corpus" / "stand" / "thumbnails"
BACKDROP = (252, 252, 252)


def thumbnail(character: dict) -> Image.Image:
    """一位角色默认衣装的那张缩略图，铺在浅色底上。"""
    kind, enza = character["default_outfit"].split("/")
    image = Image.open(THUMBS / kind / f"{enza}.png").convert("RGBA")
    backdrop = Image.new("RGB", image.size, BACKDROP)
    backdrop.paste(image, mask=image.getchannel("A"))
    return backdrop


def alpha_box(path: pathlib.Path) -> tuple[int, int, int, int]:
    """图里人物实际占的矩形（透明背景才算得准）。"""
    image = Image.open(path).convert("RGBA")
    return image.getchannel("A").getbbox() or (0, 0, *image.size)


def load_characters() -> list[dict]:
    """`characters.toml` 里的全部角色。"""
    import tomllib

    return tomllib.loads(CONFIG.read_text(encoding="utf-8"))["characters"]
