"""What a photo is generated from (GLOSSARY.md「照片」): the photo tag she wrote, read field by
field, and the prompts the image service is sent for it.

She writes how the photo is taken (`shot`: a selfie, or someone else taking it), how much of
her it shows (`framing`), and three fields of English tags: where and when (`place`), what
she wears (`outfit`), what she does and how she looks (`action`); and a note in Chinese for
herself alone, never sent. What she writes is cleaned before it goes anywhere: the prompt
syntax NovelAI reads (emphasis, weights, alternation, comments, quotes, `Text:`) is
stripped, the tags put in lower case with spaces for underscores, written once, and each
field cut to its most; a field left empty gets its default.

The positive prompt is fixed around them: who she is (her character tag and the work's
tag), her looks, the tags for how the photo is taken, `rating:general` and V5's standard
quality tags, written out rather than left to the service's switch. The negative prompt is
fixed altogether: `nsfw`, the Human Focus preset, and what no photo of hers shows
(ADR-0023). Neither the deployer nor any user changes them.
"""

import re
from dataclasses import dataclass
from typing import Literal

from eidolon.characters import Character

WORK_TAG = "idolmaster shiny colors"
QUALITY_TAGS = ("rating:general", "very aesthetic", "masterpiece", "no text")
"""What every positive prompt ends with: all ages, then V5's standard quality tags."""

NEGATIVE_PROMPT = ", ".join((
    "nsfw",
    # The Human Focus preset: the Heavy one, with what goes wrong with faces.
    "lowres", "artistic error", "film grain", "scan artifacts", "worst quality", "bad quality",
    "jpeg artifacts", "very displeasing", "chromatic aberration", "dithering", "halftone",
    "screentone", "multiple views", "logo", "too many watermarks", "negative space",
    "blank page", "@_@", "mismatched pupils", "glowing eyes", "bad anatomy",
    # All ages (ADR-0023).
    "nude", "nipples", "underwear", "bra", "panties", "bra strap", "strap slip", "see-through",
    "pantyshot", "cleavage",
))

Shot = Literal["selfie", "other"]
Framing = Literal["portrait", "upper body", "cowboy shot", "full body"]
FRAMINGS: tuple[Framing, ...] = ("portrait", "upper body", "cowboy shot", "full body")
SELFIE_FRAMINGS: tuple[Framing, ...] = ("portrait", "upper body")
"""How much of her a selfie can show: no more than an arm's length takes in."""

FIELD_TAGS = 4
"""The most tags each of her three fields keeps: twelve at most in all."""
DEFAULTS = {"place": "indoors", "outfit": "casual", "action": "smile"}
"""What a field she left empty, or that comes to nothing once cleaned, is taken to say."""

LOOKING_AT_VIEWER = "looking at viewer"
_GAZES = ("looking", "eyes closed", "closed eyes")
"""What in her action says where she looks; without any, a photo someone else takes has her
looking at the camera."""

_WEIGHT = re.compile(r"-?\d+(\.\d+)?::|::|:-?\d+(\.\d+)?\b")
_TEXT = re.compile(r"\btext:", re.IGNORECASE)
_SYNTAX = re.compile(r"[{}\[\]|#\"'“”‘’`]")


@dataclass(frozen=True)
class PhotoTag:
    """A photo tag as read: how the photo is taken and how much of her it shows, and her
    three fields of tags, cleaned."""

    shot: Shot
    framing: Framing
    place: tuple[str, ...]
    outfit: tuple[str, ...]
    action: tuple[str, ...]


@dataclass(frozen=True)
class ImagePrompt:
    positive: str
    negative: str


def read_tag(text: str) -> PhotoTag:
    """The photo tag `text` says, one field a line (`shot: selfie`), whatever it leaves out or
    gets wrong taken as most likely meant: someone else taking it, from the waist up."""
    fields: dict[str, str] = {}
    for line in text.splitlines():
        name, colon, value = line.partition(":")
        if colon:
            fields.setdefault(name.strip().lower(), value.strip())
    shot: Shot = "selfie" if fields.get("shot", "").strip().lower() == "selfie" else "other"
    written = _cleaned(fields.get("framing", ""))
    framing: Framing = "upper body"
    for known in FRAMINGS:
        if known == written:
            framing = known
    if shot == "selfie" and framing not in SELFIE_FRAMINGS:
        framing = "upper body"
    seen = set(_shot_tags(shot)) | {framing}
    place, outfit, action = (_field(fields.get(name, ""), name, seen) for name in DEFAULTS)
    return PhotoTag(shot, framing, place, outfit, action)


def image_prompt(character: Character, tag: PhotoTag) -> ImagePrompt:
    """The prompts a photo of `character` (who has her photo tags) is generated from, as
    `tag` says it is taken."""
    assert character.photo_tag is not None and character.photo_appearance is not None
    action = tag.action
    if tag.shot == "other" and not any(g in t for t in action for g in _GAZES):
        action = (*action, LOOKING_AT_VIEWER)
    positive = (
        "1girl", "solo", character.photo_tag, WORK_TAG, character.photo_appearance,
        *_shot_tags(tag.shot), tag.framing, *tag.place, *tag.outfit, *action, *QUALITY_TAGS,
    )
    return ImagePrompt(", ".join(positive), NEGATIVE_PROMPT)


def _shot_tags(shot: Shot) -> tuple[str, ...]:
    return ("selfie", LOOKING_AT_VIEWER) if shot == "selfie" else ()


def _field(value: str, name: str, seen: set[str]) -> tuple[str, ...]:
    """The tags of one of her fields, cleaned, those already written elsewhere left out
    (and added to `seen`), cut to `FIELD_TAGS`; its default if none are left."""
    tags: list[str] = []
    for raw in re.split(r"[,，、]", value):
        tag = _cleaned(raw)
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tuple(tags[:FIELD_TAGS]) or (DEFAULTS[name],)


def _cleaned(tag: str) -> str:
    """`tag` without NovelAI's prompt syntax, in lower case, a space for each underscore."""
    tag = _TEXT.sub("", tag)
    tag = _WEIGHT.sub("", tag)
    tag = _SYNTAX.sub("", tag)
    return " ".join(tag.replace("_", " ").lower().split())
