"""The judge model (GLOSSARY.md「判断模型」): asked typed questions about a state, it answers
each with probabilities, and writes nothing. Retrieval asks it what a turn needs looked up,
and calls ask it how she feels in each segment of a reply; what is asked is theirs, how it
is asked is here.

The deployer chooses one service for the whole deployment (`JUDGE_PROVIDER`): Jev through
any endpoint that serves TypeSafe's System One API, OpenRouter's by default; or Cloudflare's
Clef or Clef-flash on Workers AI, which take the same questions. Neither stands in for the
other when it fails.
"""

import logging
from typing import Any, Protocol

import httpx

from eidolon.config import CloudflareJudgeSettings, JudgeSettings

log = logging.getLogger(__name__)

CLOUDFLARE_API_URL = "https://api.cloudflare.com/client/v4"

_ACCOUNT_ERROR_CODES = {7000, 7003}
"""Cloudflare's codes for a path it cannot route, as with an account id that is wrong."""
_QUOTA_ERROR_CODES = {4006}
"""Cloudflare's code for the day's free allocation of neurons being used up."""

_CHECK_QUESTION = {"type": "noul", "instructions": "这是一条测试消息吗？"}


class JudgeError(RuntimeError):
    pass


class JudgeModel(Protocol):
    async def ask(self, state: dict[str, Any], questions: dict[str, dict]) -> dict[str, Any]:
        """The answer to each of `questions` about `state`, by the question's key, all in
        one request. Raises JudgeError if the model cannot be reached or its answer read."""
        ...

    async def aclose(self) -> None: ...


def _client() -> httpx.AsyncClient:
    return httpx.AsyncClient(timeout=httpx.Timeout(5, connect=3))


def _answers(answers: Any, service: str, res: httpx.Response) -> dict[str, Any]:
    if not isinstance(answers, dict) or not all(isinstance(a, dict) for a in answers.values()):
        raise JudgeError(f"{service} 的返回无法解析（{len(res.text)} 字）")
    return answers


class JevJudge:
    """Jev through TypeSafe's System One endpoint (`/systemone`, which OpenRouter, Vercel AI
    Gateway and TypeSafe itself all serve alike): Jev is an evaluation model, answering
    typed questions about a state with probabilities, and is not served by the Chat
    Completions endpoint."""

    def __init__(
        self, api_key: str, model: str, base_url: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._url = base_url.rstrip("/") + "/systemone"
        self._api_key = api_key
        self._model = model
        self._client = client or _client()

    async def ask(self, state: dict[str, Any], questions: dict[str, dict]) -> dict[str, Any]:
        body = {"model": self._model, "state": state, "questions": questions}
        try:
            res = await self._client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._api_key}"}
            )
        except httpx.HTTPError as e:
            raise JudgeError(f"无法连接 Jev：{e!r}") from e
        if res.status_code >= 400:
            raise JudgeError(f"Jev 返回 {res.status_code}: {res.text[:500]}")
        try:
            answers = res.json()["answers"]
        except (ValueError, KeyError, TypeError) as e:
            raise JudgeError(f"Jev 的返回无法解析（{len(res.text)} 字）") from e
        return _answers(answers, "Jev", res)

    async def aclose(self) -> None:
        await self._client.aclose()


class CloudflareRefused(JudgeError):
    """Workers AI answered with an error: its HTTP status and Cloudflare's error codes."""

    def __init__(self, message: str, status: int, codes: set[int]) -> None:
        super().__init__(message)
        self.status = status
        self.codes = codes


class CloudflareJudge:
    """Cloudflare's Clef or Clef-flash on Workers AI, over its REST API: the questions are
    System One's, but the model is named by its bare name and the answers come wrapped in
    Cloudflare's envelope (`{result, success, errors, messages}`)."""

    def __init__(
        self, api_token: str, account_id: str, model: str, client: httpx.AsyncClient | None = None
    ) -> None:
        self._url = f"{CLOUDFLARE_API_URL}/accounts/{account_id}/ai/run/@cf/cloudflare/{model}"
        self._api_token = api_token
        self._model = model
        self._client = client or _client()

    async def ask(self, state: dict[str, Any], questions: dict[str, dict]) -> dict[str, Any]:
        body = {"model": self._model, "state": state, "questions": questions}
        try:
            res = await self._client.post(
                self._url, json=body, headers={"Authorization": f"Bearer {self._api_token}"}
            )
        except httpx.HTTPError as e:
            raise JudgeError(f"无法连接 Cloudflare Workers AI：{e!r}") from e
        try:
            envelope = res.json()
        except ValueError:
            envelope = None
        if not isinstance(envelope, dict):
            if res.status_code >= 400:
                raise CloudflareRefused(
                    f"Cloudflare Workers AI 返回 {res.status_code}: {res.text[:500]}",
                    res.status_code, set(),
                )
            raise JudgeError(f"Cloudflare Workers AI 的返回无法解析（{len(res.text)} 字）")
        if res.status_code >= 400 or envelope.get("success") is False:
            raise _refused(res.status_code, envelope.get("errors"))
        result = envelope.get("result")
        return _answers(
            result.get("answers") if isinstance(result, dict) else None,
            "Cloudflare Workers AI", res,
        )

    async def check(self) -> None:
        """Tries the token and the account id with the least of requests. Raises
        RuntimeError naming the setting that is wrong if Cloudflare refuses either; only
        warns if it cannot be told, say on a timeout, an outage or the day's free
        allocation used up."""
        try:
            await self.ask({"测试": "启动检查"}, {"check": _CHECK_QUESTION})
        except JudgeError as e:
            if isinstance(e, CloudflareRefused):
                if e.status == 404 or e.codes & _ACCOUNT_ERROR_CODES:
                    raise RuntimeError(
                        f"CLOUDFLARE_ACCOUNT_ID 不对，Cloudflare 找不到这个账号：{e}"
                    ) from None
                if e.status in (401, 403):
                    raise RuntimeError(
                        "CLOUDFLARE_API_TOKEN 无效或缺少 Workers AI 权限（需要 Workers AI 的 Read 和"
                        f" Edit），或者它不属于 CLOUDFLARE_ACCOUNT_ID 这个账号：{e}"
                    ) from None
            log.warning("could not check the Cloudflare judge model; starting anyway: %s", e)

    async def aclose(self) -> None:
        await self._client.aclose()


def _refused(status: int, errors: Any) -> CloudflareRefused:
    """What Workers AI's `errors` say went wrong, in so many words when it is the day's
    free allocation used up."""
    errors = errors if isinstance(errors, list) else []
    codes = {e["code"] for e in errors if isinstance(e, dict) and isinstance(e.get("code"), int)}
    said = str(errors)[:500]
    if codes & _QUOTA_ERROR_CODES or "neurons" in said.lower():
        return CloudflareRefused(
            "Workers AI 每日的免费额度（10,000 neurons）已用完，今天的判断都会失败；"
            f"公开部署请开 Workers Paid：{status} {said}",
            status, codes,
        )
    return CloudflareRefused(f"Cloudflare Workers AI 返回 {status}: {said}", status, codes)


def open_judge(
    settings: JudgeSettings, client: httpx.AsyncClient | None = None
) -> JevJudge | CloudflareJudge:
    """The judge model `settings` choose."""
    if isinstance(settings, CloudflareJudgeSettings):
        return CloudflareJudge(settings.api_token, settings.account_id, settings.model, client)
    return JevJudge(settings.api_key, settings.model, settings.base_url, client)


async def check_judge(
    settings: JudgeSettings | None, client: httpx.AsyncClient | None = None
) -> None:
    """Tries Cloudflare's credentials as the server starts (see `CloudflareJudge.check`);
    Jev is not tried."""
    if not isinstance(settings, CloudflareJudgeSettings):
        return
    judge = CloudflareJudge(settings.api_token, settings.account_id, settings.model, client)
    try:
        await judge.check()
    finally:
        await judge.aclose()
