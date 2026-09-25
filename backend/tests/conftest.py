import re
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from pathlib import Path

import httpx
import pytest

from eidolon.__main__ import main
from eidolon.app import create_app
from eidolon.config import Settings
from tests.fakes import FakeLLM


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
        self._capsys.readouterr()
        code = main(["--db", str(self._database_path), *args])
        out = self._capsys.readouterr()
        assert code == 0, out.err
        return out.out

    def fails(self, *args: str) -> str:
        self._capsys.readouterr()
        code = main(["--db", str(self._database_path), *args])
        assert code != 0
        return self._capsys.readouterr().err

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


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "eidolon.db",
        chat_llm_base_url="http://llm.invalid/v1",
        chat_llm_api_key="test-key",
        chat_llm_model="test-model",
    )


@pytest.fixture
def admin(settings: Settings, capsys: pytest.CaptureFixture[str]) -> Admin:
    return Admin(settings.database_path, capsys)


@pytest.fixture
def producer_key(admin: Admin) -> IssuedKey:
    admin.create_user("producer")
    return admin.issue_key("producer")


@pytest.fixture
async def make_client(
    settings: Settings, producer_key: IssuedKey
) -> AsyncIterator[ClientFactory]:
    """Makes API clients; each carries the given access key, by default the producer's."""
    clients: list[httpx.AsyncClient] = []

    def factory(llm: FakeLLM, key: str | None = producer_key.secret) -> httpx.AsyncClient:
        app = create_app(settings, chat_llm=llm)
        headers = {"Authorization": f"Bearer {key}"} if key is not None else {}
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test", headers=headers
        )
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()
