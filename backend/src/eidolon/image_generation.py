"""Image generation (GLOSSARY.md「生图」): one picture from a prompt, checked and made into what
a photo is kept as.

The deployer's is reached in NovelAI's own format: `POST {base_url}/ai/generate-image` with a
bearer token, answering with a ZIP of the picture, at NovelAI or a relay passing requests on
as they are. Every request asks for one picture of 832×1216 at 23 steps, scale 7 with Euler
Ancestral, from a random seed, in the shape of V4's prompts and later; none of it is anyone's
to set. What comes back is checked: a ZIP holding exactly one picture, 832×1216. It is kept
as WebP, its size as it is, every bit of metadata dropped, the prompt the PNG carries among
it. Only the server calls the service; browsers never do.

A request is billed in pictures (`billing`): one where the service answered with a picture,
of the size asked for or not, none where it answered with an error, or not in time.
"""

import asyncio
import io
import random
import zipfile
from dataclasses import dataclass
from typing import Literal

import httpx
from PIL import Image, UnidentifiedImageError

from eidolon.billing import bill
from eidolon.config import ImageSettings
from eidolon.photo_prompt import ImagePrompt

WIDTH, HEIGHT = 832, 1216
STEPS = 23
SCALE = 7
SAMPLER = "k_euler_ancestral"
WEBP_QUALITY = 85
MAX_SEED = 4294967295 - 7
"""The largest seed NovelAI takes."""

TIME_LIMIT = 90
"""The longest a photo may take in all, in seconds, waiting its turn included."""
GENERATION_TIMEOUT = httpx.Timeout(TIME_LIMIT, connect=10)

Failure = Literal["timeout", "service_error", "bad_image"]
"""Why a picture could not be had: the service took too long, answered with an error or
could not be reached, or answered with what is not one picture of the size asked for."""


class ImageFailed(Exception):
    def __init__(self, reason: Failure, detail: str) -> None:
        super().__init__(f"{reason}: {detail}")
        self.reason: Failure = reason


def _bad_image(why: str) -> ImageFailed:
    """The service answered with what is not one picture of the size asked for: what is
    recorded as an answer that could not be read (`activity.error_kind`)."""
    return ImageFailed("bad_image", f"生图服务的返回无法解析（{why}）")


@dataclass(frozen=True)
class GeneratedImage:
    webp: bytes


def generation_request(model: str, prompt: ImagePrompt, seed: int) -> dict:
    """The body NovelAI's `/ai/generate-image` is sent for `prompt` with `model`."""
    return {
        "input": prompt.positive,
        "model": model,
        "action": "generate",
        "parameters": {
            "params_version": 3,
            "width": WIDTH,
            "height": HEIGHT,
            "scale": SCALE,
            "sampler": SAMPLER,
            "steps": STEPS,
            "n_samples": 1,
            "ucPreset": 3,  # none: the negative prompt is written out in full
            "qualityToggle": False,  # the quality tags are written out too
            "seed": seed,
            "noise_schedule": "karras",
            "cfg_rescale": 0,
            "negative_prompt": prompt.negative,
            "v4_prompt": {
                "caption": {"base_caption": prompt.positive, "char_captions": []},
                "use_coords": False,
                "use_order": True,
            },
            "v4_negative_prompt": {
                "caption": {"base_caption": prompt.negative, "char_captions": []},
                "legacy_uc": False,
            },
        },
    }


class ImageGenerator:
    """Generates pictures at the image service `settings` name, over `client`."""

    def __init__(self, settings: ImageSettings, client: httpx.AsyncClient) -> None:
        self.settings = settings
        self._client = client

    async def generate(self, prompt: ImagePrompt, until: float) -> GeneratedImage:
        """One picture for `prompt`, as kept, had by `until` (the running loop's time) at
        the latest. Raises ImageFailed saying why there is none. Tells what it is billed
        for (`billing`): one picture once the service answered with any, none before."""
        body = generation_request(
            self.settings.model, prompt, random.SystemRandom().randint(0, MAX_SEED)
        )
        bill("images", 0)
        try:
            async with asyncio.timeout_at(until):
                res = await self._client.post(
                    f"{self.settings.base_url}/ai/generate-image",
                    json=body,
                    headers={"Authorization": f"Bearer {self.settings.api_key}"},
                )
        except (TimeoutError, httpx.TimeoutException) as e:
            raise ImageFailed("timeout", f"生图服务没有及时回应：{e!r}") from e
        except httpx.HTTPError as e:
            raise ImageFailed("service_error", f"无法连接生图服务：{e!r}") from e
        if res.status_code >= 400:
            raise ImageFailed(
                "service_error", f"生图服务返回 {res.status_code}: {res.text[:300]}"
            )
        pictures = files_in(res.content)
        if pictures:
            bill("images", 1)
        if len(pictures) != 1:
            raise _bad_image(f"ZIP 里有 {len(pictures)} 个文件")
        return GeneratedImage(kept_as_webp(pictures[0]))

    async def aclose(self) -> None:
        await self._client.aclose()


def files_in(archive: bytes) -> list[bytes]:
    """The files in the ZIP `archive`. Raises ImageFailed if it is not a ZIP."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            return [zipped.read(n) for n in zipped.namelist() if not n.endswith("/")]
    except (zipfile.BadZipFile, OSError) as e:
        raise _bad_image(f"不是 ZIP：{e}") from None


def kept_as_webp(picture: bytes) -> bytes:
    """`picture` as a photo is kept: WebP, nothing but its pixels. Raises ImageFailed unless
    it is a picture of `WIDTH`×`HEIGHT`."""
    try:
        with Image.open(io.BytesIO(picture)) as opened:
            opened.load()
            size = opened.size
            if size != (WIDTH, HEIGHT):
                raise _bad_image(f"{size[0]}×{size[1]}，不是 {WIDTH}×{HEIGHT}")
            # Made anew from its pixels alone, so nothing of what came with it is written.
            pixels = opened.convert("RGB")
            bare = Image.frombytes("RGB", size, pixels.tobytes())
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise _bad_image(f"不是图片：{e}") from None
    out = io.BytesIO()
    bare.save(out, "WEBP", quality=WEBP_QUALITY)
    return out.getvalue()
