"""world sync 各导入共用的小工具（`release_sync`、`live_sync`、`setlist_sync`、`roster`）。"""

import re
from collections.abc import Awaitable, Callable

Fetch = Callable[[str], Awaitable[str]]
"""取一个网页的文字；取不到就抛出 WorldSyncError。"""


def hiragana(text: str) -> str:
    """片假名换成平假名：イルミネーションスターズ 就是读音 いるみねーしょんすたーず。"""
    return "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in text)


def without_spaces(text: str) -> str:
    """去掉所有空白：関根 瞳 就是 関根瞳。"""
    return re.sub(r"\s", "", text)
