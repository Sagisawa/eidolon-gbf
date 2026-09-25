"""Voice calls: signalling and ICE configuration, driven through the backend's external API."""

from collections.abc import AsyncIterator
from dataclasses import replace

import httpx
import pytest
from aiortc import RTCConfiguration, RTCPeerConnection

from eidolon.config import Settings
from tests.conftest import Admin, ClientFactory
from tests.fakes import FakeCalls, FakeLLM
from tests.test_text_turn import start_conversation


@pytest.fixture
async def browser() -> AsyncIterator[RTCPeerConnection]:
    """The browser's side of the call: sends the microphone and a data channel."""
    pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))  # host candidates only
    pc.addTransceiver("audio", direction="sendrecv")
    pc.createDataChannel("chat")
    yield pc
    await pc.close()


async def offer_body(pc: RTCPeerConnection, **request_data) -> dict:
    """The offer as the Pipecat client posts it, with our own request data."""
    await pc.setLocalDescription(await pc.createOffer())
    return {
        "sdp": pc.localDescription.sdp,
        "type": pc.localDescription.type,
        "pc_id": None,
        "restart_pc": False,
        "requestData": request_data,
    }


async def call(
    client: httpx.AsyncClient, pc: RTCPeerConnection, **request_data
) -> httpx.Response:
    return await client.post("/api/offer", json=await offer_body(pc, **request_data))


async def test_ice_servers_come_from_configuration(make_client: ClientFactory, settings: Settings):
    turn = {"urls": ["turn:turn.example.com:3478"], "username": "u", "credential": "p"}
    settings = replace(settings, ice_servers=[{"urls": ["stun:stun.example.com"]}, turn])
    client = make_client(FakeLLM(), settings=settings)

    res = await client.get("/api/ice-servers")

    assert res.status_code == 200
    assert res.json() == {"iceServers": [{"urls": ["stun:stun.example.com"]}, turn]}


async def test_ice_servers_need_an_access_key(make_client: ClientFactory):
    client = make_client(FakeLLM(), key=None)

    assert (await client.get("/api/ice-servers")).status_code == 401


async def test_call_is_answered_and_joins_the_conversation(
    make_client: ClientFactory, calls: FakeCalls, browser: RTCPeerConnection
):
    client = make_client(FakeLLM())
    conversation_id = await start_conversation(client, "kogane")

    res = await call(client, browser, conversation_id=conversation_id, muted=True)

    assert res.status_code == 200
    answer = res.json()
    assert answer["type"] == "answer" and answer["sdp"].startswith("v=0")
    assert answer["pc_id"]
    [started] = calls.started
    assert started.conversation.id == conversation_id
    assert started.character.id == "kogane"
    assert started.muted is True


async def test_call_needs_an_access_key(
    make_client: ClientFactory, calls: FakeCalls, browser: RTCPeerConnection
):
    client = make_client(FakeLLM())
    conversation_id = await start_conversation(client)
    client.headers.pop("Authorization")

    res = await call(client, browser, conversation_id=conversation_id)

    assert res.status_code == 401
    assert calls.started == []


async def test_call_into_someone_elses_or_a_missing_conversation_is_refused(
    make_client: ClientFactory, admin: Admin, calls: FakeCalls, browser: RTCPeerConnection
):
    admin.create_user("stranger")
    theirs = await start_conversation(make_client(FakeLLM(), admin.issue_key("stranger").secret))
    client = make_client(FakeLLM())

    assert (await call(client, browser, conversation_id=theirs)).status_code == 404
    assert (await call(client, browser, conversation_id="missing")).status_code == 404
    assert (await call(client, browser)).status_code == 422
    assert calls.started == []


async def test_call_into_a_character_removed_from_the_configuration_is_refused(
    make_client: ClientFactory, settings: Settings, calls: FakeCalls, browser: RTCPeerConnection
):
    conversation_id = await start_conversation(make_client(FakeLLM()), "kogane")
    settings.characters_path.write_text(
        settings.characters_path.read_text(encoding="utf-8").split("\n\n[[characters]]")[0],
        encoding="utf-8",
    )
    client = make_client(FakeLLM())

    res = await call(client, browser, conversation_id=conversation_id)

    assert res.status_code == 404
    assert res.json()["detail"] == "角色不存在"
    assert calls.started == []


async def test_ice_candidates_are_only_accepted_for_your_own_call(
    make_client: ClientFactory, admin: Admin, browser: RTCPeerConnection
):
    client = make_client(FakeLLM())
    conversation_id = await start_conversation(client)
    pc_id = (await call(client, browser, conversation_id=conversation_id)).json()["pc_id"]
    end_of_candidates = {
        "pc_id": pc_id,
        "candidates": [{"candidate": "", "sdp_mid": "0", "sdp_mline_index": 0}],
    }
    assert (await client.patch("/api/offer", json=end_of_candidates)).status_code == 200

    admin.create_user("stranger")
    client.headers["Authorization"] = f"Bearer {admin.issue_key('stranger').secret}"

    assert (await client.patch("/api/offer", json=end_of_candidates)).status_code == 404


async def test_call_is_unavailable_until_voice_services_are_configured(
    make_client: ClientFactory, browser: RTCPeerConnection
):
    client = make_client(FakeLLM(), voice=False)
    conversation_id = await start_conversation(client)

    for res in [
        await client.get("/api/ice-servers"),  # the browser asks for these before calling
        await call(client, browser, conversation_id=conversation_id),
    ]:
        assert res.status_code == 503
        assert "语音" in res.json()["detail"]
