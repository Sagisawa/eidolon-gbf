import json
import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from eidolon.__main__ import main
from eidolon.app import create_app
from eidolon.config import Settings
from eidolon.engine import Clock
from tests.fakes import FakeCalls, FakeEmbedder, FakeJudge, FakeLLM, FakeReranker
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
            speakers=["真乃"],
        )
        .add("kogane", "月岡恋鐘", KOGANE_SHEET, intro="L'Antica 的偶像", speakers=["恋鐘"])
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
        chat_llm_base_url="http://llm.invalid/v1",
        chat_llm_api_key="test-key",
        chat_llm_model="test-model",
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
async def calls() -> AsyncIterator[FakeCalls]:
    fake = FakeCalls()
    yield fake
    await fake.hang_up_all()


@pytest.fixture
async def make_client(
    settings: Settings, producer_key: IssuedKey, calls: FakeCalls
) -> AsyncIterator[ClientFactory]:
    """Makes API clients; each carries the given access key, by default the producer's."""
    clients: list[httpx.AsyncClient] = []

    def factory(
        llm: FakeLLM,
        key: str | None = producer_key.secret,
        *,
        settings: Settings = settings,
        calls_configured: bool = True,
        clock: Clock | None = None,
        jev: FakeJudge | None = None,
        embedder: FakeEmbedder | None = None,
        reranker: FakeReranker | None = None,
    ) -> httpx.AsyncClient:
        app = create_app(
            settings,
            chat_llm=llm,
            call_starter=calls if calls_configured else None,
            clock=clock,
            jev=jev,
            embedder=embedder,
            reranker=reranker,
        )
        headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
        )
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()
