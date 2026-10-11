"""The live configuration: the settings the server started with (`.env`), overridden by
what admins change in the admin console (ADR-0013). It is the admin console's one way to
read and change the configuration.

The configuration is in items, each a few fields saved and restored together: the chat
and memory models, speech synthesis and recognition, the judge model and its thresholds,
the reranker's thresholds, and the limits (per hour, per call, and the turns each prompt
carries, with whether users must bring their own LLM). Overrides are kept in the database, one row per field, a
key encrypted with a key derived from `EIDOLON_SECRET_KEY` (without it, keys cannot be
changed here, only seen). A change to a service is tried before it is kept, as the chat
model is when the server starts; it then holds for every turn and call that starts after
it, while those under way keep what they started with (see `lease` and
`service_clients.Swappable`). Restoring an item deletes its overrides.

The memory model, unless `.env` sets it apart (`BACKGROUND_LLM_*`) or the admin console
does, is the chat model in effect. The thresholds hold only for the model they were set
for, the judge model's for its family (`judge.judge_family`): they are cleared when the
judge model changes to another, and either is not in effect once `.env` has the server
start on another model.

As the server starts (`start`), every override of a service is tried again. One that
fails falls back to `.env`, kept but marked as failed, so a revoked key cannot keep the
server, or the admin console it is fixed in, from starting. Each item is reported in one
of three states: as `.env` has it, overridden, or overridden but not in effect, on
`.env`'s. What cannot be changed here at all is only shown (`READ_ONLY`).
"""

import asyncio
import base64
import json
import logging
import os
import threading
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, replace
from typing import Any, Literal

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from eidolon.activity import (
    ActivityLog,
    MeteredEmotionJudge,
    MeteredJudge,
    judge_origin,
    llm_origin,
    metered_llm,
)
from eidolon.characters import Character
from eidolon.clock import Clock
from eidolon.config import (
    CLOUDFLARE_JUDGE_MODELS,
    DEFAULT_JEV_BASE_URL,
    CloudflareJudgeSettings,
    JevSettings,
    JudgeSettings,
    LLMSettings,
    Settings,
    SttKey,
    UsageLimits,
)
from eidolon.database import connect
from eidolon.emotion import EmotionJudging, ModelEmotionJudge
from eidolon.judge import (
    JudgeError,
    JudgeModel,
    JudgeThresholds,
    judge_thresholds,
    same_judge_family,
    try_judge_model,
    warn_if_uncalibrated,
)
from eidolon.llm import ChatLLM, LLMError
from eidolon.llm.providers import check_chat_llm
from eidolon.own_keys import DeployerKeys, DeployerLease, KeyCheck, OwnKeyRejected
from eidolon.rerank import DEFAULT_THRESHOLDS, RerankThresholds, thresholds_for
from eidolon.retrieval import ModelRetrievalJudge, Need
from eidolon.service_clients import Lease, ServiceClients, Swappable
from eidolon.store import Message

log = logging.getLogger(__name__)

Status = Literal["env", "overridden", "failed"]
"""As `.env` has it; overridden in the admin console; or overridden, but not in effect:
the override failed its try as the server started, or was set for another model."""

CHAT_LLM = "chat_llm"
MEMORY_LLM = "memory_llm"
TTS = "tts"
STT = "stt"
JUDGE = "judge"
JUDGE_THRESHOLDS = "judge_thresholds"
RERANK = "rerank"
LIMITS = "limits"

LLM_FIELDS = ("protocol", "base_url", "api_key", "model", "max_tokens")

FOR_MODEL = "for_model"
"""Kept beside thresholds: the model they were set for."""

MAX_REASON_LENGTH = 300
"""How much of the service's own error message the admin is shown."""

READ_ONLY: dict[str, str] = {
    "admins": "改错了会把自己锁在门外，被攻破的后台也能借它把别人加成管理者，只能在服务器上改。",
    "secret_key": "后台保存的 key 用它加密，封禁名单也靠它，换了就都解不开、认不出，只能在服务器上改。",
    "oauth": "登录靠它，改错了谁都进不了后台去修。",
    "domain": "改了以后登录回调、Cookie 和 HTTPS 证书都要跟着变，需要重新部署。",
    "webrtc": "通话的连接方式由服务器和防火墙一起决定，需要在服务器上改。",
    "backup": "备份去哪、用什么加密，关系到数据能不能找回，只能在服务器上改。",
    "paths": "数据库和角色配置的位置，进程启动时就定了。",
    "embedding": "换了向量化的服务或模型，所有向量都要重新计算（eidolon reembed），不能在运行中切换。",
}
"""What the admin console only shows, and why it cannot change it."""

_SCHEMA = """
-- One row per setting the admin console overrides, named `<item>.<field>`. `value` is
-- JSON, or for a key its Fernet token, of which `last4` is what is ever shown again.
CREATE TABLE IF NOT EXISTS config_overrides (
    name TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    last4 TEXT,
    updated_at TEXT NOT NULL
);
"""


class ConfigRejected(Exception):
    """Trying the change failed, saying why; nothing was saved."""


class ConfigInvalid(Exception):
    """The change is not one the item takes, saying why; nothing was saved."""


class KeysReadOnly(Exception):
    """The deployment has no `EIDOLON_SECRET_KEY` to encrypt keys with."""

    def __init__(self) -> None:
        super().__init__("这个部署没有设置 EIDOLON_SECRET_KEY，key 只能在 .env 里修改")


class Unavailable(Exception):
    """The item is not configured in `.env`, so there is nothing to change here."""


Values = dict[str, Any]


@dataclass(frozen=True)
class _Row:
    value: str
    last4: str | None


class _Unreadable(Exception):
    """An override that can no longer be read back."""


class _Item:
    """One item of the configuration: its fields, `.env`'s values for them, how a change
    is tried and how it is put into effect. `stored` fields are kept beside the others
    but never changed by the admin directly."""

    name: str
    fields: tuple[str, ...]
    secrets: frozenset[str] = frozenset()
    stored: tuple[str, ...] = ()
    unavailable_reason: str = ""

    def __init__(self, config: "LiveConfig") -> None:
        self.c = config

    def available(self) -> bool:
        return True

    def env(self) -> Values:
        raise NotImplementedError

    def bound_model(self) -> str | None:
        """The model the item's values hold for, if they hold for one only."""
        return None

    def candidate(self, current: Values, change: Values) -> Values:
        """The values the change makes of those in effect; a key left out stays."""
        return current | change

    async def tried(self, values: Values) -> tuple[Values, Any]:
        """Try `values`, raising ConfigRejected saying why they do not work; the values
        as kept (with what the try found out) and whatever `apply` is to put in effect."""
        return values, None

    async def apply(self, values: Values, prepared: Any = None) -> None:
        """Put `values` in effect for whatever starts from now on."""

    async def retry(self, values: Values) -> Values:
        """Try the override in effect again as the server starts; raises ConfigRejected."""
        return values

    def shown(self, values: Values) -> Values:
        """`values` as the admin console shows them: of a key, its last 4 characters."""
        shown: Values = {}
        for field in self.fields + self.stored:
            if field == FOR_MODEL or field not in values:
                continue
            if field in self.secrets:
                key = values[field]
                shown[f"{field}_last4"] = key[-4:] if key else None
            else:
                shown[field] = values[field]
        return shown


class _LLMItem(_Item):
    fields = LLM_FIELDS
    secrets = frozenset({"api_key"})

    def swappable(self) -> Swappable[ChatLLM, LLMSettings]:
        raise NotImplementedError

    def make(self, settings: LLMSettings) -> ChatLLM:
        raise NotImplementedError

    async def tried(self, values: Values) -> tuple[Values, Any]:
        client = self.make(_llm(values))
        try:
            await check_chat_llm(client)
        except LLMError as e:
            await client.aclose()
            raise ConfigRejected(str(e)[:MAX_REASON_LENGTH]) from None
        return values, client

    async def apply(self, values: Values, prepared: Any = None) -> None:
        settings = _llm(values)
        await self.swappable().replace(prepared or self.make(settings), settings)

    async def retry(self, values: Values) -> Values:
        try:
            await check_chat_llm(self.swappable().current)
        except LLMError as e:
            raise ConfigRejected(str(e)[:MAX_REASON_LENGTH]) from None
        return values


class _ChatLLM(_LLMItem):
    name = CHAT_LLM

    def env(self) -> Values:
        return _llm_values(self.c.settings.chat_llm)

    def swappable(self) -> Swappable[ChatLLM, LLMSettings]:
        return self.c._chat

    def make(self, settings: LLMSettings) -> ChatLLM:
        return self.c._clients.chat_llm(settings)


class _MemoryLLM(_LLMItem):
    name = MEMORY_LLM

    def env(self) -> Values:
        return _llm_values(self.c.settings.background_llm)

    def swappable(self) -> Swappable[ChatLLM, LLMSettings]:
        return self.c._memory

    def make(self, settings: LLMSettings) -> ChatLLM:
        return self.c._clients.memory_llm(settings)

    async def apply(self, values: Values, prepared: Any = None) -> None:
        if prepared is None and self.c._memory_on_chat():
            values = self.env()  # turns write down on the chat model's client meanwhile
        await super().apply(values, prepared)


class _TTS(_Item):
    name = TTS
    fields = ("api_key", "model")
    secrets = frozenset({"api_key"})

    def env(self) -> Values:
        s = self.c.settings
        return {"api_key": s.fish_audio_api_key, "model": s.fish_audio_model}

    async def tried(self, values: Values) -> tuple[Values, Any]:
        if not values["api_key"]:
            raise ConfigRejected("还没有语音合成的 key，请填写")
        await self.c._check_speech(lambda check: check.check_tts(values["api_key"]))
        return values, None

    async def retry(self, values: Values) -> Values:
        return (await self.tried(values))[0]


STT_KEY_FIELDS = {"soniox": "soniox_api_key", "bailian": "dashscope_api_key"}


class _STT(_Item):
    name = STT
    fields = ("provider", "soniox_api_key", "dashscope_api_key")
    secrets = frozenset({"soniox_api_key", "dashscope_api_key"})
    stored = ("region",)

    def env(self) -> Values:
        s = self.c.settings
        return {
            "provider": s.stt_provider,
            "soniox_api_key": s.soniox_api_key,
            "dashscope_api_key": s.dashscope_api_key,
            "region": s.dashscope_region,
        }

    async def tried(self, values: Values) -> tuple[Values, Any]:
        provider = values["provider"]
        api_key = values[STT_KEY_FIELDS[provider]]
        if not api_key:
            raise ConfigRejected("还没有这家语音识别的 key，请填写")
        key = await self.c._check_speech(lambda check: check.check_stt(provider, api_key))
        assert isinstance(key, SttKey)
        region = key.region if provider == "bailian" else values["region"]
        return values | {"region": region}, None

    async def retry(self, values: Values) -> Values:
        return (await self.tried(values))[0]


class _Judge(_Item):
    name = JUDGE
    fields = ("provider", "api_key", "model", "account_id", "emotion_timeout")
    secrets = frozenset({"api_key"})
    unavailable_reason = (
        ".env 里没有配置判断模型，检索、记忆和通话中的情绪判断在启动时就关掉了；"
        "要启用，请在 .env 里配置后重启"
    )

    def available(self) -> bool:
        return self.c.settings.judge is not None

    def env(self) -> Values:
        judge = self.c.settings.judge
        timeout = self.c.settings.emotion.timeout
        if isinstance(judge, CloudflareJudgeSettings):
            return {"provider": "cloudflare", "api_key": judge.api_token, "model": judge.model,
                    "account_id": judge.account_id, "emotion_timeout": timeout}
        assert judge is not None
        return {"provider": "jev", "api_key": judge.api_key, "model": judge.model,
                "account_id": None, "emotion_timeout": timeout}

    def candidate(self, current: Values, change: Values) -> Values:
        env = self.env()
        values = current | change
        provider = values["provider"]
        if provider != current["provider"]:
            # Another service's key and account cannot be the one in effect.
            for field in ("api_key", "account_id"):
                if field not in change:
                    values[field] = env[field] if env["provider"] == provider else None
            if "api_key" not in change and values["api_key"] is None:
                raise ConfigInvalid("换了判断模型的服务，需要填写它的 key")
        if provider == "cloudflare":
            if not values["account_id"]:
                raise ConfigInvalid("Cloudflare 需要填写账号 ID（account_id）")
            if values["model"] not in CLOUDFLARE_JUDGE_MODELS:
                raise ConfigInvalid(
                    f"Cloudflare 的判断模型只能是 {'、'.join(CLOUDFLARE_JUDGE_MODELS)}"
                )
        else:
            values["account_id"] = None
        return values

    async def tried(self, values: Values) -> tuple[Values, Any]:
        model = self.c._clients.judge_model(self.c._judge_settings(values))
        try:
            await try_judge_model(model)
        except JudgeError as e:
            await model.aclose()
            raise ConfigRejected(str(e)[:MAX_REASON_LENGTH]) from None
        return values, model

    async def apply(self, values: Values, prepared: Any = None) -> None:
        if self.c._judge is not None:
            settings = self.c._judge_settings(values)
            await self.c._judge.replace(
                prepared or self.c._clients.judge_model(settings), settings
            )
        elif prepared is not None:
            await prepared.aclose()

    async def retry(self, values: Values) -> Values:
        if self.c._judge is not None:
            try:
                await try_judge_model(self.c._judge.current)
            except JudgeError as e:
                raise ConfigRejected(str(e)[:MAX_REASON_LENGTH]) from None
        return values


class _JudgeThresholds(_Item):
    name = JUDGE_THRESHOLDS
    fields = ("recall", "emotion")
    stored = (FOR_MODEL,)
    unavailable_reason = _Judge.unavailable_reason

    def available(self) -> bool:
        return self.c.settings.judge is not None

    def env(self) -> Values:
        thresholds = judge_thresholds(self.c.judge_settings, self.c.settings.emotion)
        return {"recall": thresholds.recall, "emotion": thresholds.emotion}

    def bound_model(self) -> str | None:
        return self.c.effective(JUDGE)["model"]


class _Rerank(_Item):
    name = RERANK
    fields = ("references", "memories")
    stored = (FOR_MODEL,)
    unavailable_reason = ".env 里没有配置重排（SILICONFLOW_API_KEY），检索和记忆在启动时就关掉了"

    def available(self) -> bool:
        return self.c.settings.rerank is not None

    def env(self) -> Values:
        rerank = self.c.settings.rerank
        assert rerank is not None
        return asdict(thresholds_for(rerank))

    def bound_model(self) -> str | None:
        rerank = self.c.settings.rerank
        return rerank.model if rerank else None


LIMIT_LABELS = {
    "turns_per_hour": "每小时回合数",
    "calls_per_hour": "每小时通话次数",
    "call_minutes": "单次通话的时长上限（分钟）",
    "turns_per_call": "单次通话的回合上限",
    "history_turns": "带上的历史回合数",
}
"""The limits, as the admin console names them; each a whole number, 0 for no limit."""

OWN_LLM_REQUIRED = "own_llm_required"
"""Beside the limits: whether users must bring their own LLM (GLOSSARY.md「必须自带 LLM」)."""


class _Limits(_Item):
    """The limits per hour, a call's own limits and the turns each prompt carries, as
    `.env` takes them (0 for none), and whether users must bring their own LLM; not tried."""

    name = LIMITS
    fields = (*LIMIT_LABELS, OWN_LLM_REQUIRED)

    def env(self) -> Values:
        limits = self.c.settings.usage_limits
        return {
            "turns_per_hour": limits.turns_per_hour or 0,
            "calls_per_hour": limits.calls_per_hour or 0,
            "call_minutes": limits.call_minutes or 0,
            "turns_per_call": limits.turns_per_call or 0,
            "history_turns": self.c.settings.history_turns or 0,
            OWN_LLM_REQUIRED: self.c.settings.own_llm_required,
        }

    def candidate(self, current: Values, change: Values) -> Values:
        for field, value in change.items():
            if field == OWN_LLM_REQUIRED:
                if not isinstance(value, bool):
                    raise ConfigInvalid(f"必须自带 LLM 需要是 true 或 false，而不是 {value!r}")
            elif isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ConfigInvalid(
                    f"{LIMIT_LABELS[field]}需要是非负整数（0 表示不限），而不是 {value!r}"
                )
        return current | change


class LiveConfig:
    """The configuration the backend runs on now, and the deployer's clients made from it."""

    def __init__(
        self,
        settings: Settings,
        clients: ServiceClients,
        clock: Clock,
        *,
        activity: ActivityLog,
        speech: KeyCheck | None = None,
    ) -> None:
        """The chat, memory and judge models are made by `clients`, each question to the
        judge model recorded in `activity`; `speech` tries the keys for speech synthesis
        and recognition."""
        self.settings = settings
        self._clients = clients
        self._clock = clock
        self._speech = speech
        self._activity = activity
        self._cipher = _cipher(settings.secret_key) if settings.secret_key else None
        self._db = connect(settings.database_path)
        self._db_lock = threading.Lock()
        self._changing = asyncio.Lock()
        with self._db_lock, self._db:
            self._db.executescript(_SCHEMA)
            self._rows = {
                name: _Row(value, last4)
                for name, value, last4 in self._db.execute(
                    "SELECT name, value, last4 FROM config_overrides"
                )
            }
        self._items: dict[str, _Item] = {
            item.name: item
            for item in (
                _ChatLLM(self), _MemoryLLM(self), _TTS(self), _STT(self),
                _Judge(self), _JudgeThresholds(self), _Rerank(self), _Limits(self),
            )
        }
        self._failures: dict[str, str] = {}
        """Why an item's override, failing as the server started or unreadable, is not
        in effect."""
        self._overrides: dict[str, Values] = {}
        for item in self._items.values():
            if item.available() and self._overridden(item.name):
                try:
                    self._overrides[item.name] = self._read(item)
                except _Unreadable as e:
                    self._failures[item.name] = str(e)

        chat = self.chat_llm
        self._chat = Swappable(clients.chat_llm(chat), chat)
        memory = settings.background_llm if self._memory_on_chat() else self.memory_llm
        self._memory = Swappable(clients.memory_llm(memory), memory)
        self._judge: Swappable[JudgeModel, JudgeSettings] | None = None
        if (judge := self.judge_settings) is not None:
            self._judge = Swappable(clients.judge_model(judge), judge)
            warn_if_uncalibrated(judge.model)

    @property
    def keys_editable(self) -> bool:
        return self._cipher is not None

    @property
    def chat_llm(self) -> LLMSettings:
        """The deployer's chat model in effect now."""
        return _llm(self.effective(CHAT_LLM))

    @property
    def memory_llm(self) -> LLMSettings:
        """The deployer's memory model in effect now."""
        return _llm(self.effective(MEMORY_LLM))

    @property
    def judge_settings(self) -> JudgeSettings | None:
        """The judge model in effect now; None without one."""
        if self.settings.judge is None:
            return None
        return self._judge_settings(self.effective(JUDGE))

    @property
    def judge_thresholds(self) -> JudgeThresholds:
        """What the judge model in effect now judges by."""
        return self.judge_thresholds_of(self.judge_settings)

    def judge_thresholds_of(self, judge: JudgeSettings | None) -> JudgeThresholds:
        """What the judge model `judge` judges by: its own thresholds, overridden by
        those set in the admin console if they hold for it."""
        thresholds = judge_thresholds(judge, self.settings.emotion)
        item = self._items[JUDGE_THRESHOLDS]
        if judge is None or not self._in_effect(item, judge.model):
            return thresholds
        override = self._overrides[JUDGE_THRESHOLDS]
        return replace(thresholds, **{k: v for k, v in override.items() if k in item.fields})

    @property
    def rerank_thresholds(self) -> RerankThresholds:
        """The reranker's thresholds in effect now."""
        if self.settings.rerank is None:
            return DEFAULT_THRESHOLDS
        return RerankThresholds(**{
            k: v for k, v in self.effective(RERANK).items() if k != FOR_MODEL
        })

    @property
    def usage_limits(self) -> UsageLimits:
        """The limits per hour and each call's own, in effect now; None for no limit."""
        values = self.effective(LIMITS)
        return UsageLimits(
            values["turns_per_hour"] or None,
            values["calls_per_hour"] or None,
            values["call_minutes"] or None,
            values["turns_per_call"] or None,
        )

    @property
    def own_llm_required(self) -> bool:
        """Whether the deployment requires users to bring their own LLM now."""
        return self.effective(LIMITS)[OWN_LLM_REQUIRED]

    @property
    def history_turns(self) -> int | None:
        """How many of the latest turns each prompt carries now; None for all of them."""
        return self.effective(LIMITS)["history_turns"] or None

    def effective(self, name: str) -> Values:
        """The item's values in effect now: `.env`'s, with its overrides if they are."""
        item = self._items[name]
        if name == MEMORY_LLM:
            return self._memory_values()
        values = item.env()
        if self._in_effect(item):
            values |= self._overrides.get(name, {})
        return values

    def lease(self) -> DeployerLease:
        """The deployer's keys for a turn or call starting now, held until it releases
        them. Each model's requests are recorded as service calls to the model it is, and
        the judge model judges by its own thresholds, whatever replaces it meanwhile."""
        chat = self._chat.lease()
        held: list[Lease[Any, Any]] = [chat]
        memory = chat.again() if self._memory_on_chat() else self._memory.lease()
        held.append(memory)
        emotions = None
        if self._judge is not None:
            judge = self._judge.lease()
            held.append(judge)
            emotions = EmotionJudging(
                MeteredEmotionJudge(
                    ModelEmotionJudge(judge.client), self._activity, judge_origin(judge.settings)
                ),
                self.judge_thresholds_of(judge.settings).emotion,
                self.effective(JUDGE)["emotion_timeout"],
            )
        tts = self.effective(TTS)
        keys = DeployerKeys(
            metered_llm(chat.client, self._activity, llm_origin("chat_llm", chat.settings)),
            metered_llm(
                memory.client, self._activity, llm_origin("memory_llm", memory.settings)
            ),
            self._stt_key(), tts["api_key"], tts["model"],
            emotions, hold_memory=lambda: memory.again().release,
        )
        return DeployerLease(keys, lambda: _release(held))

    def retrieval_judge(self) -> "LiveRetrievalJudge | None":
        """The judge model as retrieval asks it, the one in effect at each question, each
        recorded as a service call; None without one."""
        if self._judge is None:
            return None
        return LiveRetrievalJudge(self, self._judge, self._activity)

    async def start(self) -> None:
        """Try every override as the server starts: one that fails falls back to `.env`,
        with a warning. Logs those in effect."""
        for item in self._items.values():
            if item.name in self._failures:  # a key that can no longer be decrypted
                log.warning(
                    "the admin console's override of %s cannot be read, so .env's is used"
                    " until an admin fixes or restores it: %s",
                    item.name, self._failures[item.name],
                )
                continue
            if item.name not in self._overrides:
                continue
            if not self._bound_holds(item):
                log.warning(
                    "the admin console's override of %s was set for model %s, not %s, so"
                    " .env's is used until an admin sets it again",
                    item.name, self._overrides[item.name].get(FOR_MODEL), item.bound_model(),
                )
                continue
            values = self.effective(item.name)
            try:
                kept = await item.retry(values)
            except ConfigRejected as e:
                self._failures[item.name] = str(e)
                await item.apply(self.effective(item.name))
                if item.name == JUDGE:
                    self._judge_changed(values, self.effective(item.name), clear=False)
                log.warning(
                    "the admin console's override of %s failed, so .env's is used until an"
                    " admin fixes or restores it: %s",
                    item.name, e,
                )
                continue
            if kept != values:  # what the try found out, as a key's region
                self._overrides[item.name] |= {k: kept[k] for k in item.stored}
        in_effect = [
            name for name in sorted(self._rows)
            if self._in_effect(self._items[name.split(".")[0]])
            and not name.endswith(f".{FOR_MODEL}")
        ]
        if in_effect:
            log.info(
                "config overrides in effect, set in the admin console over .env: %s",
                ", ".join(in_effect),
            )

    def describe(self) -> dict[str, Any]:
        """What the admin console shows: for each item, `.env`'s value, the one in effect,
        the override if any and its status. Of a key, only its last 4 characters."""
        described: dict[str, Any] = {"keys_editable": self.keys_editable}
        for name, item in self._items.items():
            if not item.available():
                described[name] = {"unavailable": item.unavailable_reason}
                continue
            override = self._overrides.get(name)
            failure = self._failures.get(name)
            if override is not None and failure is None and not self._bound_holds(item):
                failure = (
                    f"这项覆盖是为 {override.get(FOR_MODEL)} 设的，现在用的是"
                    f" {item.bound_model()}，所以没有生效"
                )
            status: Status = "failed" if failure else "env" if override is None else "overridden"
            entry = {
                "status": status,
                "env": item.shown(item.env()),
                "effective": item.shown(self.effective(name)),
                "override": item.shown(override) if override else None,
                "failure": failure,
            }
            if name == MEMORY_LLM:
                entry["follows_chat"] = self._memory_follows()
            if item.bound_model() is not None:
                entry["model"] = item.bound_model()
            described[name] = entry
        described["read_only"] = self._read_only()
        return described

    async def save(self, name: str, change: Values) -> None:
        """Try the item `change` makes and, if it works, keep it and run every turn and
        call from now on on it. Raises KeysReadOnly for a key without
        `EIDOLON_SECRET_KEY`, ConfigInvalid or ConfigRejected saying why it was not kept,
        Unavailable for an item `.env` does not configure."""
        item = self._items[name]
        if not item.available():
            raise Unavailable(item.unavailable_reason)
        if self._cipher is None and any(f in item.secrets for f in change):
            raise KeysReadOnly()
        async with self._changing:
            current = self.effective(name)
            values = item.candidate(current, change)
            _check_ranges(item, values)
            values, prepared = await item.tried(values)
            if item.bound_model() is not None:
                values[FOR_MODEL] = item.bound_model()
            self._write(item, values, keep={f for f in item.secrets if f not in change})
            self._failures.pop(name, None)
            await item.apply(values, prepared)
            self._changed(name, current, values)

    async def restore(self, name: str) -> None:
        """Delete the item's overrides, so that `.env`'s holds from now on."""
        item = self._items[name]
        if not item.available():
            raise Unavailable(item.unavailable_reason)
        async with self._changing:
            before = self.effective(name)
            self._delete(name)
            after = self.effective(name)
            if after != before:
                await item.apply(after)
            self._changed(name, before, after)

    def _changed(self, name: str, before: dict[str, Any], after: dict[str, Any]) -> None:
        """Item `name` went from `before` to `after`."""
        if name == JUDGE:
            self._judge_changed(before, after, clear=True)

    def _judge_changed(self, before: Values, after: Values, *, clear: bool) -> None:
        """The judge model went from `before`'s to `after`'s: a model not calibrated is
        warned of, and with `clear`, thresholds that no longer hold for it go."""
        if after["model"] == before["model"]:
            return
        warn_if_uncalibrated(after["model"])
        if clear and not same_judge_family(before["model"], after["model"]):
            self._delete(JUDGE_THRESHOLDS)

    async def aclose(self) -> None:
        await self._chat.aclose()
        await self._memory.aclose()
        if self._judge is not None:
            await self._judge.aclose()
        with self._db_lock:
            self._db.close()

    def _judge_settings(self, values: Values) -> JudgeSettings:
        if values["provider"] == "cloudflare":
            return CloudflareJudgeSettings(values["api_key"], values["account_id"], values["model"])
        env = self.settings.judge
        base_url = env.base_url if isinstance(env, JevSettings) else DEFAULT_JEV_BASE_URL
        return JevSettings(values["api_key"], values["model"], base_url)

    def _memory_follows(self) -> bool:
        """Whether the memory model is the chat model in effect: `.env` sets it apart in
        no way, and neither does the admin console."""
        follows = self.settings.background_llm == self.settings.chat_llm
        return follows and not self._in_effect(self._items[MEMORY_LLM])

    def _memory_values(self) -> Values:
        if self._memory_follows():
            return self.effective(CHAT_LLM)
        item = self._items[MEMORY_LLM]
        values = item.env()
        if self._in_effect(item):
            values |= self._overrides[MEMORY_LLM]
        return values

    def _memory_on_chat(self) -> bool:
        """Whether turns write down memories with the chat model's client: the memory
        model follows the chat model, which the admin console changed."""
        return self._memory_follows() and self.chat_llm != self.settings.chat_llm

    def _stt_key(self) -> SttKey | None:
        values = self.effective(STT)
        api_key = values[STT_KEY_FIELDS[values["provider"]]]
        if not api_key:
            return None
        region = values["region"] if values["provider"] == "bailian" else None
        return SttKey(values["provider"], api_key, region)

    async def _check_speech(self, check: Callable[[KeyCheck], Any]) -> Any:
        if self._speech is None:
            raise ConfigRejected("这个部署没有语音服务")
        try:
            return await check(self._speech)
        except OwnKeyRejected as e:
            raise ConfigRejected(str(e)[:MAX_REASON_LENGTH]) from None

    def _in_effect(self, item: _Item, model: str | None = None) -> bool:
        return (
            item.name in self._overrides
            and item.name not in self._failures
            and self._bound_holds(item, model)
        )

    def _bound_holds(self, item: _Item, model: str | None = None) -> bool:
        """Whether the item's overrides were set for `model`, by default the model in
        effect, if they go with one."""
        bound = item.bound_model() if model is None else model
        if bound is None:
            return True
        set_for = self._overrides.get(item.name, {}).get(FOR_MODEL)
        if item.name == JUDGE_THRESHOLDS:
            return set_for is not None and same_judge_family(set_for, bound)
        return set_for == bound

    def _overridden(self, name: str) -> bool:
        return any(row.startswith(f"{name}.") for row in self._rows)

    def _read(self, item: _Item) -> Values:
        """The item's overrides; raises _Unreadable if a key can no longer be decrypted."""
        values: Values = {}
        for field in item.fields + item.stored:
            row = self._rows.get(f"{item.name}.{field}")
            if row is None:
                continue
            if field in item.secrets:
                if self._cipher is None:
                    raise _Unreadable("没有设置 EIDOLON_SECRET_KEY，后台保存的 key 无法解密")
                try:
                    values[field] = self._cipher.decrypt(row.value.encode()).decode()
                except InvalidToken:
                    raise _Unreadable(
                        "后台保存的 key 无法解密（EIDOLON_SECRET_KEY 改过），请重新填写"
                    ) from None
            else:
                values[field] = json.loads(row.value)
        return values

    def _write(self, item: _Item, values: Values, *, keep: set[str]) -> None:
        """Keep as the item's overrides every field of `values` that differs from
        `.env`'s; a key kept as it was (in `keep`) is not encrypted again."""
        env = item.env()
        now = self._clock().isoformat()
        rows: dict[str, _Row | None] = {}
        for field in item.fields + item.stored:
            name, value = f"{item.name}.{field}", values.get(field)
            if field == FOR_MODEL:
                continue
            if value == env.get(field):
                rows[name] = None
            elif field in item.secrets:
                if field in keep and name in self._rows:
                    continue
                if self._cipher is None:
                    raise KeysReadOnly()
                assert isinstance(value, str)
                rows[name] = _Row(self._cipher.encrypt(value.encode()).decode(), value[-4:])
            else:
                rows[name] = _Row(json.dumps(value), None)
        if FOR_MODEL in item.stored:
            kept = any(r is not None for r in rows.values())
            rows[f"{item.name}.{FOR_MODEL}"] = (
                _Row(json.dumps(values[FOR_MODEL]), None) if kept else None
            )
        with self._db_lock, self._db:
            for name, row in rows.items():
                if row is None:
                    self._db.execute("DELETE FROM config_overrides WHERE name = ?", (name,))
                else:
                    self._db.execute(
                        "INSERT INTO config_overrides (name, value, last4, updated_at)"
                        " VALUES (?, ?, ?, ?) ON CONFLICT (name) DO UPDATE SET"
                        " value = excluded.value, last4 = excluded.last4,"
                        " updated_at = excluded.updated_at",
                        (name, row.value, row.last4, now),
                    )
        for name, row in rows.items():
            if row is None:
                self._rows.pop(name, None)
            else:
                self._rows[name] = row
        if self._overridden(item.name):
            self._overrides[item.name] = self._read(item)
        else:
            self._overrides.pop(item.name, None)

    def _delete(self, name: str) -> None:
        with self._db_lock, self._db:
            self._db.execute("DELETE FROM config_overrides WHERE name LIKE ?", (f"{name}.%",))
        self._rows = {n: r for n, r in self._rows.items() if not n.startswith(f"{name}.")}
        self._overrides.pop(name, None)
        self._failures.pop(name, None)

    def _read_only(self) -> list[dict[str, Any]]:
        """What is only shown, with why: never a key, only whether it is set."""
        s = self.settings
        turn = s.turn.urls if s.turn else []
        ice = [u for server in s.ice_servers for u in _urls(server["urls"])]
        embedding = (
            f"{s.embedding.provider} · {s.embedding.model}" if s.embedding else None
        )
        values: dict[str, Any] = {
            "admins": sorted(f"{p}:{subject}" for p, subject in s.admins),
            "secret_key": s.secret_key is not None,
            "oauth": [name for name, o in (("github", s.github), ("google", s.google)) if o],
            "domain": s.domain,
            "webrtc": {"ice_servers": ice, "turn": turn},
            "backup": _backup_shown(),
            "paths": {"database": str(s.database_path), "characters": str(s.characters_path)},
            "embedding": embedding,
        }
        return [{"name": k, "value": values[k], "why": why} for k, why in READ_ONLY.items()]


class LiveRetrievalJudge:
    """The judge model as retrieval asks it: at each question, the one in effect then,
    held while it answers, by its own thresholds, recorded as the model it is."""

    def __init__(
        self,
        config: LiveConfig,
        judge: Swappable[JudgeModel, JudgeSettings],
        activity: ActivityLog,
    ) -> None:
        self._config = config
        self._judge = judge
        self._activity = activity

    async def judge(self, character: Character, history: Sequence[Message], text: str) -> Need:
        lease = self._judge.lease()
        try:
            judge = MeteredJudge(
                ModelRetrievalJudge(lease.client, self._config.judge_thresholds_of(lease.settings)),
                self._activity,
                judge_origin(lease.settings),
            )
            return await judge.judge(character, history, text)
        finally:
            lease.release()


def _check_ranges(item: _Item, values: Values) -> None:
    """Thresholds are probabilities and scores, from 0 to 1."""
    if isinstance(item, _JudgeThresholds | _Rerank):
        for field in item.fields:
            if not 0 <= values[field] <= 1:
                raise ConfigInvalid("阈值需要在 0 到 1 之间")


def _release(held: list[Lease[Any, Any]]) -> None:
    for lease in held:
        lease.release()


def _urls(urls: str | list[str]) -> list[str]:
    return [urls] if isinstance(urls, str) else list(urls)


def _backup_shown() -> str | None:
    """Which bucket backups go to, if they are configured (`backup`); never its keys."""
    return (os.environ.get("EIDOLON_BACKUP_S3_BUCKET") or "").strip() or None


def _llm_values(settings: LLMSettings) -> Values:
    return {
        "protocol": settings.protocol,
        "base_url": settings.base_url,
        "api_key": settings.api_key,
        "model": settings.model,
        "max_tokens": settings.max_tokens,
    }


def _llm(values: Values) -> LLMSettings:
    return LLMSettings(
        values["base_url"], values["api_key"], values["model"], values["protocol"],
        values["max_tokens"],
    )


def _cipher(secret_key: str) -> Fernet:
    """The cipher for the deployer's keys kept as overrides, derived from the deployment's
    secret key apart from the one for the ban list."""
    derived = HKDF(
        algorithm=hashes.SHA256(), length=32, salt=None, info=b"eidolon config overrides"
    ).derive(secret_key.encode())
    return Fernet(base64.urlsafe_b64encode(derived))
