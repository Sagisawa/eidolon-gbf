"""Backing the database up (`eidolon backup`, ADR-0012), once a day from the host's cron
through `deploy/db-backup.sh`.

The whole database, story corpus and all, is copied as it is at one moment without
stopping the server (`VACUUM INTO`), the copy checked, compressed, and encrypted to the
deployer's age public key, whose private key is kept off the server; then put in a
private S3-compatible bucket, apart from the public one the stands are in, under a name
saying when it was made (`backup_key`). Backups over 30 days old are deleted every time,
even when this one could not be made, save the newest, so the bucket is never emptied;
that is what keeps a deleted user's data in backups no longer than 30 days.

Encrypted with pyrage, the Python binding of rage, a Rust implementation of age: it
comes as wheels for the image's platforms, needs nothing installed beside it, encrypts a
file a chunk at a time, and what it writes the deployer decrypts with `age` or `rage`
alike."""

import gzip
import os
import re
import shutil
import sqlite3
import tempfile
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pyrage

from eidolon.database import connect
from eidolon.s3 import Bucket, S3Error, S3Settings

KEPT = timedelta(days=30)
"""How long a backup is kept; the newest is kept however old it is."""

_NAME = re.compile(r"eidolon-(\d{8}T\d{6}Z)\.db\.gz\.age")
_TIME_FORMAT = "%Y%m%dT%H%M%SZ"

_PING_TIMEOUT = 10
"""Seconds."""

SUCCEEDED, MISCONFIGURED, EXPORT_FAILED, UPLOAD_FAILED, PRUNE_FAILED = range(5)
"""The exit codes of `eidolon backup`: when more than one thing failed, the first of
these that did."""


@dataclass(frozen=True)
class BackupSettings:
    bucket: S3Settings
    recipient: pyrage.x25519.Recipient
    """The deployer's age public key; the private key is not on the server."""
    ping_url: str | None = None
    """Visited after each backup that went well, for a service such as healthchecks.io
    to say when the backups stop."""

    @classmethod
    def from_env(cls) -> "BackupSettings":
        """From `EIDOLON_BACKUP_S3_*`, `EIDOLON_BACKUP_AGE_RECIPIENT` and, if it is set,
        `EIDOLON_BACKUP_PING_URL`."""
        bucket = S3Settings.from_env("EIDOLON_BACKUP_S3_", "备份数据库")
        recipient = (os.environ.get("EIDOLON_BACKUP_AGE_RECIPIENT") or "").strip()
        if not recipient:
            raise RuntimeError("备份数据库需要 age 公钥，环境变量 EIDOLON_BACKUP_AGE_RECIPIENT 未设置")
        try:
            parsed = pyrage.x25519.Recipient.from_str(recipient)
        except pyrage.RecipientError:
            raise RuntimeError(
                "环境变量 EIDOLON_BACKUP_AGE_RECIPIENT 应为 age1 开头的 age 公钥"
                "（age-keygen 输出的 public key，不是 AGE-SECRET-KEY 开头的私钥）"
            ) from None
        return cls(bucket, parsed, (os.environ.get("EIDOLON_BACKUP_PING_URL") or "").strip() or None)


@dataclass
class BackupReport:
    key: str | None = None
    """The backup made this time, if it was."""
    size: int = 0
    """Its bytes, compressed and encrypted."""
    deleted: list[str] = field(default_factory=list)
    """The backups over 30 days old deleted this time."""
    kept: int = 0
    """The backups left in the bucket, this one among them."""
    export_error: str | None = None
    upload_error: str | None = None
    prune_error: str | None = None
    ping_error: str | None = None
    """A ping that failed only warns: the backup was made all the same."""

    @property
    def exit_code(self) -> int:
        if self.export_error is not None:
            return EXPORT_FAILED
        if self.upload_error is not None:
            return UPLOAD_FAILED
        if self.prune_error is not None:
            return PRUNE_FAILED
        return SUCCEEDED


def backup_key(made_at: datetime) -> str:
    """The name in the bucket of the backup made at `made_at`, in UTC."""
    return f"eidolon-{made_at.astimezone(UTC):{_TIME_FORMAT}}.db.gz.age"


async def back_up(
    database: Path,
    settings: BackupSettings,
    *,
    now: datetime,
    transport: httpx.AsyncBaseTransport | None = None,
) -> BackupReport:
    """Back the database at `database` up to the bucket, delete the backups over 30 days
    old, and ping if all went well; what went wrong is in the report, not raised. The
    temporary files are deleted whatever happens."""
    report = BackupReport()
    bucket = Bucket(settings.bucket, transport=transport)
    try:
        with tempfile.TemporaryDirectory(prefix="eidolon-backup-") as work:
            try:
                encrypted = _export(database, Path(work), settings.recipient)
            except _ExportFailed as e:
                report.export_error = str(e)
            else:
                key = backup_key(now)
                try:
                    await bucket.put_file(key, encrypted, "application/octet-stream")
                except S3Error as e:
                    report.upload_error = str(e)
                else:
                    report.key, report.size = key, encrypted.stat().st_size
        try:
            report.kept = await _prune(bucket, now, report.deleted)
        except S3Error as e:
            report.prune_error = str(e)
    finally:
        await bucket.aclose()
    if report.exit_code == SUCCEEDED and settings.ping_url is not None:
        report.ping_error = await _ping(settings.ping_url, transport)
    return report


class _ExportFailed(Exception):
    pass


def _export(database: Path, work: Path, recipient: pyrage.x25519.Recipient) -> Path:
    """The database copied whole into `work`, checked, compressed and encrypted; the path
    of the encrypted file."""
    if not database.is_file():
        raise _ExportFailed(f"找不到数据库 {database}")
    copy = work / "eidolon.db"
    try:
        db = connect(database)
        try:  # one read transaction: the database as it is at one moment
            db.execute("VACUUM INTO ?", (str(copy),))
        finally:
            db.close()
        db = connect(copy)
        try:
            check = [row for (row,) in db.execute("PRAGMA integrity_check")]
        finally:
            db.close()
        if check != ["ok"]:
            raise _ExportFailed(f"导出的副本没有通过完整性检查：{'；'.join(check[:5])}")
        compressed = work / "eidolon.db.gz"
        with copy.open("rb") as source, gzip.open(compressed, "wb") as target:
            shutil.copyfileobj(source, target)
        copy.unlink()
        encrypted = work / "eidolon.db.gz.age"
        pyrage.encrypt_file(str(compressed), str(encrypted), [recipient])
        compressed.unlink()
    except (sqlite3.Error, OSError, pyrage.EncryptError) as e:  # a broken database, a full disk
        raise _ExportFailed(f"导出数据库失败：{e}") from None
    return encrypted


async def _prune(bucket: Bucket, now: datetime, deleted: list[str]) -> int:
    """Delete the backups made over `KEPT` before `now`, save the newest, adding each to
    `deleted` once it is; how many are left. Anything else in the bucket is left alone."""
    made: dict[str, datetime] = {}
    for key in await bucket.keys():
        if match := _NAME.fullmatch(key):
            made[key] = datetime.strptime(match[1], _TIME_FORMAT).replace(tzinfo=UTC)
    newest = max(made, key=made.__getitem__, default=None)
    for key in sorted(made):
        if key != newest and made[key] < now - KEPT:
            await bucket.delete(key)
            deleted.append(key)
    return len(made) - len(deleted)


async def _ping(url: str, transport: httpx.AsyncBaseTransport | None) -> str | None:
    """Why visiting `url` failed, or None if it did not."""
    async with httpx.AsyncClient(transport=transport, timeout=_PING_TIMEOUT) as client:
        try:
            response = await client.get(url)
        except httpx.HTTPError as e:
            return f"访问心跳地址失败：{e!r}"
    if not response.is_success:
        return f"心跳地址返回了 {response.status_code}"
    return None
