"""Voicing the greetings and putting them where browsers hear them: `eidolon greeting upload`.

Each greeting the character configuration has (`Character.greeting`, GLOSSARY.md「招呼」)
is voiced once in her voice, delivery cues and all, over Fish Audio's HTTP API as mp3, and
put in the stands' bucket under `greetings/<id>-<hash>.mp3` (`greeting_path`): the hash is
of what she says, cues and all, and of her voice. So the server says where it is without
asking the bucket; a greeting whose words or voice changed is at an address no browser
has cached; and one the bucket already has is not voiced again. Once hers is up, her
greetings at other addresses are deleted, and so are those of characters who no longer
have one. Clearing the bucket takes them down along with
the stands (ADR-0003, revised 2026-10-10).

They are voiced on the deployer's key, as `.env` has it (`FISH_AUDIO_API_KEY`,
`FISH_AUDIO_MODEL`; not what the admin console may have changed it to), and are no turn:
nothing is recorded of them and they count against no one's limit. Visitors only ever
download what was voiced here; nothing is voiced for them.
"""

import hashlib
import os
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

import httpx

from eidolon.characters import Character
from eidolon.config import DEFAULT_FISH_AUDIO_MODEL
from eidolon.delivery_cues import voiced
from eidolon.s3 import Bucket, S3Error, S3Settings

GREETINGS_DIR = "greetings"
GREETING_CACHE = "public, max-age=31536000, immutable"
"""A greeting's audio never changes at its address: new words or a new voice are a new one."""
FISH_TTS_HTTP_URL = "https://api.fish.audio/v1/tts"
_HASH_LENGTH = 12
_TIMEOUT = httpx.Timeout(60, connect=10)
"""A greeting is a few seconds of audio, voiced in a few seconds more."""

SOME_FAILED = 3
"""The exit code when some greetings could not be voiced or put; 2 is the bucket failing
to be listed, so that nothing was."""


def greeting_path(character: Character) -> str | None:
    """Where her greeting's audio is in the bucket, as the command puts it there; None
    without a greeting, or without a voice to say it in."""
    greeting = character.greeting
    if greeting is None or not character.voice_id.strip():
        return None
    digest = hashlib.sha256(f"{character.voice_id}\n{greeting.text}".encode()).hexdigest()
    return f"{GREETINGS_DIR}/{character.id}-{digest[:_HASH_LENGTH]}.mp3"


def _hers(character: Character) -> re.Pattern[str]:
    """Her greetings' paths, whatever they said: not those of another character whose
    identifier starts with hers (`mano-2`)."""
    return re.compile(rf"{GREETINGS_DIR}/{re.escape(character.id)}-[0-9a-f]{{{_HASH_LENGTH}}}\.mp3")


_ANYONES = re.compile(rf"{GREETINGS_DIR}/.+-[0-9a-f]{{{_HASH_LENGTH}}}\.mp3")
"""A greeting's path, whoever's it is."""


@dataclass(frozen=True)
class FishAudioSettings:
    """The deployer's key for Fish Audio, and the model it voices with."""

    api_key: str
    model: str = DEFAULT_FISH_AUDIO_MODEL

    @classmethod
    def from_env(cls) -> "FishAudioSettings":
        api_key = (os.environ.get("FISH_AUDIO_API_KEY") or "").strip()
        if not api_key:
            raise RuntimeError("合成招呼要用部署者的语音合成 key，环境变量 FISH_AUDIO_API_KEY 未设置")
        model = (os.environ.get("FISH_AUDIO_MODEL") or "").strip() or DEFAULT_FISH_AUDIO_MODEL
        return cls(api_key, model)


class _Failed(RuntimeError):
    """Her greeting could not be voiced, put, or have its old versions deleted."""


@dataclass
class GreetingReport:
    voiced: list[str] = field(default_factory=list)
    """The names of the characters whose greetings were voiced and put this time."""
    unchanged: int = 0
    """Greetings the bucket already had, not voiced again."""
    deleted: list[str] = field(default_factory=list)
    """Old versions deleted."""
    failed: list[tuple[str, str]] = field(default_factory=list)
    """The name of each character whose greeting failed, and why."""

    @property
    def exit_code(self) -> int:
        return SOME_FAILED if self.failed else 0


async def upload_greetings(
    characters: Iterable[Character],
    bucket: S3Settings,
    fish: FishAudioSettings,
    *,
    transport: httpx.AsyncBaseTransport | None = None,
) -> GreetingReport:
    """Voice what greetings of `characters` the bucket lacks, put them in it, and delete
    their old versions. One that fails is reported and the rest go on; raises S3Error,
    having voiced nothing, if the bucket cannot be listed."""
    greeted = [c for c in characters if c.greeting is not None]
    report = GreetingReport()
    storage = Bucket(bucket, transport=transport)
    try:
        async with httpx.AsyncClient(transport=transport, timeout=_TIMEOUT) as client:
            keys = set(await storage.keys(f"{GREETINGS_DIR}/"))
            for character in greeted:
                try:
                    await _upload(character, keys, storage, client, fish, report)
                except _Failed as e:
                    report.failed.append((character.name, str(e)))
            await _delete_unclaimed(keys, greeted, storage, report)
    finally:
        await storage.aclose()
    return report


async def _delete_unclaimed(
    keys: set[str], greeted: list[Character], storage: Bucket, report: GreetingReport
) -> None:
    """Delete the greetings of characters who no longer have one, or are no longer
    configured: nothing points at them, and the bucket is public."""
    hers = [_hers(c) for c in greeted]
    for key in sorted(keys):
        if not _ANYONES.fullmatch(key) or any(p.fullmatch(key) for p in hers):
            continue
        try:
            await storage.delete(key)
        except S3Error as e:
            report.failed.append((key, f"配置里已经没有这句招呼，它没删掉（下次运行会再删）：{e}"))
        else:
            report.deleted.append(key)


async def _upload(
    character: Character,
    keys: set[str],
    storage: Bucket,
    client: httpx.AsyncClient,
    fish: FishAudioSettings,
    report: GreetingReport,
) -> None:
    assert character.greeting is not None
    path = greeting_path(character)
    if path is None:
        raise _Failed("没有音色：characters.toml 里她的 voice_id 是空的")
    if path in keys:
        report.unchanged += 1
    else:
        audio = await _voice(client, fish, voiced(character.greeting.text), character.voice_id)
        try:
            await storage.put(path, audio, "audio/mpeg", GREETING_CACHE)
        except S3Error as e:
            raise _Failed(f"上传失败：{e}") from None
        report.voiced.append(character.name)
    old = sorted(key for key in keys if key != path and _hers(character).fullmatch(key))
    for key in old:
        try:
            await storage.delete(key)
        except S3Error as e:
            raise _Failed(f"新的已上传，旧版本 {key} 没删掉（下次运行会再删）：{e}") from None
        report.deleted.append(key)


async def _voice(client: httpx.AsyncClient, fish: FishAudioSettings, text: str, voice_id: str) -> bytes:
    """`text` said in the voice `voice_id`, as mp3."""
    try:
        response = await client.post(
            FISH_TTS_HTTP_URL,
            headers={"Authorization": f"Bearer {fish.api_key}", "model": fish.model},
            json={"text": text, "reference_id": voice_id, "format": "mp3"},
        )
    except httpx.HTTPError as e:
        raise _Failed(f"连不上 Fish Audio：{e!r}") from None
    if response.is_error:
        raise _Failed(f"Fish Audio 没能合成：{response.status_code} {response.text[:200]}")
    if not response.content:
        raise _Failed("Fish Audio 没有返回音频")
    return response.content
