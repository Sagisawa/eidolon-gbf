"""核对 28 位偶像的角色 tag 是不是 V5 Curated 的已知角色 tag。

票 13 用：`photo_tag` 存 Danbooru 写法（小写、空格代替下划线），不从 `name_romaji` 推，
但两者的初稿一样，所以这里从 `characters.toml` 取 `name_romaji` 转小写来核对。

    python character_tags.py nai-diffusion-5-curated
"""

import pathlib
import sys
import tomllib

from verify import known

REPO = pathlib.Path(__file__).parents[4]
CONFIG = REPO / "characters" / "characters.toml"


def main() -> int:
    model = sys.argv[1] if len(sys.argv) > 1 else "nai-diffusion-5-curated"
    characters = tomllib.loads(CONFIG.read_text(encoding="utf-8"))["characters"]
    missing = []
    for character in characters:
        tag = character["name_romaji"].lower()
        hit = known(model, tag)
        print(f"{'YES' if hit else 'NO '}  {character['id']:9} {tag}")
        if not hit:
            missing.append((character["id"], tag))
    print(f"\n{len(characters) - len(missing)}/{len(characters)} known on {model}")
    if missing:
        print("not known: " + ", ".join(f"{i}={t}" for i, t in missing))
    return 1 if missing else 0


if __name__ == "__main__":
    sys.exit(main())
