"""Retrieval for a conversation turn: whether to look anything up, and what to bring back.

The judge model (`judge`) first judges what the user just said needs: nothing, so small
talk costs no retrieval latency; memories only, when the user talks about their
own life, for which the turn finds the memories of what they have told any of the
characters; references, for which the reference sources (the story corpus, only episodes
the character is cast in; the character's facts; and the work facts all characters share,
when there is a world setting) are searched with the same query vector, the candidates
reranked together, and the best few that are relevant enough go into the prompt, each
under its source's heading, while the turn finds the user's memories alongside; or
recall, for a question about how some past episode went, for which the episodes are
recalled as the recall-story tool would, the lives and releases of the work facts
reranked along with them, and the result goes into the prompt, saving the chat model a
round of calling it. The story not telling how something went does not mean she never
went through it: she may have stood on that stage all the same.

Retrieval never fails a turn: if the judge model cannot answer, the turn retrieves anyway;
if embedding or reranking fails, the turn goes on without references (or memories).

The chat model can also look an episode up itself with the recall-story tool, for
general questions like "what happened that time with the photo book" that the judge
model did not catch: the best matching episodes she is cast in come back with where they
sit in her story catalog (card or event, and its other episodes) and what happened in them.
The tool looks only in the story.
"""

import asyncio
import logging
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Literal, Protocol

from eidolon.characters import Character
from eidolon.corpus import CatalogSource, Episode, StoryCorpus
from eidolon.embedding import Embedder, EmbeddingError, Reembeddable
from eidolon.facts import CharacterFacts
from eidolon.judge import (
    FALLBACK_FAMILY,
    JUDGE_THRESHOLDS,
    JudgeError,
    JudgeModel,
    JudgeThresholds,
)
from eidolon.llm import Tool
from eidolon.memory import MemoryTurn
from eidolon.references import Reference, ReferenceKind, ReferenceSource
from eidolon.rerank import Reranker, RerankError
from eidolon.store import Message
from eidolon.work_facts import WORK_RULE, WorkFacts
from eidolon.world import EntryKind, World, WorldEntry

log = logging.getLogger(__name__)

MAX_REFERENCES = 5
"""The most references one turn's prompt carries, after reranking."""
CANDIDATES_PER_SOURCE = 12
"""How many candidates each reference source offers the reranker."""
JUDGE_HISTORY = 4
"""How many of the latest messages the judge model sees along with what the user just said."""


RECALL_EPISODES = 2
"""The most episodes one call of the recall-story tool brings back."""
RECALL_ENTRIES = 3
"""The most lives and releases of the work facts recalling brings back along with the
episodes."""
RECALL_KINDS: tuple[EntryKind, ...] = ("live", "release")
"""What of the work facts recalling looks in: how a live or a release went, not a song."""
RECALL_EPISODE_CHARS = 3000
"""How much of an episode's dialogue the recall-story tool brings back before cutting it short."""

RECALL_STORY_TOOL = Tool(
    name="recall_story",
    description="回顾剧情：在你亲身经历过的原作剧情中查找和某件事有关的剧情，返回它在你的剧情目录中的位置"
    "（哪张卡或哪个活动）和剧情内容。当制作人问起「那次……是怎么回事」这类过去的事、"
    "而你想不起具体经过时使用；闲聊时不需要。",
    parameters={
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "要回顾的事，写成一句概括，例如「拍写真集的那次」「W.I.N.G. 决赛」",
            }
        },
        "required": ["query"],
    },
)


_CANON_RULE = (
    "剧情里没有记录制作人当时选了哪个选项，不要断言制作人当时说了什么或选了什么。"
)
_NOT_IN_STORY = (
    "剧情库里没有记录这段经过，但这不等于这件事没有发生过。"
    "不要编造经过，也不要说没有这回事；可以坦率地说细节记不太清了"
)


Need = Literal["nothing", "memories", "references", "recall"]
"""What a turn needs looked up: nothing, the user's memories only, references from the
reference sources along with the user's memories, or the recall of a past episode."""


class RetrievalJudge(Protocol):
    async def judge(self, character: Character, history: Sequence[Message], text: str) -> Need:
        """What answering `text` needs looked up."""
        ...


class StoryReferences:
    """The story corpus as a reference source: the passages of the episodes the character
    is cast in."""

    kind: ReferenceKind = "episode"
    heading = "剧情"
    guide = "「剧情」是你亲身经历过的原作剧情，可以像回忆往事一样自然地提起，不要照搬台词。" + _CANON_RULE
    label = "剧情库"
    unit = "段"

    def __init__(self, corpus: StoryCorpus) -> None:
        self.corpus = corpus

    async def search(
        self, query_vector: Sequence[float], character: Character, limit: int
    ) -> list[Reference]:
        passages = await asyncio.to_thread(
            self.corpus.search_by_vector, query_vector, character.id, limit
        )
        return [Reference(self.kind, p.text, p.episode.id) for p in passages]

    async def embed_missing(self, batch: int, progress: Callable[[int], None]) -> int:
        return await self.corpus.embed_missing(batch, progress)

    def forget_other_models(self) -> int:
        """Nothing: each passage keeps only one vector, which embedding it again replaces."""
        return 0

    def close(self) -> None:
        self.corpus.close()


class ReferenceSources:
    """The reference sources a turn looks references up in, all searched with the same
    query vector and reranked together; and the story corpus and the work facts, which
    recalling searches itself. Closed all at once."""

    def __init__(
        self,
        embedder: Embedder,
        sources: Sequence[ReferenceSource],
        corpus: StoryCorpus,
        work: WorkFacts | None,
        unsearched: Sequence[ReferenceSource] = (),
    ) -> None:
        """`sources` are closed with the whole, `corpus` and `work` among them; so are
        `unsearched`, sources with nothing to search, kept only to be embedded again."""
        self.embedder = embedder
        self.corpus = corpus
        self.work = work
        self._sources = list(sources)
        self._unsearched = list(unsearched)

    async def rank(
        self, reranker: Reranker, character: Character, text: str
    ) -> list[tuple[Reference, float]]:
        """Every candidate reference for `text`, with the reranker's score, best first: as
        many as `CANDIDATES_PER_SOURCE` of each source's nearest the query, reranked
        together. Raises EmbeddingError or RerankError if either service fails."""
        query_vector = await self.embedder.embed_query(text)
        found = await asyncio.gather(
            *(s.search(query_vector, character, CANDIDATES_PER_SOURCE) for s in self._sources)
        )
        candidates = [r for references in found for r in references]
        if not candidates:
            return []
        best = await reranker.rerank(text, [c.text for c in candidates], len(candidates))
        return [(candidates[i], score) for i, score in best]

    def embedded(self) -> list[Reembeddable]:
        """Every source, for `eidolon reembed`, the unsearched among them."""
        return [*self._sources, *self._unsearched]

    def prompt(self, references: Sequence[Reference]) -> str:
        """The prompt section carrying a turn's references, each under its source's heading."""
        headings = {s.kind: s.heading for s in self._sources}
        lines = [
            "# 回忆与资料",
            "下面是和制作人这句话可能有关的内容，按相关程度排列，和话题无关的可以忽略。",
            *(f"- {s.guide}" for s in self._sources),
        ]
        for reference in references:
            lines += ["", f"## {headings[reference.kind]}", reference.text]
        return "\n".join(lines)

    def close(self) -> None:
        for source in [*self._sources, *self._unsearched]:
            source.close()


def open_reference_sources(
    path: Path,
    embedder: Embedder,
    characters: Iterable[Character],
    world: World | None,
    *,
    warn: bool = True,
) -> ReferenceSources:
    """The reference sources in the database at `path`: the story, the characters' facts
    and, given a world setting, the work facts; without one, the work facts are there only
    to be embedded again, which forgets whatever vectors they had. Warns (unless not to
    `warn`) if story passages have no vector from `embedder`'s model, as they cannot be
    found."""
    corpus = StoryCorpus(path, embedder)
    if warn and (missing := corpus.count_missing_vectors()):
        log.warning(
            "%d story passages have no vectors from the embedding model %s and cannot be"
            " found: run `eidolon reembed` after changing the embedding service, model"
            " or dimensions",
            missing, embedder.model,
        )
    sources: list[ReferenceSource] = [
        StoryReferences(corpus), CharacterFacts(path, embedder, characters)
    ]
    work = WorkFacts(path, embedder, world)
    if world is None:
        return ReferenceSources(embedder, sources, corpus, None, [work])
    sources.append(work)
    return ReferenceSources(embedder, sources, corpus, work)


@dataclass(frozen=True)
class Retrieved:
    """What a turn looked up."""

    prompt: str | None
    """The prompt section carrying the references or recalled episodes, if any."""
    memories_prompt: str | None = None
    """The prompt section carrying the user's memories relevant to the turn, if any."""
    recalled: bool = False
    """Whether the recall-story tool already ran, so the chat model need not call it."""


class Retrieval:
    def __init__(
        self,
        judge: RetrievalJudge,
        sources: ReferenceSources,
        reranker: Reranker,
        min_relevance: float,
    ) -> None:
        """`min_relevance` is the reranker's score below which a reference or recalled
        episode is left out (see `rerank.KNOWN_THRESHOLDS`)."""
        self._judge = judge
        self._sources = sources
        self._reranker = reranker
        self._min_relevance = min_relevance

    async def retrieve(
        self,
        character: Character,
        history: Sequence[Message],
        text: str,
        memory: MemoryTurn | None = None,
    ) -> Retrieved:
        """Look up what this turn needs, finding the user's memories through `memory`."""
        try:
            need = await self._judge.judge(character, history, text)
        except JudgeError:
            log.warning("retrieval judge failed; retrieving anyway", exc_info=True)
            need = "references"
        if need == "recall":
            return Retrieved(
                await self._recall(character, text, self._sources.work), recalled=True
            )
        if need == "memories":
            return Retrieved(None, await _find(memory, text))
        if need == "references":
            references, memories = await asyncio.gather(
                self._references(character, text), _find(memory, text)
            )
            return Retrieved(self._sources.prompt(references) if references else None, memories)
        return Retrieved(None)

    async def _references(self, character: Character, text: str) -> list[Reference]:
        """The references for `text`, most relevant first."""
        try:
            ranked = await self._sources.rank(self._reranker, character, text)
        except (EmbeddingError, RerankError):
            log.warning("retrieval failed; replying without references", exc_info=True)
            return []
        return [r for r, score in ranked if score >= self._min_relevance][:MAX_REFERENCES]

    async def recall_story(self, character: Character, query: str) -> str:
        """The recall-story tool: the episodes `character` is cast in that best match
        `query`, for the chat model to answer from."""
        return await self._recall(character, query, None)

    async def _recall(self, character: Character, query: str, work: WorkFacts | None) -> str:
        """The episodes `character` is cast in that best match `query`, and the lives and
        releases of `work` (if given), reranked together."""
        corpus = self._sources.corpus
        try:
            query_vector = await self._sources.embedder.embed_query(query)
            passages, entries = await asyncio.gather(
                asyncio.to_thread(
                    corpus.search_by_vector, query_vector, character.id, CANDIDATES_PER_SOURCE
                ),
                _search_work(work, query_vector),
            )
            documents = [p.text for p in passages] + [e.text for e in entries]
            best = (
                await self._reranker.rerank(query, documents, len(documents)) if documents else []
            )
        except (EmbeddingError, RerankError):
            log.warning("recall failed", exc_info=True)
            return "暂时想不起来，现在查不到剧情。不要编造经过，可以坦率地说记不太清了。"
        episodes: dict[str, Episode] = {}
        found: list[WorldEntry] = []
        for i, score in best:
            if score < self._min_relevance:
                continue
            if i < len(passages):
                if len(episodes) < RECALL_EPISODES:
                    episodes.setdefault(passages[i].episode.id, passages[i].episode)
            elif len(found) < RECALL_ENTRIES:
                found.append(entries[i - len(passages)])
        if not episodes and not found:
            return f"没有想起和「{query}」有关的剧情：{_NOT_IN_STORY}，或者问问制作人。"
        catalog = await asyncio.to_thread(corpus.catalog, character.id) if episodes else []
        return recall_prompt(query, list(episodes.values()), catalog, found)

    def close(self) -> None:
        self._sources.close()


async def _find(memory: MemoryTurn | None, text: str) -> str | None:
    return await memory.find(text) if memory else None


async def _search_work(work: WorkFacts | None, query_vector: Sequence[float]) -> list[WorldEntry]:
    if work is None:
        return []
    return await work.search_entries(query_vector, CANDIDATES_PER_SOURCE, RECALL_KINDS)


def recall_prompt(
    query: str,
    episodes: Sequence[Episode],
    catalog: Sequence[CatalogSource],
    entries: Sequence[WorldEntry] = (),
) -> str:
    """What recalling brings back: each episode under its place in the story catalog, then
    the lives and releases of the work facts."""
    lines = [f"# 回顾剧情：{query}"]
    if episodes:
        lines.append(
            "下面是你经历过的剧情中和这件事最相关的，按相关程度排列。用自己的话回忆经过，不要照搬台词。"
            + _CANON_RULE
        )
    else:
        lines.append(f"{_NOT_IN_STORY}。")
    if entries:
        lines.append(f"「{WorkFacts.heading}」是和这件事有关的演出或唱片的事实。" + WORK_RULE)
    for episode in episodes:
        source = next(
            (s for s in catalog if any(e.episode_id == episode.id for e in s.episodes)), None
        )
        lines += ["", f"## {episode.category} / {episode.source} /「{episode.title}」"]
        if source is not None and len(source.episodes) > 1:
            titles = "".join(f"「{e.title}」" for e in source.episodes)
            lines.append(f"（{episode.source}中你出场的剧情依次是：{titles}）")
        lines.append(_transcript(episode))
    for entry in entries:
        lines += ["", f"## {WorkFacts.heading}", entry.text]
    return "\n".join(lines)


def _transcript(episode: Episode) -> str:
    text = ""
    for line in episode.lines:
        said = f"{line.speaker}：{line.ja}" if line.speaker else line.ja
        if line.zh:
            said += f"（{line.zh}）"
        if len(text) + len(said) > RECALL_EPISODE_CHARS:
            return (text or said[:RECALL_EPISODE_CHARS]) + "……（后略）"
        text += said + "\n"
    return text.rstrip("\n")


_JUDGE_QUESTION = {
    "type": "noul",
    "instructions": "角色扮演对话中，角色是《偶像大师 闪耀色彩》的偶像，正在和她的制作人对话。"
    "可检索的内容有三类：剧情，即她亲身经历过的原作剧情；角色资料，即关于她自己和身边人物的设定"
    "（档案、人物关系等）；作品资料，即作品里的歌曲、唱片和演出（演唱者、发售日、曲目、"
    "演出的日期、会场和出演者）。回答制作人最新的一句话，是否需要检索这些内容？",
    "criteria": {
        "true": "需要回忆过去的具体经历、提到具体的人物或事件、需要确认角色设定细节，"
        "或问到具体的歌曲、唱片、演出",
        "false": "只是寒暄、闲聊、情绪回应，或只凭上文就能回答",
    },
}
_RECALL_QUESTION = {
    "type": "noul",
    "instructions": "制作人最新的一句话，是不是在问角色过去某一次具体经历的来龙去脉"
    "（例如「那次……是怎么回事」「还记得……那次吗」），需要回想那段经历的完整经过才能回答？",
    "criteria": {
        "true": "问的是过去某一次具体的事情、活动、工作或比赛的经过和当时的心情",
        "false": "寒暄闲聊、问喜好或设定、问身边人物近况，或者只是顺口提到过去",
    },
}
_ABOUT_PRODUCER_QUESTION = {
    "type": "noul",
    "instructions": "角色扮演对话中，角色是《偶像大师 闪耀色彩》的偶像，正在和她的制作人对话。"
    "制作人最新的一句话，是否说起或问起制作人自己的事（生活、近况、工作安排、计划、家人、宠物、喜好、"
    "身体状况等），而制作人以前对偶像们说过的相关的事可能有助于回应？",
    "criteria": {
        "true": "说起或问起制作人自己的生活、近况、计划、家人宠物、喜好，或提到以前对偶像说过的事",
        "false": "只是打招呼、说偶像自己的事、问原作剧情或角色设定，与制作人自己的生活无关",
    },
}
@dataclass(frozen=True)
class RetrievalAnswer:
    """The judge model's probability of yes to each of its three questions."""

    needs_retrieval: float
    recall: float
    about_producer: float


class ModelRetrievalJudge:
    """The judge model, asked three yes-or-no questions (`noul`) about the turn in one
    request: whether it needs looking anything up, whether it asks how a past episode
    went, and whether it is about the user's own life. Each answer is yes at or above the
    model's threshold for it."""

    def __init__(
        self,
        judge_model: JudgeModel,
        thresholds: JudgeThresholds = JUDGE_THRESHOLDS[FALLBACK_FAMILY],
    ) -> None:
        self._judge_model = judge_model
        self.thresholds = thresholds

    async def judge(self, character: Character, history: Sequence[Message], text: str) -> Need:
        return self.decide(await self.ask(character, history, text))

    async def ask(
        self, character: Character, history: Sequence[Message], text: str
    ) -> RetrievalAnswer:
        """How likely the judge model finds yes to each question about `text`."""
        recent = []
        for message in history[-JUDGE_HISTORY:]:
            if message.role == "user":
                recent.append(f"制作人：{message.text}")
            else:
                recent.append(f"{character.name}：{message.without_cues().ja}")
        answers = await self._judge_model.ask(
            {
                "角色": character.name,
                "上文": recent or "（对话刚开始）",
                "制作人最新的一句话": text,
            },
            {
                "needs_retrieval": _JUDGE_QUESTION,
                "recall": _RECALL_QUESTION,
                "about_producer": _ABOUT_PRODUCER_QUESTION,
            },
        )
        try:
            return RetrievalAnswer(
                float(answers["needs_retrieval"]["noul"]),
                float(answers["recall"]["noul"]),
                float(answers["about_producer"]["noul"]),
            )
        except (ValueError, KeyError, TypeError) as e:
            raise JudgeError("判断模型的返回无法解析（缺少回答）") from e

    def decide(self, answer: RetrievalAnswer) -> Need:
        """What a turn so answered needs: recall first, then references, then memories."""
        if answer.recall >= self.thresholds.recall:
            return "recall"
        if answer.needs_retrieval >= self.thresholds.needs_retrieval:
            return "references"
        if answer.about_producer >= self.thresholds.about_producer:
            return "memories"
        return "nothing"
