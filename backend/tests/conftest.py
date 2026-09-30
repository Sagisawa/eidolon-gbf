import json
from collections.abc import AsyncIterator, Callable
from dataclasses import replace
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from typing import Any

import httpx
import pipecat.utils.string
import pytest

from eidolon.__main__ import main
from eidolon.app import create_app
from eidolon.assembly import Backend, build
from eidolon.config import LLMSettings, Settings
from eidolon.identity import Identity
from eidolon.sessions import SESSION_COOKIE
from eidolon.store import Store
from tests.browser import Browser, open_browser
from tests.fakes import (
    DEPLOYER_FISH_KEY,
    DEPLOYER_SONIOX_KEY,
    START,
    FakeBackgroundLLM,
    FakeIdentityProvider,
    FakeLLM,
    FakeLLMService,
    FakeSpeech,
)
from tests.stories import write_sample_stories


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


ClientFactory = Callable[..., httpx.AsyncClient]

MANO_SHEET = "# 人设\n你是櫻木真乃。口癖是「ほわっ」。"
KOGANE_SHEET = "# 人设\n你是月岡恋鐘。说长崎方言。"
AVATAR = b"\x89PNG\r\n\x1a\n fake avatar"
BACKGROUND = b"\xff\xd8\xff fake background"


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
        color: str | None = "#ffbad6",
        background: bytes | None = None,
        speakers: list[str] | None = None,
        facts: str | None = None,
        idol_id: int | None = None,
        default_outfit: str | None = None,
    ) -> "CharacterConfig":
        entry = f'[[characters]]\nid = "{id}"\nname = "{name}"\nintro = "{intro}"\n'
        entry += f'voice_id = "{voice_id}"\nsheet = "sheets/{id}.md"\n'
        if sheet is not None:
            self.write(f"sheets/{id}.md", sheet)
        if avatar is not None:
            self.write(f"avatars/{id}.png", avatar)
            entry += f'avatar = "avatars/{id}.png"\n'
        if color is not None:
            entry += f'color = "{color}"\n'
        if background is not None:
            self.write(f"backgrounds/{id}.jpg", background)
            entry += f'background = "backgrounds/{id}.jpg"\n'
        if facts is not None:
            self.write(f"facts/{id}.md", facts)
            entry += f'facts = "facts/{id}.md"\n'
        if speakers is not None:
            entry += f"speakers = {json.dumps(speakers, ensure_ascii=False)}\n"
        if idol_id is not None:
            entry += f"idol_id = {idol_id}\n"
        if default_outfit is not None:
            entry += f'default_outfit = "{default_outfit}"\n'
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
    """Mano (with an avatar, a background and a stand) and Kogane (with none of them)."""
    return (
        CharacterConfig(tmp_path / "characters")
        .add(
            "mano", "櫻木真乃", MANO_SHEET, intro="illumination STARS 的中心", avatar=AVATAR,
            color="#ffbad6", background=BACKGROUND, speakers=["真乃"], voice_id="mano-voice",
            idol_id=1, default_outfit="stand/1030010010",
        )
        .add(
            "kogane", "月岡恋鐘", KOGANE_SHEET, intro="L'Antica 的偶像", color="#f84cad",
            speakers=["恋鐘"], voice_id="kogane-voice",
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
        dev_login=True,
        secret_key="test-secret-key",
        soniox_api_key=DEPLOYER_SONIOX_KEY,
        fish_audio_api_key=DEPLOYER_FISH_KEY,
    )


@pytest.fixture
def admin(settings: Settings, capsys: pytest.CaptureFixture[str]) -> Admin:
    return Admin(settings.database_path, capsys)


SITE = {"Origin": "http://localhost:3000"}
"""What the tests' clients send as browsers do: they are the site's own pages."""

COOKIE_DOMAIN = "test.local"
"""Where the cookies of the tests' clients (at http://test) are kept, as for any host
without a dot."""


def sign_in(store: Store, name: str, now: datetime) -> httpx.Cookies:
    """The cookies of a new session for the first user named `name`, who is made, having
    agreed to the terms, if there is none."""
    user = store.first_user_named(name) or store.create_user(name)
    if user.consented_at is None:
        store.consent(user.id, now)
    cookies = httpx.Cookies()
    cookies.set(SESSION_COOKIE, store.create_session(user.id, now), domain=COOKIE_DOMAIN)
    return cookies


def github_identity(
    subject: str = "1001",
    name: str = "producer",
    *,
    email: str | None = "producer@example.com",
    created_at: datetime = START - timedelta(days=800),
) -> Identity:
    return Identity("github", subject, name, email, email is not None, created_at)


def google_identity(
    subject: str = "g-1001",
    name: str = "Producer",
    *,
    email: str = "producer@example.com",
    verified: bool = True,
) -> Identity:
    return Identity("google", subject, name, email, verified, None)


async def sign_in_with(
    client: httpx.AsyncClient,
    provider: FakeIdentityProvider,
    identity: Identity,
    *,
    link: bool = False,
) -> httpx.Response:
    """Go through signing in at `provider` as `identity`, or with `link`, linking it to the
    signed-in user; the response to the callback."""
    start = await client.get(
        f"/api/auth/{provider.name}/start", params={"link": "1"} if link else None
    )
    assert start.status_code == 302, start.text
    [state] = parse_qs(urlsplit(start.headers["location"]).query)["state"]
    code = provider.will_identify(identity)
    return await client.get(
        f"/api/auth/{provider.name}/callback", params={"code": code, "state": state}
    )


async def agree_to_terms(client: httpx.AsyncClient) -> None:
    res = await client.post(
        "/api/account/consent", json={"agree_to_terms": True, "at_least_13": True}
    )
    assert res.status_code == 204, res.text


def sign_in_as(client: httpx.AsyncClient, other: httpx.AsyncClient) -> None:
    """Have `client` carry the session `other` carries from now on."""
    client.cookies.set(SESSION_COOKIE, other.cookies[SESSION_COOKIE], domain=COOKIE_DOMAIN)


@pytest.fixture
def speech(monkeypatch: pytest.MonkeyPatch) -> FakeSpeech:
    """Soniox and Fish Audio, faked. Tests run offline, without the NLTK data Pipecat splits
    replies into sentences with; a splitter that never splits sends Pipecat to its own
    split at 。！？, which is what NLTK does with Japanese anyway."""
    monkeypatch.setattr(pipecat.utils.string, "_sent_tokenizer", lambda: lambda text: [text])
    return FakeSpeech()


@pytest.fixture
def own_llm() -> FakeLLMService:
    """The LLM services users bring their own keys to, faked."""
    return FakeLLMService()


@pytest.fixture
def github() -> FakeIdentityProvider:
    return FakeIdentityProvider("github")


@pytest.fixture
def google() -> FakeIdentityProvider:
    return FakeIdentityProvider("google")


@pytest.fixture
async def browser() -> AsyncIterator[Browser]:
    """The browser placing a call in the test."""
    async with open_browser() as browser:
        yield browser


@pytest.fixture
async def make_client(
    settings: Settings,
    speech: FakeSpeech,
    github: FakeIdentityProvider,
    google: FakeIdentityProvider,
    own_llm: FakeLLMService,
) -> AsyncIterator[ClientFactory]:
    """Makes API clients; each is signed in as the user with the given name, by default
    the producer, who has agreed to the terms (None for a client not signed in).
    Any other keyword is an outside service to use instead of the one the settings
    describe (see `assembly.build`); the background model, speech, the identity providers
    (the `github` and `google` fixtures) and the LLM services users bring their own keys
    to (`own_llm`) are fakes by default, and `voice_configured=False` leaves the deployer
    without speech keys."""
    backends: list[Backend] = []
    clients: list[httpx.AsyncClient] = []

    def factory(
        llm: FakeLLM,
        user: str | None = "producer",
        *,
        settings: Settings = settings,
        voice_configured: bool = True,
        **services: Any,
    ) -> httpx.AsyncClient:
        services.setdefault("background_llm", FakeBackgroundLLM())
        services.setdefault("identity_providers", {"github": github, "google": google})
        services.setdefault("own_llm_service", own_llm)
        services.setdefault("speech", speech)
        if not voice_configured:
            settings = replace(settings, soniox_api_key=None, fish_audio_api_key=None)
        backend = build(settings, chat_llm=llm, **services)
        backends.append(backend)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=create_app(backend)),
            base_url="http://test",
            headers=SITE,
            cookies=sign_in(backend.store, user, backend.clock()) if user is not None else None,
        )
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()
    for backend in backends:  # the test transport runs no lifespan to close it
        await backend.aclose()
