"""把初稿逐位打出来，供人工一眼过一遍。

    python dump_draft.py
"""

import json
import pathlib
import sys

from verify_draft import appearance_of

HERE = pathlib.Path(__file__).parent
DRAFT = HERE / "draft.json"


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")  # Windows 控制台默认 GBK，中文会打不出来
    for character in json.loads(DRAFT.read_text(encoding="utf-8"))["characters"]:
        print(f"{character['id']:9} {character['photo_tag']:20} {' | '.join(appearance_of(character))}")


if __name__ == "__main__":
    main()
