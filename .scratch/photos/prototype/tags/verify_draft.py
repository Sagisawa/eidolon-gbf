"""核对票 13 的初稿（`draft.json`）。

查四件事：
1. 28 位一个不少，和 `characters.toml` 里的 id、名罗马字、默认衣装对得上；
2. `photo_tag` 和 `photo_appearance` 的写法合规（小写、空格分隔、无语法字符）；
3. 每一条 tag 都是 V5 Curated 词表里的已知 tag（官方 tag 建议接口，一次一条）；
4. `photo_appearance` 只写发色、发型、瞳色，没混进饰物和服装。

    python verify_draft.py            # 全部核对
    python verify_draft.py --offline  # 只查 1、2、4，不联网
"""

import json
import pathlib
import re
import sys
import tomllib

from verify import known

HERE = pathlib.Path(__file__).parent
REPO = HERE.parents[3]
CONFIG = REPO / "characters" / "characters.toml"
DRAFT = HERE / "draft.json"
MODEL = "nai-diffusion-5-curated"

# 外貌 tag 只许这三类：发色/发型/瞳色。其余（饰物、服装、身材）一律算越界。
ALLOWED = re.compile(
    r"^(?:(?:black|brown|blonde|grey|silver|white|red|orange|pink|purple|blue|green|aqua|light blue|dark blue|light brown) hair"
    r"|short hair|medium hair|long hair|twintails|low twintails|ponytail|high ponytail|braided ponytail|single braid|side braid"
    r"|hair bun|double bun|drill hair|ringlets|wavy hair|curly hair|gradient hair|streaked hair|two-tone hair|multicolored hair"
    r"|ahoge|swept bangs|blunt bangs|parted bangs|diagonal bangs|hair between eyes|bob cut|hime cut|sidelocks|hair intakes"
    r"|(?:black|brown|grey|red|orange|pink|purple|blue|green|aqua|yellow|heterochromia) eyes)$"
)
TAG = re.compile(r"^[a-z0-9][a-z0-9:' ()-]*$")


def fail(messages: list[str], text: str) -> None:
    messages.append(text)


def load() -> tuple[dict, dict]:
    draft = json.loads(DRAFT.read_text(encoding="utf-8"))
    config = tomllib.loads(CONFIG.read_text(encoding="utf-8"))
    return draft, {character["id"]: character for character in config["characters"]}


def main() -> int:
    offline = "--offline" in sys.argv
    draft, configured = load()
    messages: list[str] = []
    characters = draft["characters"]

    if len(characters) != 28:
        fail(messages, f"初稿有 {len(characters)} 位，应为 28 位")
    if {c["id"] for c in characters} != set(configured):
        fail(messages, "初稿的 id 和 characters.toml 对不上")
    if len({c["id"] for c in characters}) != len(characters):
        fail(messages, "初稿里有重复的 id")

    checked: set[str] = set()
    for character in characters:
        label = character["id"]
        source = configured.get(label)
        if source is None:
            continue
        if character["romaji"].lower() != source["name_romaji"].lower():
            fail(messages, f"{label}: 罗马字 {character['romaji']!r} 和配置对不上")
        if character["enza"] != source["default_outfit"].split("/")[1]:
            fail(messages, f"{label}: 默认衣装 {character['enza']} 和配置对不上")

        if character["photo_tag"] != source["name_romaji"].lower():
            fail(messages, f"{label}: 角色 tag 应从 name_romaji 转小写")

        appearance = [t.strip() for t in character["photo_appearance"].split(",") if t.strip()]
        if not appearance:
            fail(messages, f"{label}: 外貌 tag 是空的")
        for tag in appearance:
            if not TAG.match(tag):
                fail(messages, f"{label}: {tag!r} 写法不合规")
            if not ALLOWED.match(tag):
                fail(messages, f"{label}: {tag!r} 不是发色/发型/瞳色，混进了别的")
        eye_tags = [t for t in appearance if t.endswith(" eyes")]
        if len(eye_tags) != 1:
            fail(messages, f"{label}: 瞳色应恰好一条，现在 {eye_tags}")
        if len(set(appearance)) != len(appearance):
            fail(messages, f"{label}: 外貌 tag 有重复")
        checked.add(character["photo_tag"])
        checked.update(appearance)

    if not offline:
        for tag in sorted(checked):
            if not known(MODEL, tag):
                fail(messages, f"{tag!r} 不是 {MODEL} 的已知 tag")

    if messages:
        print(f"✗ {len(messages)} 处问题")
        for message in messages:
            print(f"  - {message}")
        return 1
    mode = "离线核对" if offline else f"含 {len(checked)} 条 tag 的联网核对"
    print(f"✓ 28 位齐、写法合规、外貌只含发色发型瞳色（{mode}）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
