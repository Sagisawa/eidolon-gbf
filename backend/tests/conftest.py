from collections.abc import AsyncIterator, Callable
from pathlib import Path

import httpx
import pytest

from eidolon.app import create_app
from eidolon.config import Settings
from tests.fakes import FakeLLM

ClientFactory = Callable[[FakeLLM], httpx.AsyncClient]


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_path=tmp_path / "eidolon.db",
        chat_llm_base_url="http://llm.invalid/v1",
        chat_llm_api_key="test-key",
        chat_llm_model="test-model",
    )


@pytest.fixture
async def make_client(settings: Settings) -> AsyncIterator[ClientFactory]:
    clients: list[httpx.AsyncClient] = []

    def factory(llm: FakeLLM) -> httpx.AsyncClient:
        app = create_app(settings, chat_llm=llm)
        client = httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        )
        clients.append(client)
        return client

    yield factory
    for client in clients:
        await client.aclose()
