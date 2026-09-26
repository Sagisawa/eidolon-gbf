"""The assembly root: from settings to the running backend, and back down again.

`build` makes every module the backend runs on from `Settings`: the store, the
characters, the chat and background models, retrieval, memory, the conversation
engine, usage limits and voice calls. It decides what is on. Retrieval needs Jev, the
embedder and the reranker all at hand, and memory is on only with retrieval, since only
retrieval finds memories again; the background model is always at hand, being the chat
model unless configured apart.

The outside services can be passed in instead of made from the settings, as tests do
with fakes. Whoever passes one in closes it; `Backend.aclose` closes only what `build`
made, in the order that lets what is still running finish.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from eidolon.call import Calls, SonioxFishSpeech, Speech
from eidolon.characters import Character, load_characters
from eidolon.clock import Clock, utc_now
from eidolon.config import Settings
from eidolon.corpus import StoryCorpus
from eidolon.embedding import Embedder, open_embedder
from eidolon.engine import ConversationEngine
from eidolon.facts import FactIndex
from eidolon.llm import ChatLLM
from eidolon.llm.providers import open_llm
from eidolon.memory import Memories
from eidolon.rerank import (
    DEFAULT_THRESHOLDS,
    FALLBACK_MODEL,
    KNOWN_THRESHOLDS,
    Reranker,
    SiliconFlowReranker,
    thresholds_for,
)
from eidolon.retrieval import JevJudge, Retrieval, RetrievalJudge
from eidolon.store import Store
from eidolon.usage import UsageLimiter

log = logging.getLogger(__name__)

Closer = Callable[[], Awaitable[None] | None]


@dataclass
class Backend:
    """Everything the API serves from, ready to run."""

    settings: Settings
    store: Store
    characters: dict[str, Character]
    memories: Memories
    engine: ConversationEngine
    usage: UsageLimiter
    clock: Clock
    calls: Calls
    _closers: list[Closer] = field(default_factory=list, repr=False)

    async def aclose(self) -> None:
        """Close what `build` opened, last opened first."""
        for close in reversed(self._closers):
            result = close()
            if result is not None:
                await result


def build(
    settings: Settings,
    *,
    chat_llm: ChatLLM | None = None,
    background_llm: ChatLLM | None = None,
    jev: RetrievalJudge | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    clock: Clock | None = None,
    speech: Speech | None = None,
) -> Backend:
    """The backend `settings` describe, with any of the outside services passed in
    used instead of made. Raises RuntimeError, having opened nothing, if the character
    configuration is broken."""
    characters = load_characters(settings.characters_path)
    clock = clock or utc_now
    closers: list[Closer] = []

    store = Store(settings.database_path)
    closers.append(store.close)
    if chat_llm is None:
        chat_llm = open_llm(settings.chat_llm)
        closers.append(chat_llm.aclose)
    if embedder is None and settings.embedding is not None:
        opened = open_embedder(settings.embedding)
        closers.append(opened.aclose)
        embedder = opened
    thresholds = DEFAULT_THRESHOLDS
    if (r := settings.rerank) is not None:
        thresholds = thresholds_for(r)
        if r.model not in KNOWN_THRESHOLDS:
            log.warning(
                "rerank model %s has not been calibrated; using the thresholds of %s"
                " (references %s, memories %s) unless RERANK_MIN_RELEVANCE and"
                " RERANK_MEMORY_MIN_RELEVANCE set them",
                r.model, FALLBACK_MODEL, thresholds.references, thresholds.memories,
            )
        if reranker is None:
            reranker = SiliconFlowReranker(r.api_key, r.model, r.base_url)
            closers.append(reranker.aclose)
    if jev is None and (j := settings.jev) is not None:
        judge = JevJudge(j.api_key, j.model, j.base_url)
        closers.append(judge.aclose)
        jev = judge

    retrieval = None
    if jev is not None and embedder is not None and reranker is not None:
        retrieval = Retrieval(
            jev,
            embedder,
            StoryCorpus(settings.database_path, embedder),
            FactIndex(settings.database_path, embedder),
            reranker,
            thresholds.references,
        )
        closers.append(retrieval.close)
        if background_llm is None:
            background_llm = open_llm(settings.background_llm)
            closers.append(background_llm.aclose)
        memories = Memories(
            settings.database_path, characters, clock,
            background_llm=background_llm, embedder=embedder, reranker=reranker,
            min_relevance=thresholds.memories,
        )
    else:
        log.info(
            "retrieval and memory are off: they need the embedding service's key"
            " (SILICONFLOW_API_KEY, or GEMINI_API_KEY with EMBEDDING_PROVIDER=gemini),"
            " SILICONFLOW_API_KEY for reranking, AI_GATEWAY_API_KEY and JEV_MODEL"
        )
        memories = Memories(settings.database_path, characters, clock)
    closers.append(memories.aclose)  # closed before the clients, so what it writes down can finish

    engine = ConversationEngine(
        store, chat_llm, characters, memories, clock, retrieval, settings.history_turns
    )
    usage = UsageLimiter(store, settings.usage_limits, clock)
    calls = Calls(settings, engine, usage, speech or SonioxFishSpeech.from_settings(settings), clock)
    closers.append(calls.aclose)  # closed before memory, so no call is still taking turns
    return Backend(
        settings=settings,
        store=store,
        characters=characters,
        memories=memories,
        engine=engine,
        usage=usage,
        clock=clock,
        calls=calls,
        _closers=closers,
    )
