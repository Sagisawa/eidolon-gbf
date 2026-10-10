"""Characters available for conversation, loaded from the character configuration.

The configuration is a TOML file listing each character's identifier, display
name, introduction, voice, image colour and the location of her character sheet
(and, optionally, her character facts, avatar and call background), relative to
the file, plus the speaker names her lines carry in the story corpus. Adding a
character or replacing a voice is a configuration change. The sheets, facts,
avatars and backgrounds are committed with the configuration (ADR-0003).

Optionally, she also names her idol in the original (`idol_id`, as in the Spine
mirror's `spine_manifest.json`) and the outfit her stand wears unless the user picks
another (`default_outfit`, e.g. `stand/1030010010`). The stands themselves are not
committed: they are served from object storage (ADR-0003, revised 2026-09-30).

Optionally, she also has a greeting for the landing page (GLOSSARY.md「招呼」): what she
says in Japanese, delivery cues and all (`greeting`), and its Chinese subtitle
(`greeting_subtitle`), the one with the other. The words are committed; the audio
`eidolon greeting upload` voices from them is not, and goes to the stands' bucket
(ADR-0003, revised 2026-10-10).

Character facts are a Markdown file; each section under a heading is one fact,
retrieved on its own when a turn calls for it.

A sheet drafted by `eidolon character draft-sheet` starts with `DRAFT_MARKER` until an
administrator has reviewed it and removed the line; the marker never reaches the prompt.
"""

import logging
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

from eidolon.delivery_cues import without_cues

log = logging.getLogger(__name__)

_VALID_ID = re.compile(r"[a-z][a-z0-9_-]*")
_REQUIRED = ("id", "name", "intro", "voice_id", "sheet", "color")
_IMAGE_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
_OUTFIT = re.compile(r"(stand|stand_costume)/[0-9]{10}")
"""An outfit: her everyday clothes on a card (`stand`) or its stage costume
(`stand_costume`), and the card's ten-digit enzaId."""

DRAFT_MARKER = "<!-- 人设草稿：由后台模型根据剧情生成，尚未校对。校对完成后删除这一行。 -->"


class CharacterConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Fact:
    """One entry of a character's facts: the section under a heading."""

    title: str | None
    """The headings above it, e.g. `人物关系 / 風野灯織`; None for text before any heading."""
    text: str
    """The entry as it is retrieved, headed by its title."""


@dataclass(frozen=True)
class Greeting:
    """What she says to a producer she meets for the first time, on the landing page: written
    beforehand and reviewed, voiced once in her voice; never part of any turn."""

    text: str
    """In Japanese as it is voiced, delivery cues and all (`delivery_cues`)."""
    subtitle: str
    """Its Chinese subtitle."""

    @property
    def ja(self) -> str:
        """In Japanese as people see it, without its delivery cues."""
        return without_cues(self.text)


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    intro: str
    voice_id: str
    sheet: str
    """Empty when the sheet file does not exist yet (only when loaded without requiring it)."""
    avatar: Path | None
    color: str
    """Her image colour, the official one from the original, as lower-case `#rrggbb`."""
    background: Path | None = None
    """The picture behind her call screen; None shows a gradient of her image colour."""
    speakers: tuple[str, ...] = ()
    """Names her lines are credited to in story scripts, e.g. 真乃."""
    facts: tuple[Fact, ...] = ()
    """Her character facts, one entry per section of her facts file."""
    sheet_path: Path | None = None
    idol_id: int | None = None
    """Who she is in the original's Spine mirror (`idolId` in `spine_manifest.json`)."""
    default_outfit: str | None = None
    """The outfit her stand wears unless the user picks another, as `<category>/<enzaId>`:
    `stand/1030010010` is her everyday clothes on that card, `stand_costume/...` its stage
    costume. Its files are at `spine/idols/<category>/<enzaId>/` under the stand assets."""
    greeting: Greeting | None = None
    """Her greeting on the landing page; None shows her there without one."""


def load_characters(path: Path, require_sheets: bool = True) -> dict[str, Character]:
    """Read the character configuration at `path`, keyed by identifier in file order.

    Without `require_sheets`, a character whose sheet file is missing is loaded with an
    empty sheet, as when drafting it."""
    path = path.resolve()
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CharacterConfigError(f"找不到角色配置文件 {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise CharacterConfigError(f"角色配置文件 {path} 格式有误：{e}") from None

    characters: dict[str, Character] = {}
    for entry in config.get("characters", []):
        character = _parse_character(entry, path.parent, require_sheets)
        if character.id in characters:
            raise CharacterConfigError(f"角色标识 {character.id} 重复")
        for other in characters.values():
            if shared := set(character.speakers) & set(other.speakers):
                raise CharacterConfigError(
                    f"角色 {other.id} 和 {character.id} 的 speakers 都有 {'、'.join(sorted(shared))}"
                )
        characters[character.id] = character
    if not characters:
        raise CharacterConfigError(f"角色配置文件 {path} 里没有任何角色")
    return characters


def _parse_character(entry: dict, base: Path, require_sheet: bool) -> Character:
    label = entry.get("id", "（没有标识）")
    missing = [field for field in _REQUIRED if not isinstance(entry.get(field), str)]
    if missing:
        raise CharacterConfigError(f"角色 {label} 缺少字段 {'、'.join(missing)}")
    if not _VALID_ID.fullmatch(entry["id"]):
        raise CharacterConfigError(f"角色标识 {label} 只能包含小写字母、数字、- 和 _")
    if not _IMAGE_COLOR.fullmatch(entry["color"]):
        raise CharacterConfigError(
            f"角色 {label} 的 color 应为 #rrggbb 格式的印象色，现在是 {entry['color']!r}"
        )

    sheet_path = base / entry["sheet"]
    try:
        sheet = sheet_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        if require_sheet:
            raise CharacterConfigError(
                f"角色 {label} 的人设文件 {sheet_path} 不存在"
                "（可参考 sheets/example.md，或用 eidolon character draft-sheet 生成初稿）"
            ) from None
        sheet = ""
    if is_draft(sheet):
        log.warning("sheet %s of character %s is an unreviewed draft", sheet_path, label)
        sheet = sheet.replace(DRAFT_MARKER, "", 1).strip()

    facts: tuple[Fact, ...] = ()
    if isinstance(entry.get("facts"), str):
        facts_path = base / entry["facts"]
        try:
            facts = parse_facts(facts_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            log.warning("facts %s of character %s are missing; retrieving none", facts_path, label)

    speakers = entry.get("speakers", [])
    if not isinstance(speakers, list) or not all(isinstance(s, str) and s for s in speakers):
        raise CharacterConfigError(f"角色 {label} 的 speakers 应为说话人名字的列表")

    avatar = _optional_file(entry, "avatar", base, label)
    background = _optional_file(entry, "background", base, label)

    idol_id = entry.get("idol_id")
    # bool is an int in Python, but `idol_id = true` is a mistake all the same.
    if idol_id is not None and (type(idol_id) is not int or idol_id <= 0):
        raise CharacterConfigError(
            f"角色 {label} 的 idol_id 应为原作的偶像编号（spine_manifest.json 的 idolId，正整数），"
            f"现在是 {idol_id!r}"
        )
    default_outfit = entry.get("default_outfit")
    if default_outfit is not None and not (
        isinstance(default_outfit, str) and _OUTFIT.fullmatch(default_outfit)
    ):
        raise CharacterConfigError(
            f"角色 {label} 的 default_outfit 应写成 stand/<enzaId> 或 stand_costume/<enzaId>"
            f"（enzaId 是十位数字），现在是 {default_outfit!r}"
        )

    return Character(
        id=entry["id"],
        name=entry["name"],
        intro=entry["intro"],
        voice_id=entry["voice_id"],
        sheet=sheet,
        avatar=avatar,
        color=entry["color"].lower(),
        background=background,
        speakers=tuple(speakers),
        facts=facts,
        sheet_path=sheet_path,
        idol_id=idol_id,
        default_outfit=default_outfit,
        greeting=_greeting(entry, label),
    )


def _greeting(entry: dict, label: str) -> Greeting | None:
    """Her greeting, if she has one: its words and its subtitle, both or neither."""
    text, subtitle = entry.get("greeting"), entry.get("greeting_subtitle")
    if text is None and subtitle is None:
        return None
    if not (isinstance(text, str) and text.strip()):
        raise CharacterConfigError(
            f"角色 {label} 的招呼缺少日语原文：greeting 应为她说的日语（可以带语气提示），和 greeting_subtitle 一起配"
        )
    if not without_cues(text):
        raise CharacterConfigError(f"角色 {label} 的招呼 greeting 去掉语气提示后什么都不剩，现在是 {text!r}")
    if not (isinstance(subtitle, str) and subtitle.strip()):
        raise CharacterConfigError(
            f"角色 {label} 的招呼缺少中文字幕：greeting_subtitle 应为 greeting 的中文字幕，和它一起配"
        )
    return Greeting(text.strip(), subtitle.strip())


def _optional_file(entry: dict, field: str, base: Path, label: str) -> Path | None:
    """The file an optional field names, relative to the configuration; None when the
    field is absent or the file is missing (with a warning, so she shows without it)."""
    if not isinstance(entry.get(field), str):
        return None
    path = base / entry[field]
    if not path.is_file():
        log.warning("%s %s of character %s is missing; showing none", field, path, label)
        return None
    return path


def is_draft(sheet: str) -> bool:
    """Whether a sheet is a draft nobody has reviewed yet."""
    return sheet.lstrip().startswith(DRAFT_MARKER)


_HEADING = re.compile(r"(#{1,6})\s+(.+?)\s*#*\s*")


def parse_facts(markdown: str) -> tuple[Fact, ...]:
    """Split a facts file into entries: the text under each heading, titled with the
    headings above it (e.g. `人物关系 / 風野灯織`). Headings with nothing under them
    make no entry."""
    facts: list[Fact] = []
    titles: list[str] = []
    body: list[str] = []

    def flush() -> None:
        text = "\n".join(body).strip()
        if text:
            title = " / ".join(titles) or None
            facts.append(Fact(title, f"{title}\n{text}" if title else text))
        body.clear()

    for line in markdown.splitlines():
        if heading := _HEADING.fullmatch(line):
            flush()
            del titles[len(heading.group(1)) - 1 :]
            titles.append(heading.group(2))
        else:
            body.append(line)
    flush()
    return tuple(facts)
