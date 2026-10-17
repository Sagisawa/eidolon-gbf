"""Image generation (GLOSSARY.md「生图」): one picture from a prompt, checked and made into what
a photo is kept as.

The deployer's is reached in NovelAI's own format: `POST {base_url}/ai/generate-image` with a
bearer token, answering with a ZIP of the picture, at NovelAI or a relay passing requests on
as they are. Every request asks for one picture of 832×1216 at 23 steps, scale 7 with Euler
Ancestral, from a random seed, in the shape of V4's prompts and later; none of it is anyone's
to set. What comes back is checked: a ZIP holding exactly one picture, 832×1216. It is kept
as WebP, its size as it is, every bit of metadata dropped, the prompt the PNG carries among
it. Only the server calls the service; browsers never do.
"""

import io
import random
import zipfile
from dataclasses import dataclass
from typing import Literal

import httpx
from PIL import Image, UnidentifiedImageError

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
        self._settings = settings
        self._client = client

    async def generate(self, prompt: ImagePrompt) -> GeneratedImage:
        """One picture for `prompt`, as kept. Raises ImageFailed saying why there is none."""
        body = generation_request(
            self._settings.model, prompt, random.SystemRandom().randint(0, MAX_SEED)
        )
        try:
            res = await self._client.post(
                f"{self._settings.base_url}/ai/generate-image",
                json=body,
                headers={"Authorization": f"Bearer {self._settings.api_key}"},
            )
        except httpx.TimeoutException as e:
            raise ImageFailed("timeout", repr(e)) from None
        except httpx.HTTPError as e:
            raise ImageFailed("service_error", repr(e)) from None
        if res.status_code >= 400:
            raise ImageFailed("service_error", f"HTTP {res.status_code}: {res.text[:300]}")
        return GeneratedImage(kept_as_webp(only_picture(res.content)))

    async def aclose(self) -> None:
        await self._client.aclose()


def only_picture(archive: bytes) -> bytes:
    """The one file in the ZIP `archive`. Raises ImageFailed if it is not a ZIP of one."""
    try:
        with zipfile.ZipFile(io.BytesIO(archive)) as zipped:
            names = [n for n in zipped.namelist() if not n.endswith("/")]
            if len(names) != 1:
                raise ImageFailed("bad_image", f"the ZIP holds {len(names)} files")
            return zipped.read(names[0])
    except (zipfile.BadZipFile, OSError) as e:
        raise ImageFailed("bad_image", f"not a ZIP: {e}") from None


def kept_as_webp(picture: bytes) -> bytes:
    """`picture` as a photo is kept: WebP, nothing but its pixels. Raises ImageFailed unless
    it is a picture of `WIDTH`×`HEIGHT`."""
    try:
        with Image.open(io.BytesIO(picture)) as opened:
            opened.load()
            size = opened.size
            if size != (WIDTH, HEIGHT):
                raise ImageFailed("bad_image", f"{size[0]}×{size[1]}, not {WIDTH}×{HEIGHT}")
            # Made anew from its pixels alone, so nothing of what came with it is written.
            pixels = opened.convert("RGB")
            bare = Image.frombytes("RGB", size, pixels.tobytes())
    except (UnidentifiedImageError, OSError, ValueError) as e:
        raise ImageFailed("bad_image", f"not a picture: {e}") from None
    out = io.BytesIO()
    bare.save(out, "WEBP", quality=WEBP_QUALITY)
    return out.getvalue()
