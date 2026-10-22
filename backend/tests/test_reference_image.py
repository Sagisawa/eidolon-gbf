"""Tests for reference image-to-image photo generation (GLOSSARY.md「照片」).

Verifies:
1. `reference_image_prompt` creates instructions preserving the reference image character
   features while specifying setting, outfit, action, and framing.
2. `ImageGenerator` in OpenAI format calls `/images/edits` with multipart form data when
   reference images are supplied.
3. `ImageGenerator` falls back to `/images/generations` if `/images/edits` returns 404/405.
4. When character background or avatar exists and OpenAI format is active, photos are
   generated via reference images.
"""

import io
from dataclasses import replace
from pathlib import Path

import httpx
import pytest
from PIL import Image

from eidolon.characters import Character
from eidolon.config import ImageSettings, Settings
from eidolon.image_generation import ImageGenerator, to_png_bytes
from eidolon.photo_prompt import PhotoTag, reference_image_prompt
from tests.conftest import ClientFactory
from tests.fakes import FAKE_JUDGE, FakeImageService, FakeLLM
from tests.test_photos import REPLY, asking, photo_events, settled
from tests.test_text_turn import send_turn, start_conversation

OPENAI_IMAGE = ImageSettings(
    api_key="sk-test",
    base_url="https://api.openai.test/v1",
    model="gpt-image-2.5-sunburst",
    api_format="openai",
)


def _make_png_bytes(width: int = 64, height: int = 64, color: tuple[int, int, int] = (255, 0, 0)) -> bytes:
    im = Image.new("RGB", (width, height), color)
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def _make_jpg_bytes(width: int = 64, height: int = 64) -> bytes:
    im = Image.new("RGB", (width, height), (0, 128, 255))
    buf = io.BytesIO()
    im.save(buf, format="JPEG")
    return buf.getvalue()


def test_to_png_bytes_converts_jpeg_to_png():
    jpg = _make_jpg_bytes(32, 32)
    png = to_png_bytes(jpg)
    with Image.open(io.BytesIO(png)) as im:
        assert im.format == "PNG"
        assert im.size == (32, 32)


def test_reference_image_prompt_contains_fidelity_instruction_and_tags():
    character = Character(
        id="narmaya",
        name="ナルメア",
        name_romaji="Narmaya",
        intro="swordmaster",
        voice_id="v1",
        sheet="",
        avatar=None,
        color="#8a5aa8",
        photo_tag="narmaya (granblue fantasy)",
        photo_appearance="draph, curved horns, purple hair",
    )
    tag = PhotoTag(
        shot="selfie",
        framing="upper body",
        place=("beach", "outdoors", "day"),
        outfit=("swimsuit",),
        action=("smile", "peace sign"),
    )
    prompt = reference_image_prompt(character, tag, style="anime")

    assert "Strictly preserve" in prompt.positive
    assert "Narmaya" in prompt.positive
    assert "selfie" in prompt.positive
    assert "upper body" in prompt.positive
    assert "beach, outdoors, day" in prompt.positive
    assert "swimsuit" in prompt.positive
    assert "smile, peace sign" in prompt.positive
    assert "narmaya (granblue fantasy)" in prompt.positive
    assert "granblue fantasy" in prompt.positive
    assert "anime" in prompt.positive


async def test_generator_calls_openai_edits_when_reference_images_provided():
    fake_service = FakeImageService()
    async with httpx.AsyncClient(transport=fake_service.transport()) as client:
        generator = ImageGenerator(OPENAI_IMAGE, client)
        prompt = reference_image_prompt(
            Character(
                id="test",
                name="Test",
                intro="",
                voice_id="v1",
                sheet="",
                avatar=None,
                color="#000000",
                photo_tag="test_tag",
                photo_appearance="test_look",
            ),
            PhotoTag(
                shot="other",
                framing="upper body",
                place=("cafe",),
                outfit=("apron",),
                action=("smile",),
            ),
        )

        ref1 = _make_png_bytes()
        ref2 = _make_jpg_bytes()

        result = await generator.generate(
            prompt,
            until=9999999999.0,
            reference_images=(ref1, ref2),
        )

        assert len(fake_service.requests) == 1
        req = fake_service.requests[0]
        assert req["url"].endswith("/images/edits")
        assert req["key"] == "sk-test"
        assert req["body"]["model"] == "gpt-image-2.5-sunburst"
        assert len(result.webp) > 0


async def test_generator_fallback_to_generations_when_edits_returns_404():
    fake_service = FakeImageService()
    valid_png = _make_png_bytes(832, 1216)

    def custom_handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/images/edits"):
            return httpx.Response(404, json={"error": "Not Found"})
        if request.url.path.endswith("/images/generations"):
            return fake_service._openai(valid_png)

        raise AssertionError(f"unexpected request {request.url}")
    mock_transport = httpx.MockTransport(custom_handler)
    async with httpx.AsyncClient(transport=mock_transport) as client:
        generator = ImageGenerator(OPENAI_IMAGE, client)
        prompt = reference_image_prompt(
            Character(
                id="test",
                name="Test",
                intro="",
                voice_id="v1",
                sheet="",
                avatar=None,
                color="#000000",
                photo_tag="test_tag",
                photo_appearance="test_look",
            ),
            PhotoTag(
                shot="selfie",
                framing="portrait",
                place=("room",),
                outfit=("t-shirt",),
                action=("wink",),
            ),
        )

        # Generating with reference image should fallback gracefully to /images/generations
        result = await generator.generate(
            prompt,
            until=9999999999.0,
            reference_images=(_make_png_bytes(),),
        )
        assert len(result.webp) > 0


async def test_photos_sends_reference_image_in_openai_format(
    make_client: ClientFactory, settings: Settings
):
    image = FakeImageService()
    openai_settings = replace(
        settings,
        image=OPENAI_IMAGE,
        judge=FAKE_JUDGE,
        affinity_and_gifts=False,
    )
    llm = FakeLLM(REPLY)
    client = make_client(
        llm,
        settings=openai_settings,
        clients=asking(),
        image_transport=image.transport(),
    )
    conversation = await start_conversation(client)

    events = await send_turn(client, conversation, "发张自拍给我看看")
    [photo] = photo_events(events)
    ready = await settled(client, photo["id"])
    assert ready["status"] == "ready"

    # Because Mano has avatar & background files in conftest, /images/edits should have been called!
    assert len(image.requests) == 1
    assert image.requests[0]["url"].endswith("/images/edits")
    assert "Strictly preserve" in image.requests[0]["body"]["prompt"]
