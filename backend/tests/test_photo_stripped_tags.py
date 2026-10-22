"""What she writes in her photo tag is hers (ADR-0026): no rating is put in for her, nothing
sexual is stripped, and the negative prompt is only the quality preset. What is never hers
to write is stripped, tag by tag, and the photo generated from the rest, a field stripped
bare taking its default: her looks, an art style or an artist, and anyone else in the
picture. The dashboard says how often, and for which part of the line, tags were stripped
from her photos; never which tags.

Driven through the backend's external API, the image service faked at its transport,
where every request it is sent is seen."""

from dataclasses import replace

import pytest

from eidolon.config import Settings
from tests.conftest import ClientFactory
from tests.fakes import FAKE_JUDGE, FakeClock, FakeIdentityProvider, FakeImageService, FakeLLM
from tests.test_activity_records import admin_client, dashboard, health
from tests.test_photos import IMAGE, WORDS, asking, photo_events, settled
from tests.test_text_turn import send_turn, start_conversation

HEAD = "1girl, solo, sakuragi mano, granblue fantasy, brown hair, medium hair, brown eyes"
TAIL = "very aesthetic, masterpiece, no text"
NEGATIVE = (
    "lowres, artistic error, film grain, scan artifacts, worst quality, bad quality,"
    " jpeg artifacts, very displeasing, chromatic aberration, dithering, halftone,"
    " screentone, multiple views, logo, too many watermarks, negative space, blank page,"
    " @_@, mismatched pupils, glowing eyes, bad anatomy"
)

BOLD = """
shot: other
framing: full body
place: bathroom, onsen, beach, poolside
outfit: nude, lingerie, micro bikini, school swimsuit
action: ahegao, spread legs, rating:explicit, smile
"""
NOT_HERS = """
shot: selfie
framing: upper body
place: indoors
outfit: blonde hair, 1boy
action: twintails, artist:someone, smile
"""


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """With the deployer's image generation and the judge model, affinity off; the GitHub
    user 1001 is an admin."""
    return replace(
        settings, image=IMAGE, judge=FAKE_JUDGE, affinity_and_gifts=False,
        admins=frozenset({("github", "1001")}),
    )


async def test_nothing_sexual_is_stripped_and_no_rating_is_put_in_for_her(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    clock = FakeClock()
    image = FakeImageService()
    client = make_client(
        FakeLLM([f"<photo>{BOLD}</photo>{WORDS}"]),
        clients=asking(),
        clock=clock,
        image_transport=image.transport(),
    )
    conversation = await start_conversation(client)

    [photo] = photo_events(await send_turn(client, conversation, "发张照片"))
    assert (await settled(client, photo["id"]))["status"] == "ready"

    [request] = image.requests
    assert request["body"]["input"] == (
        f"{HEAD}, full body, bathroom, onsen, beach, poolside, nude, lingerie, micro bikini,"
        f" school swimsuit, ahegao, spread legs, rating:explicit, smile, looking at viewer,"
        f" {TAIL}"
    )
    assert request["body"]["parameters"]["negative_prompt"] == NEGATIVE
    assert "rating:general" not in request["body"]["input"]


async def test_what_is_never_hers_to_write_is_stripped_and_counted_never_named(
    make_client: ClientFactory, github: FakeIdentityProvider
):
    clock = FakeClock()
    image = FakeImageService()
    client = make_client(
        FakeLLM([f"<photo>{NOT_HERS}</photo>{WORDS}"]),
        clients=asking(),
        clock=clock,
        image_transport=image.transport(),
    )
    admin = await admin_client(make_client, github, clock)
    conversation = await start_conversation(client)

    [photo] = photo_events(await send_turn(client, conversation, "发张照片"))
    assert (await settled(client, photo["id"]))["status"] == "ready"
    board = await dashboard(admin)

    [request] = image.requests
    assert request["body"]["input"] == (
        f"{HEAD}, selfie, looking at viewer, upper body, indoors, casual, smile, {TAIL}"
    )
    image_row = health(board, "image")
    assert image_row is not None
    assert image_row["stripped_photos"] == 1
    assert image_row["stripped"] == {"appearance": 2, "style": 1, "people": 1}
    for written in ("blonde", "twintails", "someone", "1boy"):
        assert written not in str(board), written
