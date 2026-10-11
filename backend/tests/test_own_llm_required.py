"""Own LLM required (GLOSSARY.md「必须自带 LLM」): the deployer may require users to bring
their own LLM. `.env` sets whether it does (`EIDOLON_OWN_LLM_REQUIRED`), the admin console
may override it beside the limits, and it holds from the next turn on. Then a text turn
that brings no LLM of the user's own is refused, 403 saying why; it is recorded rejected
and counts towards nothing. One that brings one goes on, and counts towards nothing as
ever; admins are not bound by it, and their turns count as ever. Driven through the
backend's external API."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from dataclasses import replace

import httpx
import pytest

from eidolon.config import Settings, UsageLimits
from tests.conftest import SITE, ClientFactory, agree_to_terms, github_identity, sign_in_with
from tests.fakes import FakeClock, FakeIdentityProvider, FakeLLM, FakeLLMService
from tests.test_activity_records import dashboard
from tests.test_admin_users import ADMIN
from tests.test_own_llm import LLM
from tests.test_rate_limit import REPLY, post_turn
from tests.test_text_turn import send_turn, start_conversation

CONFIG = "/api/admin/config"
LIMITS = f"{CONFIG}/limits"
ENV_LIMITS = {
    "turns_per_hour": 1, "calls_per_hour": 5, "call_minutes": 10, "turns_per_call": 40,
    "history_turns": 20,
}
"""The limits as `.env` has them in these tests, but for whether an own LLM is required."""
DETAIL = "这个部署需要你自带 LLM，可以在设置里填写"


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """With an admin, a turn an hour, and users' own LLM required."""
    return replace(
        settings,
        admins=frozenset({ADMIN}),
        usage_limits=UsageLimits(turns_per_hour=1),
        own_llm_required=True,
    )


@asynccontextmanager
async def admin_beside(
    client: httpx.AsyncClient, github: FakeIdentityProvider
) -> AsyncIterator[httpx.AsyncClient]:
    """The admin, signed in in another browser on the backend `client` is on, so that what
    they change in the admin console holds for its next turn."""
    transport = client._transport
    async with httpx.AsyncClient(
        transport=transport, base_url="http://test", headers=SITE
    ) as admin:
        await sign_in_with(admin, github, github_identity(ADMIN[1], name="boss"))
        await agree_to_terms(admin)
        yield admin


async def require(admin: httpx.AsyncClient, required: object) -> httpx.Response:
    """Have the admin require users' own LLM, or not, in the admin console."""
    return await admin.put(LIMITS, json=ENV_LIMITS | {"own_llm_required": required})


async def test_a_turn_without_an_own_llm_is_refused_saying_why_recorded_rejected_and_not_counted(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    deployers = FakeLLM(REPLY, REPLY)
    producer = make_client(deployers, clock=FakeClock())
    conversation_id = await start_conversation(producer)

    async with admin_beside(producer, github) as admin:
        refused = await post_turn(producer, conversation_id)
        board = await dashboard(admin)
        assert (await require(admin, False)).status_code == 200
        # Had the refused turn counted, the hour's one turn would be used up.
        allowed = await send_turn(producer, conversation_id, "在吗")
        over = await post_turn(producer, conversation_id)

    assert refused.status_code == 403
    assert refused.json() == {"detail": DETAIL, "own_llm_required": True}
    assert board["turns"]["by_result"] == {"success": 0, "failed": 0, "rejected": 1, "left": 0}
    assert allowed[-1]["type"] == "done"
    assert len(deployers.prompts) == 1  # only the turn let through reached the model
    assert over.status_code == 429


async def test_a_turn_bringing_an_own_llm_goes_on_and_does_not_count(
    make_client: ClientFactory, own_llm: FakeLLMService
):
    own_llm.llm = FakeLLM(REPLY, REPLY)
    deployers = FakeLLM()
    producer = make_client(deployers, clock=FakeClock())
    conversation_id = await start_conversation(producer)

    # One turn an hour, but turns on the user's own LLM count towards nothing.
    for said in ("早上好", "在吗"):
        events = await send_turn(producer, conversation_id, said, own_llm=LLM)
        assert events[-1]["type"] == "done", said
    assert deployers.prompts == []


async def test_an_admin_without_an_own_llm_goes_on_and_counts(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    deployers = FakeLLM(REPLY)
    producer = make_client(deployers, clock=FakeClock())

    async with admin_beside(producer, github) as admin:
        conversation_id = await start_conversation(admin)
        allowed = await send_turn(admin, conversation_id, "早上好")
        over = await post_turn(admin, conversation_id)

    assert allowed[-1]["type"] == "done"
    assert len(deployers.prompts) == 1
    assert over.status_code == 429


async def test_off_turns_without_an_own_llm_go_on_and_count_as_before(
    make_client: ClientFactory, settings: Settings
):
    deployers = FakeLLM(REPLY)
    producer = make_client(
        deployers, settings=replace(settings, own_llm_required=False), clock=FakeClock()
    )
    conversation_id = await start_conversation(producer)

    allowed = await send_turn(producer, conversation_id, "早上好")
    over = await post_turn(producer, conversation_id)

    assert allowed[-1]["type"] == "done"
    assert over.status_code == 429
    assert "每小时 1 次" in over.json()["detail"]


async def test_the_admin_console_shows_and_overrides_envs_from_the_next_turn_on(
    make_client: ClientFactory, settings: Settings, github: FakeIdentityProvider
):
    producer = make_client(
        FakeLLM(REPLY),
        settings=replace(settings, own_llm_required=False),
        clock=FakeClock(),
    )
    conversation_id = await start_conversation(producer)

    async with admin_beside(producer, github) as admin:
        before = (await admin.get(CONFIG)).json()["limits"]
        saved = await require(admin, True)
        refused = await post_turn(producer, conversation_id)
        restored = await admin.delete(LIMITS)
        allowed = await send_turn(producer, conversation_id, "在吗")

    env = ENV_LIMITS | {"own_llm_required": False}
    assert before == {
        "status": "env", "env": env, "effective": env, "override": None, "failure": None
    }
    assert saved.status_code == 200, saved.text
    assert saved.json()["limits"]["status"] == "overridden"
    assert saved.json()["limits"]["override"] == {"own_llm_required": True}
    assert saved.json()["limits"]["effective"] == env | {"own_llm_required": True}
    assert refused.status_code == 403
    assert refused.json()["detail"] == DETAIL
    assert restored.json()["limits"] == before
    assert allowed[-1]["type"] == "done"


async def test_the_admin_console_refuses_anything_but_true_or_false_saying_why(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    producer = make_client(FakeLLM())

    async with admin_beside(producer, github) as admin:
        refusals = [await require(admin, bad) for bad in (1, "yes", None)]
        after = (await admin.get(CONFIG)).json()["limits"]

    for res in refusals:
        assert res.status_code == 422
        assert "必须自带 LLM" in res.json()["detail"]
    assert after["status"] == "env"


def test_env_turns_it_on_with_1_and_refuses_anything_but_0_or_1(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setenv("CHAT_LLM_BASE_URL", "https://llm.example.com/v1")
    monkeypatch.setenv("CHAT_LLM_API_KEY", "sk-deployer")
    monkeypatch.setenv("CHAT_LLM_MODEL", "deployer-model")
    seen = {}
    for value in ("", "0", "1"):
        monkeypatch.setenv("EIDOLON_OWN_LLM_REQUIRED", value)
        seen[value] = Settings.from_env().own_llm_required
    monkeypatch.delenv("EIDOLON_OWN_LLM_REQUIRED")
    seen[None] = Settings.from_env().own_llm_required

    assert seen == {"": False, "0": False, "1": True, None: False}
    monkeypatch.setenv("EIDOLON_OWN_LLM_REQUIRED", "true")
    with pytest.raises(RuntimeError, match="EIDOLON_OWN_LLM_REQUIRED.*0 或 1"):
        Settings.from_env()


async def test_the_account_says_the_user_must_bring_their_own_llm_now(make_client: ClientFactory):
    # 字段就是拒绝用的那条规则，它的各个分支由回合的测试守着；
    # 要求关闭时为 False 由 test_sign_in.py 守着。这里只看它接上了。
    res = await make_client(FakeLLM()).get("/api/account")

    assert res.status_code == 200, res.text
    assert res.json()["own_llm_required"] is True
