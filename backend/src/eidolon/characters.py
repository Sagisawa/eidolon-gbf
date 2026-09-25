"""Characters available for conversation, loaded from the character configuration.

The configuration is a TOML file listing each character's identifier, display
name, introduction, voice and the location of her character sheet (and,
optionally, avatar), relative to the file. Adding a character or replacing a
voice is a configuration change. The sheets and avatars themselves stay out of
the repository (ADR-0003).
"""

import logging
import re
import tomllib
from dataclasses import dataclass
from pathlib import Path

log = logging.getLogger(__name__)

_VALID_ID = re.compile(r"[a-z][a-z0-9_-]*")
_REQUIRED = ("id", "name", "intro", "voice_id", "sheet")


class CharacterConfigError(RuntimeError):
    pass


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    intro: str
    voice_id: str
    sheet: str
    avatar: Path | None


def load_characters(path: Path) -> dict[str, Character]:
    """Read the character configuration at `path`, keyed by identifier in file order."""
    path = path.resolve()
    try:
        config = tomllib.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise CharacterConfigError(f"找不到角色配置文件 {path}") from None
    except tomllib.TOMLDecodeError as e:
        raise CharacterConfigError(f"角色配置文件 {path} 格式有误：{e}") from None

    characters: dict[str, Character] = {}
    for entry in config.get("characters", []):
        character = _parse_character(entry, path.parent)
        if character.id in characters:
            raise CharacterConfigError(f"角色标识 {character.id} 重复")
        characters[character.id] = character
    if not characters:
        raise CharacterConfigError(f"角色配置文件 {path} 里没有任何角色")
    return characters


def _parse_character(entry: dict, base: Path) -> Character:
    label = entry.get("id", "（没有标识）")
    missing = [field for field in _REQUIRED if not isinstance(entry.get(field), str)]
    if missing:
        raise CharacterConfigError(f"角色 {label} 缺少字段 {'、'.join(missing)}")
    if not _VALID_ID.fullmatch(entry["id"]):
        raise CharacterConfigError(f"角色标识 {label} 只能包含小写字母、数字、- 和 _")

    sheet_path = base / entry["sheet"]
    try:
        sheet = sheet_path.read_text(encoding="utf-8").strip()
    except FileNotFoundError:
        raise CharacterConfigError(
            f"角色 {label} 的人设文件 {sheet_path} 不存在（可参考 sheets/example.md）"
        ) from None

    avatar = base / entry["avatar"] if isinstance(entry.get("avatar"), str) else None
    if avatar is not None and not avatar.is_file():
        log.warning("avatar %s of character %s is missing; showing none", avatar, label)
        avatar = None

    return Character(
        id=entry["id"],
        name=entry["name"],
        intro=entry["intro"],
        voice_id=entry["voice_id"],
        sheet=sheet,
        avatar=avatar,
    )
