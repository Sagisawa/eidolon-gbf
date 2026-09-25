"""Drafting a character sheet from the story corpus with the background model.

Only the episodes the character is cast in are material. When they fit in one request
the background model reads them all and writes the draft; when they do not, it first
takes notes on them batch by batch (and on its notes, until they fit), and writes the
draft from the notes. If even that would take too many requests, episodes are sampled
evenly across the corpus first.

The draft has a section for each part a sheet needs and starts with `DRAFT_MARKER`, so it
is plainly a draft until an administrator has reviewed it and removed the line. A sheet
that has no marker has been reviewed, and is only replaced when asked to.
"""

import logging
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from eidolon.characters import DRAFT_MARKER, Character, is_draft
from eidolon.corpus import Episode, StoryCorpus
from eidolon.llm import ChatLLM, ChatMessage

log = logging.getLogger(__name__)

SECTIONS = ("身份", "自称", "对他人的称呼", "口癖", "组合成员", "硬性规则")
"""The parts of a character sheet, each a `##` section of the draft."""

DEFAULT_BUDGET = 40_000
"""How much material, in characters, goes into one request to the background model."""
MAX_BATCHES = 20
"""The most batches of episodes the background model takes notes on for one draft."""
_MISSING = "（待补充：剧情素材中没有找到，请人工填写）"


class SheetReviewed(RuntimeError):
    """The file exists and is a reviewed sheet; replacing it needs `overwrite`."""


class NoEpisodes(RuntimeError):
    """The character is cast in no episode, so there is nothing to draft from."""


@dataclass(frozen=True)
class DraftReport:
    episodes: int
    """How many episodes the character is cast in."""
    episodes_read: int
    """How many of them the background model read; fewer when they had to be sampled."""
    requests: int
    """How many requests the background model answered."""


async def draft_sheet(
    character: Character,
    corpus: StoryCorpus,
    background_llm: ChatLLM,
    *,
    output: Path | None = None,
    overwrite: bool = False,
    budget: int = DEFAULT_BUDGET,
) -> DraftReport:
    """Draft `character`'s sheet and write it to her sheet file, or to `output`."""
    path = check_replaceable(output or _sheet_path(character), overwrite)
    episodes = corpus.list_episodes(character.id)
    if not episodes:
        raise NoEpisodes(f"剧情库里没有 {character.name} 出场的剧情，请先导入剧情并检查 speakers")

    texts = [_episode_text(e)[:budget] for e in episodes]
    if sum(map(len, texts)) > budget * MAX_BATCHES:
        texts = _sample(texts, budget * MAX_BATCHES)
    drafter = _Drafter(character, background_llm, budget)
    material, kind = texts, "剧情"
    while sum(map(len, material)) > budget:
        material, kind = await drafter.take_notes(material, kind), "笔记"
    answer = await drafter.ask(_draft_instructions(character, kind), "\n\n".join(material))

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_draft(character, answer), encoding="utf-8")
    return DraftReport(len(episodes), len(texts), drafter.requests)


def check_replaceable(path: Path, overwrite: bool = False) -> Path:
    """`path`, if a draft may be written to it: it does not exist, is itself an unreviewed
    draft, or `overwrite` is set. Raises `SheetReviewed` if not."""
    if path.exists() and not overwrite and not is_draft(path.read_text(encoding="utf-8")):
        raise SheetReviewed(f"{path} 已存在且是校对过的人设")
    return path


def _sheet_path(character: Character) -> Path:
    assert character.sheet_path is not None, "characters come from a configuration file"
    return character.sheet_path


class _Drafter:
    def __init__(self, character: Character, llm: ChatLLM, budget: int) -> None:
        self._character = character
        self._llm = llm
        self._budget = budget
        self.requests = 0

    async def take_notes(self, material: Sequence[str], kind: str) -> list[str]:
        """Notes on each batch of `material` that fits in one request."""
        batches = _batches(material, self._budget)
        notes = []
        for i, batch in enumerate(batches, 1):
            log.info("taking notes on batch %d of %d", i, len(batches))
            answer = await self.ask(_notes_instructions(self._character, kind), batch)
            # Kept short enough that several fit in a batch, so taking notes on notes ends.
            notes.append(answer.strip()[: self._budget // 3])
        return notes

    async def ask(self, instructions: str, material: str) -> str:
        prompt = [ChatMessage("system", instructions), ChatMessage("user", material)]
        self.requests += 1
        return "".join([c async for c in self._llm.stream(prompt) if isinstance(c, str)])


def _episode_text(episode: Episode) -> str:
    lines = [f"## {episode.category}｜{episode.source}「{episode.title}」"]
    for line in episode.lines:
        text = f"{line.speaker}：{line.ja}" if line.speaker else line.ja
        lines.append(f"{text}（{line.zh}）" if line.zh else text)
    return "\n".join(lines)


def _sample(texts: list[str], size: int) -> list[str]:
    """Episodes spread evenly over `texts`, in order, adding up to about `size` characters."""
    step = sum(map(len, texts)) / size
    sampled, position = [], 0.0
    while round(position) < len(texts):
        sampled.append(texts[round(position)])
        position += step
    return sampled


def _batches(texts: Sequence[str], budget: int) -> list[str]:
    batches: list[list[str]] = [[]]
    size = 0
    for text in texts:
        if batches[-1] and size + len(text) > budget:
            batches.append([])
            size = 0
        batches[-1].append(text)
        size += len(text) + 2
    return ["\n\n".join(batch) for batch in batches]


def _notes_instructions(character: Character, kind: str) -> str:
    return f"""\
你在为《偶像大师 闪耀色彩》的偶像{character.name}整理人设素材。下面是她出场的一部分{kind}。
用中文记下能看出她是什么样的人的要点：身份和经历、自称、对制作人和其他人物的称呼、口癖和说话方式、\
所属组合和成员、性格和价值观、她绝不会做或说的事。
称呼、自称和口癖要照原文写出日语，并尽量注明出自哪段剧情。只写素材里看得到的内容，不要推测。
只输出要点列表。"""


def _draft_instructions(character: Character, kind: str) -> str:
    sections = "\n".join(f"## {s}" for s in SECTIONS)
    return f"""\
你在为一个角色扮演对话系统撰写《偶像大师 闪耀色彩》的偶像{character.name}的人设。\
这份人设会完整放进对话模型的系统提示词里，由对话模型扮演她和制作人（用户）对话。
根据下面她出场的{kind}，用中文、以第二人称（「你是……」）写出人设，依次包含这些小节，小节标题照抄：
{sections}

- 身份：她是谁、所属事务所、正在和制作人说话。
- 自称、对他人的称呼、口癖：照原文写出日语，对制作人和其他主要人物分别写。
- 组合成员：所属组合和其他成员，以及她和各成员的关系。
- 硬性规则：扮演她时必须遵守、绝不能违反的事，包括始终以她的身份说话、不提到自己是 AI。
只写素材里看得到的内容，没有依据的小节写「（待补充）」。只输出这些小节，不要其他文字。"""


_SECTION = re.compile(r"^##\s*(.+?)\s*$", re.MULTILINE)


def _draft(character: Character, answer: str) -> str:
    """The sheet file: the marker, a title, and every section, filling in any the model
    left out."""
    body = re.sub(r"^```\w*\n|\n```\s*$", "", answer.strip()).strip()
    present = {m.group(1) for m in _SECTION.finditer(body)}
    missing = [f"## {s}\n{_MISSING}" for s in SECTIONS if s not in present]
    parts = [DRAFT_MARKER, f"# 人设：{character.name}", body, *missing]
    return "\n\n".join(p for p in parts if p) + "\n"
