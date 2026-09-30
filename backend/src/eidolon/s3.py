"""An S3-compatible bucket, as far as uploading the stands needs one (`stand_upload`):
listing what it has, and putting objects. The provider is chosen at deploy time
(Cloudflare R2, Tencent COS, Aliyun OSS, MinIO...), so nothing here is any one
provider's: requests are signed with Signature Version 4, which all of them take, and
the bucket is addressed by path (`https://endpoint/bucket/key`) or, for providers that
only take that, by host (`https://bucket.endpoint/key`)."""

import hashlib
import hmac
import os
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from urllib.parse import parse_qsl, quote
from xml.etree import ElementTree

import httpx

DEFAULT_REGION = "us-east-1"
"""What MinIO expects unless told otherwise, and what R2 takes for its `auto`."""

_TIMEOUT = 60
"""Seconds; a texture is under a megabyte or two."""


class S3Error(RuntimeError):
    """The bucket could not be reached, or refused a request."""


@dataclass(frozen=True)
class S3Settings:
    endpoint: str
    """The S3 API's address, without a trailing slash, e.g.
    `https://<account>.r2.cloudflarestorage.com`."""
    bucket: str
    access_key_id: str
    secret_access_key: str
    region: str = DEFAULT_REGION
    virtual_host: bool = False
    """Address the bucket by host rather than by path (Aliyun OSS takes nothing else)."""

    @classmethod
    def from_env(cls) -> "S3Settings":
        """From `EIDOLON_STAND_S3_*`."""
        names = ("ENDPOINT", "BUCKET", "ACCESS_KEY_ID", "SECRET_ACCESS_KEY")
        missing = [f"EIDOLON_STAND_S3_{name}" for name in names if not os.environ.get(f"EIDOLON_STAND_S3_{name}")]
        if missing:
            raise RuntimeError(f"上传立绘需要存储桶的设置，环境变量 {'、'.join(missing)} 未设置")
        endpoint, bucket, key_id, secret = (os.environ[f"EIDOLON_STAND_S3_{name}"].strip() for name in names)
        endpoint = endpoint.rstrip("/")
        if not endpoint.startswith(("https://", "http://")):
            raise RuntimeError(f"环境变量 EIDOLON_STAND_S3_ENDPOINT 应为 http:// 或 https:// 开头的地址，而不是 {endpoint}")
        addressing = (os.environ.get("EIDOLON_STAND_S3_ADDRESSING") or "path").strip()
        if addressing not in ("path", "virtual"):
            raise RuntimeError(f"环境变量 EIDOLON_STAND_S3_ADDRESSING 应为 path 或 virtual，而不是 {addressing}")
        return cls(
            endpoint,
            bucket,
            key_id,
            secret,
            region=(os.environ.get("EIDOLON_STAND_S3_REGION") or DEFAULT_REGION).strip(),
            virtual_host=addressing == "virtual",
        )


class Bucket:
    def __init__(
        self,
        settings: S3Settings,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        self._settings = settings
        self._clock = clock
        self._client = httpx.AsyncClient(transport=transport, timeout=_TIMEOUT)

    async def etags(self) -> dict[str, str]:
        """Every object in the bucket, and its ETag without the quotes: the MD5 of an
        object put in one piece, as `put` puts them."""
        etags: dict[str, str] = {}
        token: str | None = None
        while True:
            params = {"list-type": "2"} | ({"continuation-token": token} if token else {})
            response = await self._send("GET", self._url("", params))
            root = ElementTree.fromstring(response.content)
            for contents in _children(root, "Contents"):
                key, etag = _text(contents, "Key"), _text(contents, "ETag")
                if key is not None:
                    etags[key] = (etag or "").strip('"').lower()
            token = _text(root, "NextContinuationToken")
            if _text(root, "IsTruncated") != "true" or not token:
                return etags

    async def put(self, key: str, body: bytes, content_type: str, cache_control: str) -> None:
        await self._send(
            "PUT",
            self._url(key),
            {"Content-Type": content_type, "Cache-Control": cache_control},
            body,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    def _url(self, key: str, params: Mapping[str, str] | None = None) -> httpx.URL:
        endpoint = httpx.URL(self._settings.endpoint)
        bucket = self._settings.bucket
        if self._settings.virtual_host:
            url = endpoint.copy_with(host=f"{bucket}.{endpoint.host}", path=f"/{key}")
        else:
            url = endpoint.copy_with(path=f"/{bucket}/{key}" if key else f"/{bucket}")
        return url.copy_with(params=params) if params else url

    async def _send(
        self, method: str, url: httpx.URL, headers: Mapping[str, str] | None = None, body: bytes = b""
    ) -> httpx.Response:
        headers = dict(headers or {})
        settings = self._settings
        headers |= sign(
            method, url, headers, hashlib.sha256(body).hexdigest(),
            key_id=settings.access_key_id, secret=settings.secret_access_key,
            region=settings.region, now=self._clock(),
        )
        try:
            response = await self._client.request(method, url, headers=headers, content=body)
        except httpx.HTTPError as e:
            raise S3Error(f"连不上存储桶 {settings.endpoint}：{e!r}") from None
        if response.is_success:
            return response
        raise S3Error(f"存储桶拒绝了 {method} {url.path}：{response.status_code} {_error_of(response)}")


def sign(
    method: str,
    url: httpx.URL,
    headers: Mapping[str, str],
    payload_hash: str,
    *,
    key_id: str,
    secret: str,
    region: str,
    now: datetime,
) -> dict[str, str]:
    """The headers that sign a request to S3 with Signature Version 4: the request's
    `headers`, the host and these are all signed."""
    amz_date = now.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")
    day = amz_date[:8]
    added = {"x-amz-content-sha256": payload_hash, "x-amz-date": amz_date}
    signed = {name.lower(): " ".join(value.split()) for name, value in headers.items()}
    signed |= {"host": url.netloc.decode("ascii")} | added
    names = sorted(signed)
    canonical_request = "\n".join([
        method,
        quote(url.path, safe="/-_.~"),
        "&".join(
            f"{_encode(name)}={_encode(value)}"
            for name, value in sorted(parse_qsl(url.query.decode("ascii"), keep_blank_values=True))
        ),
        "".join(f"{name}:{signed[name]}\n" for name in names),
        ";".join(names),
        payload_hash,
    ])
    scope = f"{day}/{region}/s3/aws4_request"
    string_to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope, hashlib.sha256(canonical_request.encode()).hexdigest()
    ])
    key = f"AWS4{secret}".encode()
    for part in (day, region, "s3", "aws4_request"):
        key = hmac.new(key, part.encode(), hashlib.sha256).digest()
    signature = hmac.new(key, string_to_sign.encode(), hashlib.sha256).hexdigest()
    return added | {
        "Authorization": f"AWS4-HMAC-SHA256 Credential={key_id}/{scope}, "
        f"SignedHeaders={';'.join(names)}, Signature={signature}"
    }


def _encode(value: str) -> str:
    return quote(value, safe="-_.~")


def _children(element: ElementTree.Element, name: str) -> list[ElementTree.Element]:
    """The element's children called `name`, whatever namespace the provider puts them in."""
    return [child for child in element if _local(child.tag) == name]


def _text(element: ElementTree.Element, name: str) -> str | None:
    found = _children(element, name)
    return found[0].text if found else None


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _error_of(response: httpx.Response) -> str:
    """The code and message of an S3 error, or the start of whatever else came back."""
    try:
        root = ElementTree.fromstring(response.content)
    except ElementTree.ParseError:
        return re.sub(r"\s+", " ", response.text)[:200]
    return " ".join(text for name in ("Code", "Message") if (text := _text(root, name)))
