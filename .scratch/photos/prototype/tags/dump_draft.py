"""把初稿逐位打出来，供人工一眼过一遍（发色、发型、瞳色三段分开看）。

    python dump_draft.py
"""

import json
import pathlib

HERE = pathlib.Path(__file__).parent
DRAFT = HERE / "draft.json"


def main() -> None:
    for character in json.loads(DRAFT.read_text(encoding="utf-8"))["characters"]:
        tags = [tag.strip() for tag in character["photo_appearance"].split(",")]
        print(f"{character['id']:9} {character['photo_tag']:20} {' | '.join(tags)}")


if __name__ == "__main__":
    main()
