import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx
import pipecat.utils.string
import pytest

from eidolon.__main__ import main
from eidolon.app import create_app
from eidolon.assembly import Backend, build
from eidolon.config import LLMSettings, Settings
from tests.browser import Browser, open_browser
from tests.fakes import FakeBackgroundLLM, FakeLLM, FakeSpeech
from tests.stories import write_sample_stories


@dataclass(frozen=True)
class IssuedKey:
    id: str
    secret: str


class Admin:
    """Drives the admin command line against the test database."""

    def __init__(self, database_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        self._database_path = database_path
        self._capsys = capsys

    def run(self, *args: str) -> str:
        code, out, err = self._invoke(args)
        assert code == 0, err
        return out

    def fails(self, *args: str) -> str:
        code, _, err = self._invoke(args)
        assert code != 0
        return err

    def invoke(self, *args: str) -> tuple[int, str, str]:
        """The exit code, standard output and standard error."""
        return self._invoke(args)

    def _invoke(self, args: tuple[str, ...]) -> tuple[int, str, str]:
        self._capsys.readouterr()
        code = main(["--db", str(self._database_path), *args])
        captured = self._capsys.readouterr()
        return code, captured.out, captured.err

    def create_user(self, name: str) -> None:
        self.run("user", "create", name)

    def issue_key(self, user: str) -> IssuedKey:
        out = self.run("key", "issue", user)
        key_id = re.search(r"访问密钥 (\w+)", out)
        secret = re.search(r"esc_\S+", out)
        assert key_id and secret, out
        return IssuedKey(key_id.group(1), secret.group(0))

    def revoke_key(self, key_id: str) -> None:
        self.run("key", "revoke", key_id)


ClientFactory = Callable[..., httpx.AsyncClient]

MANO_SHEET = "# 人设\n你是櫻木真乃。口癖是「ほわっ」。"
KOGANE_SHEET = "# 人设\n你是月岡恋鐘。说长崎方言。"
AVATAR = b"\x89PNG\r\n\x1a\n fake avatar"


class CharacterConfig:
    """Writes a character configuration directory, the way an administrator would."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self.path = directory / "characters.toml"
        self._entries: list[str] = []

    def add(
        self,
        id: str,
        name: str,
        sheet: str | None,
        *,
        intro: str = "",
        voice_id: str = "voice",
        avatar: bytes | None = None,
        speakers: list[str] | None = None,
        facts: str | None = None,
    ) -> "CharacterConfig":
        entry = f'[[characters]]\nid = "{id}"\nname = "{name}"\nintro = "{intro}"\n'
        entry += f'voice_id = "{voice_id}"\nsheet = "sheets/{id}.md"\n'
        if sheet is not None:
            self.write(f"sheets/{id}.md", sheet)
        if avatar is not None:
            self.write(f"avatars/{id}.png", avatar)
            entry += f'avatar = "avatars/{id}.png"\n'
        if facts is not None:
            self.write(f"facts/{id}.md", facts)
            entry += f'facts = "facts/{id}.md"\n'
        if speakers is not None:
            entry += f"speakers = {json.dumps(speakers, ensure_ascii=False)}\n"
        self._entries.append(entry)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.path.write_text("\n".join(self._entries), encoding="utf-8")
        return self

    def write(self, relative: str, content: str | bytes) -> None:
        target = self.directory / relative
        target.parent.mkdir(parents=True, exist_ok=True)
        if isinstance(content, bytes):
            target.write_bytes(content)
        else:
            target.write_text(content, encoding="utf-8")


@pytest.fixture
def characters(tmp_path: Path) -> CharacterConfig:
    """Mano (with an avatar) and Kogane (without one)."""
    return (
        CharacterConfig(tmp_path / "characters")
        .add(
            "mano", "櫻木真乃", MANO_SHEET, intro="illumination STARS 的中心", avatar=AVATAR,
            speakers=["真乃"], voice_id="mano-voice",
        )
        .add(
            "kogane", "月岡恋鐘", KOGANE_SHEET, intro="L'Antica 的偶像", speakers=["恋鐘"],
            voice_id="kogane-voice",
        )
    )


@pytest.fixture
def story(tmp_path: Path) -> Path:
    """A directory of sample story CSVs: Mano's W.I.N.G. episodes (won, and failure endings),
    a card of Kogane's that Mano also speaks in, and an event with neither."""
    return write_sample_stories(tmp_path / "story")


@pytest.fixture
def settings(tmp_path: Path, characters: CharacterConfig) -> Settings:
    return Settings(
        database_path=tmp_path / "eidolon.db",
        characters_path=characters.path,
        chat_llm=LLMSettings("http://llm.invalid/v1", "test-key", "test-model"),
        ice_servers=[],  # tests run offline: gather host candidates only
    )


@pytest.fixture
def admin(settings: Settings, capsys: pytest.CaptureFixture[str]) -> Admin:
    return Admin(settings.database_path, capsys)


@pytest.fixture
def producer_key(admin: Admin) -> IssuedKey:
    admin.create_user("producer")
    return admin.issue_key("producer")


@pytest.fixture
def speech(monkeypatch: pytest.MonkeyPatch) -> FakeSpeech:
    """Soniox and Fish Audio, faked. Tests run offline, without the NLTK data Pipecat splits
    replies into sentences with; a splitter that never splits sends Pipecat to its own
    split at 。！？, which is what NLTK does with Japanese anyway."""
    monkeypatch.setattr(pipecat.utils.string, "_sent_tokenizer", lambda: lambda text: [text])
    return FakeSpeech()


@pytest.fixture
async def browser() -> AsyncIterator[Browser]:
    """The browser placing a call in the test."""
    async with open_browser() as browser:
        yield browser


@pytest.fixture
async def make_client(
    settings: Settings, producer_key: IssuedKey, speech: FakeSpeech
) -> AsyncIterator[ClientFactory]:
    """Makes API clients; each carries the given access key, by default the producer's.
    Any other keyword is an outside service to use instead of the one the settings
    describe (see `assembly.build`); the background model and speech are fakes by default,
    and `voice_configured=False` leaves calls unconfigured."""
    backends: list[Backend] = []
    clients: list[httpx.AsyncClient] = []

    def factory(
        llm: FakeLLM,
        key: str | None = producer_key.secret,
        *,
        settings: Settings = settings,
        voice_configured: bool = True,
        **services: Any,
    ) -> httpx.AsyncClient:
        services.setdefault("background_llm", FakeBackgroundLLM())
        if voice_configured:
            services.setdefault("speech", speech)
        backend = build(settings, chat_llm=llm, **services)
        backends.append(backend)
        headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(backend)),
            base_url="http://test",
            headers=headers,
        )
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()
    for backend in backends:  # the test transport runs no lifespan to close it
        await backend.aclose()
