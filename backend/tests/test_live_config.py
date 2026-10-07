"""The live configuration: admins change the deployer's chat model in the admin console
(ADR-0013). A change is tried before it is kept, then plays the next turn and the next
call, while calls already connected keep the model they connected with; it overrides
`.env` until restored, and one that no longer works when the server starts falls back to
`.env`, marked as such. The clients are made by a fake `ServiceClients`."""

import asyncio
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from eidolon.assembly import Backend
from eidolon.config import LLMSettings, Settings
from tests.browser import Browser, open_browser, until_gone
from tests.conftest import ClientFactory, agree_to_terms, github_identity, sign_in_with
from tests.fakes import (
    DEPLOYER_KEY,
    FakeIdentityProvider,
    FakeLLM,
    FakeServiceClients,
    FakeSpeech,
)
from tests.test_text_turn import send_turn, start_conversation

CONFIG = "/api/admin/config"
CHAT_LLM = "/api/admin/config/chat_llm"
REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]

NEW_KEY = "sk-new-key-5678"
NEW = {
    "protocol": "anthropic",
    "base_url": "https://llm.example/v1",
    "model": "new-model",
    "max_tokens": 1024,
    "api_key": NEW_KEY,
}
NEW_SETTINGS = LLMSettings("https://llm.example/v1", NEW_KEY, "new-model", "anthropic", 1024)
NEW_SHOWN = {k: v for k, v in NEW.items() if k != "api_key"} | {"api_key_last4": "5678"}
ENV_SETTINGS = LLMSettings("http://llm.invalid/v1", DEPLOYER_KEY, "test-model")
ENV_SHOWN = {
    "protocol": "chat-completions",
    "base_url": "http://llm.invalid/v1",
    "model": "test-model",
    "max_tokens": None,
    "api_key_last4": DEPLOYER_KEY[-4:],
}


@pytest.fixture
def admins(settings: Settings) -> Settings:
    return replace(settings, admins=frozenset({("github", "1001")}))


async def admin_client(
    make_client: ClientFactory,
    settings: Settings,
    github: FakeIdentityProvider,
    clients: FakeServiceClients,
) -> httpx.AsyncClient:
    """A client signed in as the admin, on a backend whose chat models `clients` makes."""
    client = make_client(clients.llm, user=None, settings=settings, clients=clients)
    await sign_in_with(client, github, github_identity("1001"))
    await agree_to_terms(client)
    return client


def recorded(client: httpx.AsyncClient, service: str) -> list[tuple[str, str, bool]]:
    """The service calls to `service` recorded so far, by provider, model and whether on
    the user's own key, sorted."""
    backend: Backend = client._transport.app.state.backend  # pyright: ignore[reportAttributeAccessIssue]
    _, calls = backend.activity.since(backend.clock() - timedelta(days=1))
    return sorted((c.provider, c.model, c.own_key) for c in calls if c.service == service)


async def until(done: Callable[[], object]) -> None:
    """Wait, a while at most, for `done` to come true, as what a call let go of closes."""
    for _ in range(100):
        if done():
            return
        await asyncio.sleep(0.02)


async def start(client: httpx.AsyncClient) -> None:
    """What the server does as it starts, before serving anyone."""
    backend: Backend = client._transport.app.state.backend  # pyright: ignore[reportAttributeAccessIssue]
    await backend.start()


async def test_a_saved_chat_model_plays_the_next_turn_until_restored(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    clients = FakeServiceClients(FakeLLM(REPLY, REPLY, REPLY))
    client = await admin_client(make_client, admins, github, clients)
    conversation_id = await start_conversation(client)
    before = (await client.get(CONFIG)).json()
    await send_turn(client, conversation_id, "早上好")

    saved = await client.put(CHAT_LLM, json=NEW)
    assert saved.status_code == 200, saved.text
    await send_turn(client, conversation_id, "你好")
    shown = (await client.get(CONFIG)).json()
    restored = await client.delete(CHAT_LLM)
    assert restored.status_code == 200, restored.text
    await send_turn(client, conversation_id, "再见")

    unchanged = {"status": "env", "env": ENV_SHOWN, "effective": ENV_SHOWN, "override": None,
                 "failure": None}
    assert before["keys_editable"] is True and before["chat_llm"] == unchanged
    assert shown == saved.json()
    assert shown["chat_llm"] == {"status": "overridden", "env": ENV_SHOWN, "effective": NEW_SHOWN,
                                 "override": NEW_SHOWN, "failure": None}
    assert NEW_KEY not in saved.text and DEPLOYER_KEY not in saved.text
    assert restored.json() == before
    assert clients.llm.keys == [DEPLOYER_KEY, NEW_KEY, DEPLOYER_KEY]
    assert clients.opened == [ENV_SETTINGS, NEW_SETTINGS, ENV_SETTINGS]
    assert clients.closed == [ENV_SETTINGS, NEW_SETTINGS]  # each once no turn was on it


async def test_a_chat_model_that_fails_its_try_is_not_saved(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    clients = FakeServiceClients(FakeLLM(REPLY))
    clients.rejects[NEW_KEY] = "401 invalid api key"
    client = await admin_client(make_client, admins, github, clients)
    conversation_id = await start_conversation(client)

    res = await client.put(CHAT_LLM, json=NEW)
    await send_turn(client, conversation_id, "早上好")

    assert res.status_code == 422
    assert "401 invalid api key" in res.json()["detail"]
    assert (await client.get(CONFIG)).json()["chat_llm"]["status"] == "env"
    assert clients.llm.keys == [DEPLOYER_KEY]
    assert clients.closed == [NEW_SETTINGS]


async def test_a_call_keeps_the_chat_model_it_connected_with(
    make_client: ClientFactory,
    admins: Settings,
    github: FakeIdentityProvider,
    speech: FakeSpeech,
    browser: Browser,
):
    clients = FakeServiceClients(FakeLLM(REPLY, REPLY))
    client = await admin_client(make_client, admins, github, clients)
    conversation_id = await start_conversation(client)
    assert (await client.put(CHAT_LLM, json=NEW)).status_code == 200
    await browser.call(client, conversation_id=conversation_id)
    await browser.connect()
    assert browser.pc_id is not None

    other = NEW | {"api_key": "sk-other-key-9999", "model": "other-model"}
    assert (await client.put(CHAT_LLM, json=other)).status_code == 200
    await speech.stts[-1].hear("早上好")
    await browser.turn()
    assert clients.llm.keys == [NEW_KEY]
    assert clients.closed == [ENV_SETTINGS]  # the call is still on the new one

    await browser.close()
    await until_gone(client, browser.pc_id)
    async with open_browser() as again:
        await again.call(client, conversation_id=conversation_id)
        await again.connect()
        await speech.stts[-1].hear("你好")
        await again.turn()

    assert clients.llm.keys == [NEW_KEY, "sk-other-key-9999"]
    assert clients.closed == [ENV_SETTINGS, NEW_SETTINGS]
    # Each call's turn is recorded as the model it connected with.
    await until(lambda: len(recorded(client, "chat_llm")) == 2)  # as the call is written
    assert recorded(client, "chat_llm") == [
        ("llm.example", "new-model", False), ("llm.example", "other-model", False)
    ]


async def test_without_the_secret_key_the_chat_models_key_is_read_only(
    make_client: ClientFactory, admins: Settings, github: FakeIdentityProvider
):
    clients = FakeServiceClients(FakeLLM(REPLY))
    client = await admin_client(make_client, replace(admins, secret_key=None), github, clients)
    conversation_id = await start_conversation(client)

    with_key = await client.put(CHAT_LLM, json=NEW)
    without_key = await client.put(CHAT_LLM, json={k: v for k, v in NEW.items() if k != "api_key"})
    await send_turn(client, conversation_id, "早上好")

    assert with_key.status_code == 409
    assert "EIDOLON_SECRET_KEY" in with_key.json()["detail"]
    assert without_key.status_code == 200, without_key.text
    shown = without_key.json()
    assert shown["keys_editable"] is False
    assert shown["chat_llm"]["effective"] == NEW_SHOWN | {"api_key_last4": DEPLOYER_KEY[-4:]}
    assert clients.opened == [ENV_SETTINGS, replace(NEW_SETTINGS, api_key=DEPLOYER_KEY)]
    assert clients.llm.keys == [DEPLOYER_KEY]


async def test_an_override_that_fails_its_try_as_the_server_starts_falls_back_to_env(
    make_client: ClientFactory,
    admins: Settings,
    github: FakeIdentityProvider,
    caplog: pytest.LogCaptureFixture,
):
    caplog.set_level(logging.INFO)
    first = await admin_client(make_client, admins, github, FakeServiceClients())
    assert (await first.put(CHAT_LLM, json=NEW)).status_code == 200

    # Restarted, the override still works.
    working = FakeServiceClients(FakeLLM(REPLY))
    restarted = await admin_client(make_client, admins, github, working)
    await start(restarted)
    await send_turn(restarted, await start_conversation(restarted), "早上好")
    assert working.llm.keys == [NEW_KEY]
    assert "chat_llm" in caplog.text and "overrides in effect" in caplog.text

    # Restarted again after the key was revoked.
    caplog.clear()
    revoked = FakeServiceClients(FakeLLM(REPLY))
    revoked.rejects[NEW_KEY] = "401 key revoked"
    again = await admin_client(make_client, admins, github, revoked)
    await start(again)
    await send_turn(again, await start_conversation(again), "早上好")

    shown = (await again.get(CONFIG)).json()["chat_llm"]
    assert shown["status"] == "failed"
    assert "401 key revoked" in shown["failure"]
    assert shown["effective"] == ENV_SHOWN and shown["override"] == NEW_SHOWN
    assert revoked.llm.keys == [DEPLOYER_KEY]
    assert any(
        r.levelno == logging.WARNING and "401 key revoked" in r.getMessage()
        for r in caplog.records
    )


async def test_a_key_the_changed_secret_key_cannot_decrypt_falls_back_with_a_warning(
    make_client: ClientFactory,
    admins: Settings,
    github: FakeIdentityProvider,
    caplog: pytest.LogCaptureFixture,
):
    first = await admin_client(make_client, admins, github, FakeServiceClients())
    assert (await first.put(CHAT_LLM, json=NEW)).status_code == 200

    caplog.set_level(logging.INFO)
    changed = replace(admins, secret_key="another-secret-key-" + "0" * 45)
    restarted = await admin_client(make_client, changed, github, FakeServiceClients(FakeLLM(REPLY)))
    await start(restarted)

    assert (await restarted.get(CONFIG)).json()["chat_llm"]["status"] == "failed"
    assert any(
        r.levelno == logging.WARNING and "chat_llm" in r.getMessage()
        and "EIDOLON_SECRET_KEY" in r.getMessage()
        for r in caplog.records
    )


async def test_no_one_but_admins_finds_the_configuration(
    make_client: ClientFactory, admins: Settings
):
    producer = make_client(FakeLLM(), settings=admins)
    nobody = make_client(FakeLLM(), user=None, settings=admins)

    for client in (producer, nobody):
        assert (await client.get(CONFIG)).status_code == 404
        assert (await client.put(CHAT_LLM, json=NEW)).status_code == 404
        assert (await client.delete(CHAT_LLM)).status_code == 404
