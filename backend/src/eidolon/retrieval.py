"""Retrieval for a conversation turn: whether to look anything up, and what to bring back.

Jev (through Vercel AI Gateway) first judges whether what the user just said calls
for looking anything up, so small talk costs no retrieval latency. When it does,
the story corpus (only episodes the character is cast in) and the character's facts
are searched with the same query vector, the candidates are reranked together, and
the best few go into the prompt.

Retrieval never fails a turn: if Jev cannot answer, the turn retrieves anyway; if
embedding or reranking fails, the turn goes on without references.
"""

import asyncio
import logging
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

import httpx

from eidolon.characters import Character
from eidolon.corpus import StoryCorpus
from eidolon.embedding import Embedder, EmbeddingError
from eidolon.facts import FactIndex
from eidolon.rerank import Reranker, RerankError
from eidolon.store import Message

log = logging.getLogger(__name__)

MAX_REFERENCES = 5
"""The most references one turn's prompt carries, after reranking."""
CANDIDATES_PER_SOURCE = 12
"""How many candidates each source (story corpus, character facts) offers the reranker."""
JUDGE_HISTORY = 4
"""How many of the latest messages Jev sees along with what the user just said."""


class RetrievalJudge(Protocol):
    async def needs_retrieval(
        self, character: Character, history: Sequence[Message], text: str
    ) -> bool:
        """Whether answering `text` would benefit from the story corpus or character facts."""
        ...


class JudgeError(RuntimeError):
    pass


@dataclass(frozen=True)
class Reference:
    kind: Literal["episode", "fact"]
    text: str


class Retrieval:
    def __init__(
        self,
        judge: RetrievalJudge,
        embedder: Embedder,
        corpus: StoryCorpus,
        facts: FactIndex,
        reranker: Reranker,
    ) -> None:
        self._judge = judge
        self._embedder = embedder
        self._corpus = corpus
        self._facts = facts
        self._reranker = reranker

    async def references(
        self, character: Character, history: Sequence[Message], text: str
    ) -> list[Reference]:
        """What this turn's prompt should carry, most relevant first; empty when the turn
        needs no retrieval."""
        try:
            needed = await self._judge.needs_retrieval(character, history, text)
        except JudgeError:
            log.warning("retrieval judge failed; retrieving anyway", exc_info=True)
            needed = True
        if not needed:
            return []

        try:
            query_vector = await self._embedder.embed_query(text)
            passages, facts = await asyncio.gather(
                asyncio.to_thread(
                    self._corpus.search_by_vector, query_vector, character.id, CANDIDATES_PER_SOURCE
                ),
                self._facts.search_by_vector(query_vector, character, CANDIDATES_PER_SOURCE),
            )
            candidates = [Reference("episode", p.text) for p in passages]
            candidates += [Reference("fact", f) for f in facts]
            if not candidates:
                return []
            best = await self._reranker.rerank(
                text, [c.text for c in candidates], MAX_REFERENCES
            )
        except (EmbeddingError, RerankError):
            log.warning("retrieval failed; replying without references", exc_info=True)
            return []
        return [candidates[i] for i in best[:MAX_REFERENCES]]

    def close(self) -> None:
        self._corpus.close()
        self._facts.close()


def references_prompt(references: Sequence[Reference]) -> str:
    """The prompt section carrying a turn's references."""
    lines = [
        "# 回忆与资料",
        "下面是和制作人这句话可能有关的内容，按相关程度排列，和话题无关的可以忽略。",
        "- 「剧情」是你亲身经历过的原作剧情，可以像回忆往事一样自然地提起，不要照搬台词。"
        "剧情里没有记录制作人当时选了哪个选项，不要断言制作人当时说了什么或选了什么。",
        "- 「角色资料」是关于你自己和身边人物的设定。",
    ]
    for reference in references:
        heading = "剧情" if reference.kind == "episode" else "角色资料"
        lines += ["", f"## {heading}", reference.text]
    return "\n".join(lines)


_JUDGE_INSTRUCTIONS = """\
你负责判断一个角色扮演对话系统是否需要检索资料。角色是《偶像大师 闪耀色彩》的偶像{name}，\
正在和她的制作人对话。可检索的资料有两类：她亲身经历过的原作剧情，以及关于她自己和身边人物的设定\
（档案、人物关系等）。
如果回答制作人最新的这句话需要回忆过去的具体经历、提到具体的人物或事件、或需要确认角色设定细节，\
回答 YES；如果只是寒暄、闲聊、情绪回应，或只凭上文就能回答，回答 NO。
只回答 YES 或 NO。"""


class JevJudge:
    """Jev through Vercel AI Gateway's OpenAI-compatible Chat Completions endpoint."""

    def __init__(
        self, api_key: str, model: str, base_url: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._api_key = api_key
        self._model = model
        self._client = client or httpx.AsyncClient(timeout=httpx.Timeout(5, connect=3))

    async def needs_retrieval(
        self, character: Character, history: Sequence[Message], text: str
    ) -> bool:
        recent = []
        for message in history[-JUDGE_HISTORY:]:
            if message.role == "user":
                recent.append(f"制作人：{message.text}")
            else:
                recent.append(f"{character.name}：{message.ja}")
        conversation = "\n".join(recent) or "（对话刚开始）"
        body = {
            "model": self._model,
            "temperature": 0,
            "max_tokens": 5,
            "messages": [
                {"role": "system", "content": _JUDGE_INSTRUCTIONS.format(name=character.name)},
                {
                    "role": "user",
                    "content": f"上文：\n{conversation}\n\n制作人最新的一句话：\n{text}",
                },
            ],
        }
        try:
            res = await self._client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._api_key}"}
            )
        except httpx.HTTPError as e:
            raise JudgeError(f"无法连接 Jev：{e!r}") from e
        if res.status_code >= 400:
            raise JudgeError(f"Jev 返回 {res.status_code}: {res.text[:500]}")
        try:
            answer = res.json()["choices"][0]["message"]["content"] or ""
        except (ValueError, KeyError, IndexError, TypeError) as e:
            raise JudgeError(f"Jev 的返回无法解析：{res.text[:500]}") from e
        return "YES" in answer.upper()

    async def aclose(self) -> None:
        await self._client.aclose()
