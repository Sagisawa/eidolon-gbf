"""The assembly root: from settings to the running backend, and back down again.

`build` makes every module the backend runs on from `Settings`: the store, the
characters and the world setting beside them, the identity providers users sign in with, the chat and background models,
the services users bring their own keys to, retrieval, memory, the conversation engine,
usage limits and voice calls. It decides what is on. Retrieval needs the judge model, the
embedder and the reranker all at hand, and memory is on only with retrieval, since only
retrieval finds memories again; judging her emotion during calls needs only the judge
model, the same one; the
background model is always at hand, being the chat model unless configured apart.

The deployer's chat and memory models and judge model are made by `ServiceClients` from
the live configuration (`live_config`): `.env`'s settings as overridden in the admin
console, replaced while the backend runs as admins change them; the speech keys, the
thresholds and the limits are read from it as each turn or call starts. `Backend.start`
tries the overrides as the server starts.

The outside services can be passed in instead of made from the settings, as tests do
with fakes; the deployer's chat, memory and judge models only ever by passing in the
`ServiceClients` that make them. Whoever passes one in closes it; `Backend.aclose`
closes only what `build` made, in the order that lets what is still running finish.
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

import httpx

from eidolon.accounts import Accounts
from eidolon.activity import ActivityLog, metered_retrieval
from eidolon.admission import Admissions
from eidolon.call import Calls, Speech, SpeechServices
from eidolon.characters import Character, load_characters
from eidolon.clock import Clock, utc_now
from eidolon.config import DEFAULT_BAILIAN_STT_MODEL, Settings
from eidolon.embedding import Embedder, open_embedder
from eidolon.engine import ConversationEngine
from eidolon.identity import IdentityProvider, ProviderName, open_identity_providers
from eidolon.live_config import LiveConfig
from eidolon.memory import Memories
from eidolon.price_catalog import Catalog
from eidolon.prices import Prices
from eidolon.own_keys import LLMService, OwnKeys, ProviderLLMService
from eidolon.readings import load_readings, readings_path
from eidolon.rerank import (
    FALLBACK_MODEL,
    KNOWN_THRESHOLDS,
    Reranker,
    SiliconFlowReranker,
    thresholds_for,
)
from eidolon.retrieval import Retrieval, open_reference_sources
from eidolon.service_clients import ProviderClients, ServiceClients
from eidolon.store import Store
from eidolon.usage import UsageLimiter
from eidolon.world import World, load_world, world_path

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
    admissions: Admissions
    """Lets text turns and calls begin, and settles them."""
    accounts: Accounts
    identity_providers: dict[ProviderName, IdentityProvider]
    activity: ActivityLog
    """Every turn's activity record, and every service call's, for the dashboard."""
    config: LiveConfig
    prices: Prices
    """The prices the dashboard estimates the deployer's costs at."""
    world: World | None = None
    """The world setting; None without its data file."""
    _closers: list[Closer] = field(default_factory=list, repr=False)
    _keeping_fresh: asyncio.Task[None] | None = field(default=None, repr=False)

    async def start(self) -> None:
        """What is done as the server starts, on its event loop: try the overrides of the
        configuration, falling back to `.env` where one fails; keep the price catalogs
        fresh from now on, fetching them in the background."""
        await self.config.start()
        self._keeping_fresh = asyncio.create_task(self.prices.catalog.keep_fresh())

    async def aclose(self) -> None:
        """Close what `build` opened, last opened first."""
        if self._keeping_fresh is not None:
            self._keeping_fresh.cancel()
        for close in reversed(self._closers):
            result = close()
            if result is not None:
                await result


def build(
    settings: Settings,
    *,
    embedder: Embedder | None = None,
    reranker: Reranker | None = None,
    clock: Clock | None = None,
    speech: Speech | None = None,
    identity_providers: dict[ProviderName, IdentityProvider] | None = None,
    own_llm_service: LLMService | None = None,
    clients: ServiceClients | None = None,
    catalog_transport: httpx.BaseTransport | None = None,
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
    # Users' own DashScope keys hear with the deployer's model, or the default one where the
    # deployer chose Soniox.
    bailian_model = (
        settings.bailian_stt_model if settings.stt_provider == "bailian"
        else DEFAULT_BAILIAN_STT_MODEL
    )
    speech = speech or SpeechServices(
        bailian_model, load_readings(readings_path(settings.characters_path))
    )
    activity = ActivityLog(settings.database_path, clock)
    closers.append(activity.close)
    catalog = Catalog(settings.database_path, clock, catalog_transport)
    closers.append(catalog.close)
    prices = Prices(settings.database_path, clock, catalog)
    closers.append(prices.close)
    config = LiveConfig(
        settings, clients or ProviderClients(), clock, activity=activity, speech=speech
    )
    closers.append(config.aclose)
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
    embedder, reranker = metered_retrieval(activity, settings, embedder, reranker)
    # The judge model is the live configuration's: retrieval asks the one in effect at
    # each question, and each call judges her emotions on the one it connected with.
    retrieval_judge = config.retrieval_judge()

    retrieval = None
    if retrieval_judge is not None and embedder is not None and reranker is not None:
        retrieval = Retrieval(
            retrieval_judge,
            open_reference_sources(
                settings.database_path, embedder, characters.values(), world
            ),
            reranker,
            lambda: config.rerank_thresholds.references,
        )
        closers.append(retrieval.close)
        memories = Memories(
            settings.database_path, characters, clock, embedder=embedder, reranker=reranker,
            min_relevance=lambda: config.rerank_thresholds.memories,
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
        store, characters, memories, clock, retrieval, lambda: config.history_turns, world
    )
    usage = UsageLimiter(settings.database_path, lambda: config.usage_limits, clock)
    closers.append(usage.close)
    own_keys = OwnKeys(own_llm_service, config, activity, speech)
    admissions = Admissions(usage, activity, own_keys)
    calls = Calls(
        settings, engine, admissions, own_keys, lambda: config.usage_limits, speech, clock, store
    )
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
        admissions=admissions,
        accounts=Accounts(store, clock, memories, calls, settings.secret_key),
        identity_providers=identity_providers,
        activity=activity,
        config=config,
        prices=prices,
        world=world,
        _closers=closers,
    )
