"""查 Danbooru 上和每位角色 tag 共现最多的外貌 tag，当写外貌 tag 初稿的参考。

票 13 用（照票 05 `related.py` 的做法）。共现 tag 不能直接用：团体图里会混进别人的
特征，只能当参考，最后要对着缩略图核对。

    python danbooru_related.py            # 全部 28 位
    python danbooru_related.py mamimi     # 只查几位
"""

import json
import pathlib
import re
import sys
import tomllib
import urllib.parse
import urllib.request

REPO = pathlib.Path(__file__).parents[4]
CONFIG = REPO / "characters" / "characters.toml"

APPEARANCE = re.compile(
    r"(hair|eyes|bangs|sidelocks|ahoge|twintails|ponytail|bun|braid|bob cut|curly|wavy|drill|ringlets)"
)


def related(tag: str) -> list[tuple[str, float]]:
    """和这个 tag 共现最多的外貌类 general tag，按共现频率排序。"""
    query = urllib.parse.urlencode(
        {"query": tag.replace(" ", "_"), "category": "general", "limit": 200}
    )
    request = urllib.request.Request(
        f"https://danbooru.donmai.us/related_tag.json?{query}",
        headers={"User-Agent": "curl/8.7.1"},
    )
    with urllib.request.urlopen(request, timeout=40) as response:
        payload = json.loads(response.read())
    rows = [(row["tag"]["name"].replace("_", " "), float(row.get("frequency", 0))) for row in payload.get("related_tags", [])]
    return [(name, frequency) for name, frequency in rows if APPEARANCE.search(name)][:14]


def main() -> int:
    wanted = set(sys.argv[1:])
    characters = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["characters"]
    for character in characters:
        if wanted and character["id"] not in wanted:
            continue
        tag = character["name_romaji"].lower()
        try:
            rows = related(tag)
        except Exception as error:  # noqa: BLE001 - 查不到就跳过，不挡着别的
            print(f"{character['id']:9} {tag:20} ERROR {error}")
            continue
        shown = ", ".join(f"{name}({frequency:.2f})" for name, frequency in rows)
        print(f"{character['id']:9} {tag:20} {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
