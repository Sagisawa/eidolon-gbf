"""The ShinyColorsDB mirror of the game's decoded scripts, and its API (ADR-0004).

The API (`api.shinycolors.moe`) lists every idol and her cards, and each card's
episodes with the game script they are in and their title; the viewer
(`viewer.shinycolors.moe`) serves the scripts themselves, as the game does. Neither
publishes terms or a rate limit and both are run by volunteers, so requests go out
one at a time, about a second apart, and a script already downloaded is only asked
for again conditionally, on its ETag.
"""

import asyncio
import os
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import httpx

API_URL = "https://api.shinycolors.moe"
VIEWER_URL = "https://viewer.shinycolors.moe/json"
DEFAULT_INTERVAL = 1.0
"""Seconds between requests."""
_USER_AGENT = "eidolon-sc story sync (weekly, one request a second)"


class MirrorError(RuntimeError):
    """The API or the viewer could not be reached, or answered with something unexpected."""


@dataclass(frozen=True)
class Card:
    uuid: str
    name: str
    """As the game names it, 【card name】idol name, which is also how SCTranslationData
    names the card's directory."""
    type: str
    """`P_SSR`, `S_SR` and so on: a produce (P) or support (S) card."""
    version: str
    """Changes whenever the card's data does."""


@dataclass(frozen=True)
class CardEpisode:
    script: str
    """The game script, e.g. `produce_events/200100401`."""
    title: str


Fetched = Literal["downloaded", "unchanged", "missing"]


class Mirror:
    def __init__(
        self,
        client: httpx.AsyncClient | None = None,
        *,
        interval: float = DEFAULT_INTERVAL,
    ) -> None:
        self._client = client or httpx.AsyncClient(
            timeout=httpx.Timeout(60, connect=10), headers={"User-Agent": _USER_AGENT}
        )
        self._interval = interval
        self._last_request: float | None = None

    async def idols(self) -> list[int]:
        idols = await self._api("/info/idolList")
        with _unexpected("/info/idolList"):
            return [int(idol["idolId"]) for idol in idols]

    async def cards(self, idol_id: int) -> list[Card]:
        info = await self._api("/info/idolInfo", idolId=idol_id)
        with _unexpected("/info/idolInfo"):
            return [
                Card(
                    uuid=card["cardUuid"],
                    name=card["cardName"],
                    type=card["cardType"],
                    version=f"{card.get('cardHash')}/{card.get('lastModified')}",
                )
                for card in info.get("cardLists") or []
            ]

    async def episodes(self, card: Card) -> list[CardEpisode]:
        """The card's episodes, in the order the game numbers them. Some cards have none."""
        if card.type.startswith("P_"):
            path, events, title = "/info/pCardInfo", "cardIdolEvents", "eventTitle"
        elif card.type.startswith("S_"):
            path, events, title = "/info/sCardInfo", "cardSupportEvents", "eventName"
        else:
            return []
        info = await self._api(path, cardId=card.uuid)
        with _unexpected(path):
            return sorted(
                (
                    CardEpisode(f"produce_events/{event['eventId']}", event.get(title) or "")
                    for event in info.get(events) or []
                    if event.get("eventId")
                ),
                key=lambda episode: episode.script,
            )

    async def download(self, script: str, target: Path, etag: str | None) -> tuple[Fetched, str | None]:
        """Save the script to `target` unless the mirror says the copy matching `etag` is
        still current; returns what happened and the ETag of the copy now at `target`.
        A script the mirror does not have is `missing`, not an error."""
        headers = {"If-None-Match": etag} if etag else {}
        response = await self._get(f"{VIEWER_URL}/{script}.json", headers=headers)
        if response.status_code == 304:
            return "unchanged", etag
        if response.status_code == 404:
            return "missing", None
        _check(response)
        try:
            frames = response.json()
        except ValueError as e:
            raise MirrorError(f"{script}：镜像返回的不是 JSON（{e}）") from e
        if not isinstance(frames, list):
            raise MirrorError(f"{script}：镜像返回的不是剧本的帧数组")
        target.parent.mkdir(parents=True, exist_ok=True)
        partial = target.with_name(target.name + ".part")
        partial.write_bytes(response.content)
        os.replace(partial, target)  # never a half-written script, even if interrupted
        return "downloaded", response.headers.get("ETag")

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _api(self, path: str, **params: Any) -> Any:
        response = await self._get(API_URL + path, params=params)
        _check(response)
        try:
            return response.json()
        except ValueError as e:
            raise MirrorError(f"{path}：API 返回的不是 JSON（{e}）") from e

    async def _get(self, url: str, **kwargs: Any) -> httpx.Response:
        if self._last_request is not None:
            wait = self._last_request + self._interval - time.monotonic()
            if wait > 0:
                await asyncio.sleep(wait)
        try:
            return await self._client.get(url, **kwargs)
        except httpx.HTTPError as e:
            raise MirrorError(f"无法连接 {url}：{e!r}") from e
        finally:
            self._last_request = time.monotonic()


@contextmanager
def _unexpected(path: str) -> Iterator[None]:
    """An API answer shaped unlike what it used to be is the mirror's error, too."""
    try:
        yield
    except (KeyError, TypeError, ValueError, AttributeError) as e:
        raise MirrorError(f"{path}：API 返回的数据结构和预期不同（{e!r}）") from e


def _check(response: httpx.Response) -> None:
    if response.status_code != 200:
        raise MirrorError(f"{response.request.url} 返回 HTTP {response.status_code}")
