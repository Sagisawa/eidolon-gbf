"""The assembly root: from settings to the running backend, and back down again.

`build` makes every module the backend runs on from `Settings`: the store, the
characters and the world setting beside them, the identity providers users sign in with, the chat and background models,
the services users bring their own keys to, retrieval, memory, the conversation engine,
usage limits and voice calls. It decides what is on. Retrieval needs the judge model, the
embedder and the reranker all at hand, and memory is on only with retrieval, since only
retrieval finds memories again; judging her emotion during calls needs only the judge
model, the same one; the
background model is always at hand, being the chat model unless configured apart.

The outside services can be passed in instead of made from the settings, as tests do
with fakes. Whoever passes one in closes it; `Backend.aclose` closes only what `build`
made, in the order that lets what is still running finish.
"""

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

from eidolon.accounts import Accounts
from eidolon.call import Calls, Speech, SpeechServices
from eidolon.characters import Character, load_characters
from eidolon.clock import Clock, utc_now
from eidolon.config import DEFAULT_BAILIAN_STT_MODEL, Settings
from eidolon.embedding import Embedder, open_embedder
from eidolon.emotion import EmotionJudge, EmotionJudging, ModelEmotionJudge
from eidolon.engine import ConversationEngine
from eidolon.identity import IdentityProvider, ProviderName, open_identity_providers
from eidolon.llm import ChatLLM
from eidolon.llm.providers import open_llm
from eidolon.memory import Memories
from eidolon.own_keys import DeployerKeys, LLMService, OwnKeys, ProviderLLMService
from eidolon.rerank import (
    DEFAULT_THRESHOLDS,
    FALLBACK_MODEL,
    KNOWN_THRESHOLDS,
    Reranker,
    SiliconFlowReranker,
    thresholds_for,
)
from eidolon.judge import open_judge
from eidolon.retrieval import (
    ModelRetrievalJudge,
    Retrieval,
    RetrievalJudge,
    open_reference_sources,
)
from eidolon.store import Store
from eidolon.usage import UsageLimiter
from eidolon.world import load_world, world_path

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
    emotions: EmotionJudging | None
    """Judging her emotion in each segment during calls; None without the judge model."""
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
    retrieval_judge: RetrievalJudge | None = None,
    emotion_judge: EmotionJudge | None = None,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    clock: Clock | None = None,
    speech: Speech | None = None,
    identity_providers: dict[ProviderName, IdentityProvider] | None = None,
    own_llm_service: LLMService | None = None,
) -> Backend:
    """The backend `settings` describe, with any of the outside services passed in
    used instead of made. Raises RuntimeError, having opened nothing, if the character
    configuration or the world setting is broken, or a character is none of its idols."""
    characters = load_characters(settings.characters_path)
    world = load_world(path := world_path(settings.characters_path))
    if world is None:
        log.info(
            "there is no world setting at %s: characters go without it (run `eidolon world"
            " sync` and commit the file it writes)",
            path,
        )
    else:
        world.check_characters(characters, path)
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
    if background_llm is None:
        background_llm = open_llm(settings.background_llm)
        closers.append(background_llm.aclose)
    if own_llm_service is None:  # users' own LLMs write down memories too
        own_llm_service = ProviderLLMService(public_only=settings.domain is not None)
        closers.append(own_llm_service.aclose)
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
    if (retrieval_judge is None or emotion_judge is None) and settings.judge is not None:
        judge_model = open_judge(settings.judge)
        closers.append(judge_model.aclose)
        retrieval_judge = retrieval_judge or ModelRetrievalJudge(judge_model)
        emotion_judge = emotion_judge or ModelEmotionJudge(judge_model)
    emotions = None
    if emotion_judge is not None:
        emotions = EmotionJudging(
            emotion_judge, settings.emotion.min_probability, settings.emotion.timeout
        )

    retrieval = None
    if retrieval_judge is not None and embedder is not None and reranker is not None:
        retrieval = Retrieval(
            retrieval_judge,
            open_reference_sources(
                settings.database_path, embedder, characters.values(), world
            ),
            reranker,
            thresholds.references,
        )
        closers.append(retrieval.close)
        memories = Memories(
            settings.database_path, characters, clock, embedder=embedder, reranker=reranker,
            min_relevance=thresholds.memories,
        )
    else:
        log.info(
            "retrieval and memory are off: they need the embedding service's key"
            " (SILICONFLOW_API_KEY, or GEMINI_API_KEY with EMBEDDING_PROVIDER=gemini),"
            " SILICONFLOW_API_KEY for reranking, and the judge model's (JEV_API_KEY, or"
            " CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID with JUDGE_PROVIDER=cloudflare)"
        )
        memories = Memories(settings.database_path, characters, clock)
    closers.append(memories.aclose)  # closed before the clients, so what it writes down can finish

    engine = ConversationEngine(
        store, characters, memories, clock, retrieval, settings.history_turns, world
    )
    usage = UsageLimiter(settings.database_path, settings.usage_limits, clock)
    closers.append(usage.close)
    # Users' own DashScope keys hear with the deployer's model, or the default one where the
    # deployer chose Soniox.
    bailian_model = (
        settings.bailian_stt_model if settings.stt_provider == "bailian"
        else DEFAULT_BAILIAN_STT_MODEL
    )
    speech = speech or SpeechServices(settings.fish_audio_model, bailian_model)
    deployer = DeployerKeys(chat_llm, background_llm, settings.stt_key, settings.fish_audio_api_key)
    own_keys = OwnKeys(store, settings.secret_key, own_llm_service, deployer, speech)
    calls = Calls(settings, engine, usage, speech, clock, own_keys, store, emotions)
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
        emotions=emotions,
        own_keys=own_keys,
        accounts=Accounts(store, clock, memories, calls),
        identity_providers=identity_providers,
        _closers=closers,
    )
