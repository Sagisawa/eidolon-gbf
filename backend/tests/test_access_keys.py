"""Users and access keys: issued and revoked from the admin command line, checked on
every API request, and resolved to the user who owns the conversation record."""

import httpx
import pytest

from tests.conftest import Admin, ClientFactory, IssuedKey
from tests.fakes import FakeLLM
from tests.test_text_turn import send_turn, start_conversation

REPLY = ["<ja>はいっ</ja><zh>好的</zh>"]


async def mano_conversations(client: httpx.AsyncClient) -> list[str]:
    res = await client.get("/api/conversations", params={"character_id": "mano"})
    assert res.status_code == 200
    return [c["id"] for c in res.json()]


@pytest.mark.parametrize(
    "headers",
    [{}, {"Authorization": "Bearer esc_not-a-real-key"}, {"Authorization": "esc_no-scheme"}],
    ids=["missing", "invalid", "malformed"],
)
async def test_requests_without_a_valid_key_are_rejected_with_a_clear_reason(
    make_client: ClientFactory, headers: dict[str, str]
):
    client = make_client(FakeLLM(), key=None)
    client.headers.update(headers)

    for res in [
        await client.get("/api/conversations", params={"character_id": "mano"}),
        await client.post("/api/conversations", json={"character_id": "mano"}),
        await client.get("/api/conversations/any/messages"),
        await client.post("/api/conversations/any/turns", json={"text": "在吗"}),
    ]:
        assert res.status_code == 401
        assert "访问密钥" in res.json()["detail"]


async def test_health_check_needs_no_key(make_client: ClientFactory):
    res = await make_client(FakeLLM(), key=None).get("/api/health")
    assert res.status_code == 200


async def test_two_keys_of_one_user_share_the_same_conversation_record(
    make_client: ClientFactory, admin: Admin, producer_key: IssuedKey
):
    phone_key = admin.issue_key("producer")
    desktop = make_client(FakeLLM(REPLY))
    phone = make_client(FakeLLM(), key=phone_key.secret)

    conversation_id = await start_conversation(desktop)
    await send_turn(desktop, conversation_id, "在吗")

    assert await mano_conversations(phone) == [conversation_id]
    messages = (await phone.get(f"/api/conversations/{conversation_id}/messages")).json()
    assert [m["role"] for m in messages] == ["user", "character"]


async def test_revoked_key_is_refused_while_the_users_other_keys_keep_their_data(
    make_client: ClientFactory, admin: Admin, producer_key: IssuedKey
):
    spare = admin.issue_key("producer")
    client = make_client(FakeLLM(REPLY))
    conversation_id = await start_conversation(client)
    await send_turn(client, conversation_id, "在吗")

    admin.revoke_key(producer_key.id)

    res = await client.get("/api/conversations", params={"character_id": "mano"})
    assert res.status_code == 401
    assert "吊销" in res.json()["detail"]
    other = make_client(FakeLLM(), key=spare.secret)
    assert await mano_conversations(other) == [conversation_id]
    messages = (await other.get(f"/api/conversations/{conversation_id}/messages")).json()
    assert len(messages) == 2


async def test_users_cannot_see_or_use_each_others_conversations(
    make_client: ClientFactory, admin: Admin
):
    admin.create_user("friend")
    friend = make_client(FakeLLM(), key=admin.issue_key("friend").secret)
    mine = make_client(FakeLLM(REPLY))
    conversation_id = await start_conversation(mine)
    await send_turn(mine, conversation_id, "在吗")

    assert await mano_conversations(friend) == []
    res = await friend.get(f"/api/conversations/{conversation_id}/messages")
    assert res.status_code == 404
    res = await friend.post(f"/api/conversations/{conversation_id}/turns", json={"text": "hi"})
    assert res.status_code == 404


def test_admin_lists_keys_by_id_without_revealing_them(admin: Admin, producer_key: IssuedKey):
    spare = admin.issue_key("producer")
    admin.revoke_key(spare.id)

    listing = admin.run("key", "list", "producer")

    assert producer_key.id in listing and spare.id in listing
    assert producer_key.secret not in listing and spare.secret not in listing
    assert "已吊销" in listing


def test_admin_commands_refuse_unknown_users_keys_and_duplicate_names(
    admin: Admin, producer_key: IssuedKey
):
    assert "producer" in admin.fails("user", "create", "producer")
    assert "nobody" in admin.fails("key", "issue", "nobody")
    assert "nothing" in admin.fails("key", "revoke", "nothing")
