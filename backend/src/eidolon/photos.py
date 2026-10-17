"""The photos she sends with her replies (GLOSSARY.md「照片」): whether a turn could have one,
what she is told of it, and each photo from her tag to the picture kept with her reply.

A turn could have a photo where the deployer has image generation and she has her photo
tags (`characters`); only then is the judge model asked whether the user asks for one, and
only where it says so is she told she can send one, in the system message that changes from
turn to turn (ADR-0020), or, in the coldest tier of her affinity, that she does not want to.
A turn that could not have one is as it was before there were photos.

A photo begins as her tag closes (`begin`), generating while she goes on speaking; its id is
the browser's to wait on. It is kept with her reply as the reply is recorded (`recorded`),
being generated, and once generated its picture is, or why there is none; one generated
before the reply is recorded is kept as it is. A reply that is never recorded has its
photo dropped once generated (`dropped`), as does one whose conversation is deleted
meanwhile. Nothing stops a photo once begun, not the page closing: what it costs is spent.

The deployer's image service generates one photo at a time, and none takes longer than
`image_generation.TIME_LIMIT` from her tag on, waiting its turn included. Begun in a turn,
a photo is generated in the turn's context: its request to the image service is a service
call recorded under the turn (`activity`), however long after it the photo comes out.
"""

import asyncio
import logging
import uuid
from collections.abc import Callable
from contextlib import nullcontext
from dataclasses import dataclass

from eidolon.activity import ActivityLog, Recording, image_origin, recording, timed
from eidolon.affinity import TIERS, Tier
from eidolon.characters import Character
from eidolon.image_generation import TIME_LIMIT, ImageFailed, ImageGenerator
from eidolon.photo_prompt import image_prompt, read_tag
from eidolon.store import Store

log = logging.getLogger(__name__)

CAN_SEND = """\
# 照片
制作人在要你发一张照片。你可以发，也可以按你的性格和此刻的情境推掉（比如害羞、正在忙）。
要发的话，在回复的最前面、第一个 <ja> 之前写一个照片标签，一行一栏，格式如下：
<photo>
shot: selfie
framing: upper body
place: cafe, indoors, afternoon, sunlight
outfit: white shirt, cardigan
action: peace sign, smile
note: 在咖啡店给他拍的自拍
</photo>
- shot：selfie（自拍）或 other（别人帮你拍）。
- framing：portrait、upper body、cowboy shot、full body 选一个；自拍只能选 portrait 或 upper body。
- place：2–4 个英文 tag，写地点、室内还是室外、时段或天气、光线。
- outfit：1–4 个英文 tag，写一套衣服，只写这个景别里看得见的。
- action：2–4 个英文 tag，写一个动作、一两个表情；不看镜头时加一个视线。
- note：一句中文，写这是一张什么样的照片，只给你自己回看。
- place、outfit、action 合计不超过 12 个 tag。不写发色、瞳色、发型、身材，也不写画风或画师。
- 照着现在的时间和你们正在聊的事拍；他指定了地点或服装，在全年龄的范围内照办。
- 不拍裸露、内衣、透视、走光、洗澡，也不拍性感的姿势、表情和镜头；他要这些时，你可以推掉，也可以换成全年龄的样子再拍。
- 一次回复最多一张。标签后面照常用 <ja><zh> 说话。"""
"""What she is told in a turn the user asks for a photo in, and she can send one."""

NOT_NOW = """\
# 照片
制作人在要你发一张照片，你现在不想给。用你自己的话推掉，不要写照片标签。"""
"""What she is told in a turn the user asks for a photo in, her affinity in its coldest
tier: she does not send one."""

COLDEST: Tier = TIERS[0][0]


@dataclass(frozen=True)
class PhotoTurn:
    """What a turn the judge model says asks for a photo comes to: what she is told of it,
    and whether a photo tag she writes is kept."""

    prompt: str
    keeps_tag: bool


def photo_turn(asked: bool, tier: Tier | None) -> PhotoTurn | None:
    """What a turn that could have a photo comes to, the user having `asked` for one or not,
    her affinity in `tier` (None where affinity is off); None if not asked."""
    if not asked:
        return None
    if tier == COLDEST:
        return PhotoTurn(NOT_NOW, keeps_tag=False)
    return PhotoTurn(CAN_SEND, keeps_tag=True)


@dataclass
class _Generating:
    """A photo begun: whether its reply is recorded or never will be, and how it came out
    once it has (its picture, or why there is none)."""

    recorded: bool = False
    dropped: bool = False
    outcome: tuple[bytes | None, str | None] | None = None


class Photos:
    """Every photo she sends, from her tag to the picture kept with her reply."""

    def __init__(
        self,
        store: Store,
        generator: Callable[[], ImageGenerator | None],
        activity: ActivityLog,
    ) -> None:
        """`generator` says, whenever asked, the deployer's image generation in effect;
        None while there is none. Its requests are recorded in `activity`."""
        self._store = store
        self._generator = generator
        self._activity = activity
        self._one_at_a_time = asyncio.Semaphore(1)
        self._generating: dict[str, _Generating] = {}
        self._tasks: set[asyncio.Task[None]] = set()

    def could_send(self, character: Character) -> bool:
        """Whether a turn with her could have a photo: there is image generation, and she has
        her photo tags."""
        return character.photographed and self._generator() is not None

    def begin(self, character: Character, tag: str) -> str:
        """Begin the photo her `tag` says, generating, in the turn it is begun in; its id."""
        photo_id = uuid.uuid4().hex
        self._generating[photo_id] = _Generating()
        until = asyncio.get_running_loop().time() + TIME_LIMIT
        task = asyncio.create_task(
            self._generate(photo_id, character, tag, until, recording())
        )
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return photo_id

    def recorded(self, photo_id: str) -> None:
        """Her reply is recorded with the photo, being generated: it is kept as it comes out,
        or now, if it has."""
        generating = self._generating[photo_id]
        generating.recorded = True
        if generating.outcome is not None:
            self._keep(photo_id, *generating.outcome)

    def dropped(self, photo_id: str) -> None:
        """Her reply is never to be recorded: the photo is not kept, however it comes out."""
        generating = self._generating[photo_id]
        if generating.outcome is not None:
            del self._generating[photo_id]
        else:
            generating.dropped = True

    async def _generate(
        self,
        photo_id: str,
        character: Character,
        tag: str,
        until: float,
        turn: Recording | None,
    ) -> None:
        """Generate the photo by `until` (the running loop's time), its request recorded
        under `turn`."""
        outcome: tuple[bytes | None, str | None]
        try:
            async with asyncio.timeout_at(until):  # waiting its turn, not yet sent
                await self._one_at_a_time.acquire()
            try:
                generator = self._generator()
                if generator is None:
                    raise ImageFailed("service_error", "image generation is off")
                with turn.current() if turn is not None else nullcontext():
                    image = await timed(
                        self._activity,
                        image_origin(generator.settings),
                        generator.generate(image_prompt(character, read_tag(tag)), until),
                    )
            finally:
                self._one_at_a_time.release()
            outcome = image.webp, None
        except ImageFailed as e:
            log.warning("photo %s was not generated: %s", photo_id, e)
            outcome = None, e.reason
        except TimeoutError:
            log.warning("photo %s took longer than %ss", photo_id, TIME_LIMIT)
            outcome = None, "timeout"
        except Exception:  # never left being generated for good
            log.exception("generating photo %s failed", photo_id)
            outcome = None, "service_error"
        generating = self._generating[photo_id]
        if generating.dropped:
            del self._generating[photo_id]
        elif generating.recorded:
            self._keep(photo_id, *outcome)
        else:
            generating.outcome = outcome

    def _keep(self, photo_id: str, image: bytes | None, reason: str | None) -> None:
        del self._generating[photo_id]
        if not self._store.finish_photo(photo_id, image, reason):
            log.info("photo %s came out after its reply was deleted; not kept", photo_id)

    async def aclose(self) -> None:
        """Stop generating: the server is shutting down."""
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)
