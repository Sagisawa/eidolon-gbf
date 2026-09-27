"""The assembly root: from settings to the running backend, and back down again.

`build` makes every module the backend runs on from `Settings`: the store, the
characters, the identity providers users sign in with, the chat and background models,
the services users bring their own keys to, retrieval, memory, the conversation engine,
usage limits and voice calls. It decides what is on. Retrieval needs Jev, the
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

from eidolon.accounts import Accounts
from eidolon.call import Calls, SonioxFishSpeech, Speech
from eidolon.characters import Character, load_characters
from eidolon.clock import Clock, utc_now
from eidolon.config import Settings
from eidolon.corpus import StoryCorpus
from eidolon.embedding import Embedder, open_embedder
from eidolon.engine import ConversationEngine
from eidolon.facts import FactIndex
from eidolon.identity import IdentityProvider, ProviderName, open_identity_providers
from eidolon.llm import ChatLLM
from eidolon.llm.providers import open_llm
from eidolon.memory import Memories
from eidolon.own_keys import LLMService, OwnKeys, ProviderLLMService
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
    own_keys: OwnKeys
    accounts: Accounts
    identity_providers: dict[ProviderName, IdentityProvider]
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
    identity_providers: dict[ProviderName, IdentityProvider] | None = None,
    own_llm_service: LLMService | None = None,
) -> Backend:
    """The backend `settings` describe, with any of the outside services passed in
    used instead of made. Raises RuntimeError, having opened nothing, if the character
    configuration is broken."""
    characters = load_characters(settings.characters_path)
    clock = clock or utc_now
    closers: list[Closer] = []

    store = Store(settings.database_path)
    closers.append(store.close)
    if identity_providers is None:
        identity_providers = open_identity_providers(settings.github, settings.google)
        closers.extend(p.aclose for p in identity_providers.values())
    if chat_llm is None:
        chat_llm = open_llm(settings.chat_llm)
        closers.append(chat_llm.aclose)
    if embedder is None and settings.embedding is not None:
        opened = open_embedder(settings.embedding)
        closers.append(opened.aclose)
        embedder = opened
    if (
        settings.domain is not None
        and settings.embedding is not None
        and settings.embedding.provider == "gemini"
        and not settings.gemini_billing_enabled
    ):
        log.warning(
            "a public deployment is embedding with Gemini without GEMINI_BILLING_ENABLED=1:"
            " on the free tier Google may use what it embeds, users' memories included, to"
            " improve its products. Turn on billing and set GEMINI_BILLING_ENABLED=1, or"
            " embed with SiliconFlow (ADR-0005, revised 2026-09-27)"
        )
    thresholds = DEFAULT_THRESHOLDS
    if (r := settings.rerank) is not None:
        thresholds = thresholds_for(r)
        if r.model not in KNOWN_THRESHOLDS:
            log.warning(
                "rerank model %s has not been calibrated; its thresholds default to those of"
                " %s (set RERANK_MIN_RELEVANCE and RERANK_MEMORY_MIN_RELEVANCE to choose):"
                " using references %s, memories %s",
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
        corpus = StoryCorpus(settings.database_path, embedder)
        if missing := corpus.count_missing_vectors():
            log.warning(
                "%d story passages have no vectors from the embedding model %s and cannot be"
                " found: run `eidolon reembed` after changing the embedding service, model"
                " or dimensions",
                missing, embedder.model,
            )
        retrieval = Retrieval(
            jev,
            embedder,
            corpus,
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
    if own_llm_service is None:
        own_llm_service = ProviderLLMService(public_only=settings.domain is not None)
        closers.append(own_llm_service.aclose)
    speech = speech or SonioxFishSpeech(settings.fish_audio_model)
    own_keys = OwnKeys(store, settings.secret_key, own_llm_service, speech)
    calls = Calls(settings, engine, usage, speech, clock, own_keys, store)
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
        own_keys=own_keys,
        accounts=Accounts(store, clock, memories, calls),
        identity_providers=identity_providers,
        _closers=closers,
    )
