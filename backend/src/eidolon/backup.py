"""Backing the database up (`eidolon backup`, ADR-0012), once a day from the host's cron
through `deploy/db-backup.sh`.

The whole database, story corpus and all, is copied as it is at one moment without
stopping the server (`VACUUM INTO`), the copy checked, compressed, and encrypted to the
deployer's age public key, whose private key is kept off the server; then put in a
private S3-compatible bucket, apart from the public one the stands are in, under a name
saying when it was made (`backup_key`). Backups past the retention, 30 days unless the
deployer says less, are deleted every time, even when this one could not be made, save
the newest, so the bucket is never emptied; that is what keeps a deleted user's data in
backups no longer than 30 days. How many are left and how large they are is reported,
with a warning over the size the deployer set.

Each run, the cron's, the deployer's or an admin's in the admin console, is recorded in
the database (`Backups`), and the record of one under way keeps another from beginning.

Encrypted with pyrage, the Python binding of rage, a Rust implementation of age: it
comes as wheels for the image's platforms, needs nothing installed beside it, encrypts a
file a chunk at a time, and what it writes the deployer decrypts with `age` or `rage`
alike."""

import asyncio
import gzip
import math
import os
import re
import shutil
import sqlite3
import tempfile
import threading
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Literal

import httpx
import pyrage

from eidolon.clock import Clock
from eidolon.database import connect
from eidolon.s3 import Bucket, S3Error, S3Settings

MOST_DAYS_KEPT = 30
"""The longest backups may be kept, and how long they are unless the deployer says less:
what the privacy policy promises a deleted user (ADR-0012, revised 2026-10-15). The newest
is kept however old it is."""

_NAME = re.compile(r"eidolon-(\d{8}T\d{6}Z)\.db\.gz\.age")
_TIME_FORMAT = "%Y%m%dT%H%M%SZ"

GB = 1_000_000_000
"""Bytes in a gigabyte, as storage is billed."""

_PING_TIMEOUT = 10
"""Seconds."""

SUCCEEDED, MISCONFIGURED, EXPORT_FAILED, UPLOAD_FAILED, PRUNE_FAILED = range(5)
"""The exit codes of `eidolon backup`: when more than one thing failed, the first of
these that did."""
BUSY = 6
"""The exit code of `eidolon backup` when another backup was under way; 5 is
`deploy/db-backup.sh`'s own, for when it could not run the command at all."""

Source = Literal["cron", "manual", "admin"]
"""Who began a backup run: the host's daily cron, the deployer running
`deploy/db-backup.sh` by hand, or an admin with the admin console's button."""

STALE = timedelta(hours=1)
"""How long after a run began, unfinished, another may begin all the same, its process
taken to have been killed: a backup takes some 3 minutes (2026-10-15)."""

RECORDS_KEPT = timedelta(days=90)
"""How long the record of a run is kept, as activity records are."""


@dataclass(frozen=True)
class BackupSettings:
    bucket: S3Settings
    recipient: pyrage.x25519.Recipient
    """The deployer's age public key; the private key is not on the server."""
    ping_url: str | None = None
    """Visited after each backup that went well, for a service such as healthchecks.io
    to say when the backups stop."""
    keep_days: int = MOST_DAYS_KEPT
    """How many days a backup is kept, 1 to `MOST_DAYS_KEPT`."""
    warn_gb: float | None = None
    """Gigabytes (10⁹ bytes) of backups in the bucket over which each backup warns; None
    for no warning."""

    @classmethod
    def from_env(cls) -> "BackupSettings":
        """From `EIDOLON_BACKUP_S3_*`, `EIDOLON_BACKUP_AGE_RECIPIENT` and, if they are
        set, `EIDOLON_BACKUP_PING_URL`, `EIDOLON_BACKUP_KEEP_DAYS` and
        `EIDOLON_BACKUP_WARN_GB`."""
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
        ping_url = (os.environ.get("EIDOLON_BACKUP_PING_URL") or "").strip() or None
        if ping_url is not None and not ping_url.startswith(("https://", "http://")):
            raise RuntimeError(f"环境变量 EIDOLON_BACKUP_PING_URL 应为 http:// 或 https:// 开头的地址，而不是 {ping_url}")
        days = (os.environ.get("EIDOLON_BACKUP_KEEP_DAYS") or "").strip() or str(MOST_DAYS_KEPT)
        if not re.fullmatch(r"\d+", days) or not 1 <= int(days) <= MOST_DAYS_KEPT:
            raise RuntimeError(
                f"环境变量 EIDOLON_BACKUP_KEEP_DAYS 应为 1 到 {MOST_DAYS_KEPT} 的整数天数，而不是 {days}"
                f"（最长 {MOST_DAYS_KEPT} 天，是隐私政策的承诺：删除的数据最多 {MOST_DAYS_KEPT} 天后从备份里消失）"
            )
        warn = (os.environ.get("EIDOLON_BACKUP_WARN_GB") or "").strip()
        try:
            warn_gb = float(warn) if warn else None
        except ValueError:
            warn_gb = math.nan
        if warn_gb is not None and not (math.isfinite(warn_gb) and warn_gb > 0):
            raise RuntimeError(
                f"环境变量 EIDOLON_BACKUP_WARN_GB 应为正数（单位 GB，可以是小数），而不是 {warn}"
            )
        return cls(bucket, parsed, ping_url, int(days), warn_gb)


@dataclass
class BackupReport:
    key: str | None = None
    """The backup made this time, if it was."""
    size: int = 0
    """Its bytes, compressed and encrypted."""
    deleted: list[str] = field(default_factory=list)
    """The backups past the retention deleted this time."""
    kept: int | None = None
    """The backups left in the bucket, this one among them; None if it could not be
    listed."""
    total: int | None = None
    """Their bytes."""
    space_warning: str | None = None
    """Why the backups left take more space than the deployer would be warned over;
    only a warning, as a ping that failed is."""
    export_error: str | None = None
    upload_error: str | None = None
    prune_error: str | None = None
    ping_error: str | None = None
    """A ping that failed only warns: the backup was made all the same."""
    config_error: str | None = None
    """Why the settings would not do, when a run did nothing for it."""
    busy: bool = False
    """Whether a run did nothing for another being under way."""

    @property
    def exit_code(self) -> int:
        if self.config_error is not None:
            return MISCONFIGURED
        if self.busy:
            return BUSY
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
    """Back the database at `database` up to the bucket, delete the backups past the
    retention, and ping if all went well; what went wrong is in the report, not raised.
    The temporary files are deleted whatever happens."""
    report = BackupReport()
    bucket = Bucket(settings.bucket, transport=transport)
    try:
        with tempfile.TemporaryDirectory(prefix="eidolon-backup-") as work:
            try:
                # In a thread: in the server, its event loop has calls to keep going.
                encrypted = await asyncio.to_thread(
                    _export, database, Path(work), settings.recipient
                )
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
            await _prune(bucket, now - timedelta(days=settings.keep_days), report)
        except S3Error as e:
            report.prune_error = str(e)
        if (
            settings.warn_gb is not None
            and report.total is not None
            and report.total > settings.warn_gb * GB
        ):
            report.space_warning = (
                f"存储桶里的备份共 {report.total / GB:.2f} GB，"
                f"超过了 EIDOLON_BACKUP_WARN_GB 设的 {settings.warn_gb:g} GB"
            )
    finally:
        await bucket.aclose()
    if report.exit_code == SUCCEEDED and settings.ping_url is not None:
        report.ping_error = await _ping(settings.ping_url, transport)
    return report


_SCHEMA = """
-- One row a backup run (`Backups`): when it began, and when it finished, NULL while it is
-- under way, which keeps another from beginning; abandoned if it was taken never to
-- finish. Nothing in it is any user's.
CREATE TABLE IF NOT EXISTS backup_runs (
    id INTEGER PRIMARY KEY,
    source TEXT NOT NULL,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    abandoned INTEGER NOT NULL DEFAULT 0,
    exit_code INTEGER,
    key TEXT,
    size INTEGER,
    kept INTEGER,
    total INTEGER,
    over_warning INTEGER NOT NULL DEFAULT 0,
    config_error TEXT,
    export_error TEXT,
    upload_error TEXT,
    prune_error TEXT
);
"""

_COLUMNS = (
    "source, started_at, finished_at, abandoned, exit_code, key, size, kept, total,"
    " over_warning, config_error, export_error, upload_error, prune_error"
)


@dataclass(frozen=True)
class BackupRecord:
    """A backup run, as the database keeps it."""

    source: Source
    started_at: str
    """ISO 8601, as is `finished_at`."""
    finished_at: str | None
    """None while it is under way."""
    abandoned: bool
    """Whether it was taken never to finish (`Backups.abandon_unfinished`)."""
    exit_code: int | None
    """`eidolon backup`'s; None until it finished, and if it was abandoned."""
    key: str | None
    """The backup it made, if it did, and its bytes."""
    size: int | None
    kept: int | None
    """The backups it left in the bucket, and their bytes; None if it did not list them."""
    total: int | None
    over_warning: bool
    """Whether those took more space than the deployer would be warned over."""
    config_error: str | None
    export_error: str | None
    upload_error: str | None
    prune_error: str | None


class Backups:
    """The backups of the database at `database`, and the record of each run kept in it,
    which lets only one run be under way at a time, whether it is `eidolon backup` in a
    process of its own or the admin console's button in the server's. The lock is in the
    database rather than a lock file: the two processes share it, and on Windows, where
    the server is run in development, there is no `fcntl`."""

    def __init__(
        self,
        database: Path,
        clock: Clock,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._database = database
        self._clock = clock
        self._transport = transport
        self._db = connect(database)
        self._lock = threading.Lock()
        with self._lock, self._db:
            self._db.executescript(_SCHEMA)

    async def run(
        self,
        source: Source,
        settings: Callable[[], BackupSettings] = BackupSettings.from_env,
    ) -> BackupReport:
        """Back the database up as `back_up` does, with the `settings` read now, unless
        they will not do or another run is under way, and record it; a run that did
        nothing for the settings is recorded too, one that did nothing for another is
        not."""
        try:
            loaded = settings()
        except RuntimeError as e:
            report = BackupReport(config_error=str(e))
            self._finish(self._begin(source), report)
            return report
        run = self.start(source)
        if run is None:
            return BackupReport(busy=True)
        try:
            report = await back_up(
                self._database, loaded, now=self._clock(), transport=self._transport
            )
        except BaseException:  # cancelled, as when the server shuts down
            self._abandon("id = ?", (run,))
            raise
        self._finish(run, report)
        return report

    def start(self, source: Source) -> int | None:
        """Record a run begun now, unless another is under way (begun within `STALE` and
        not finished): its id, or None if there was one. Forgets the records older than
        `RECORDS_KEPT`."""
        return self._begin(source, exclusive=True)

    def records(self) -> list[BackupRecord]:
        """Every run recorded, the latest first."""
        with self._lock:
            rows = self._db.execute(
                f"SELECT {_COLUMNS} FROM backup_runs ORDER BY started_at DESC, id DESC"
            ).fetchall()
        return [_record(*row) for row in rows]

    def abandon_unfinished(self) -> int:
        """Take every run not finished never to finish, as after the database is restored
        from a backup, which was made while its own run was under way; how many there
        were."""
        return self._abandon("1", ())

    def close(self) -> None:
        self._db.close()

    def _begin(self, source: Source, *, exclusive: bool = False) -> int | None:
        now = self._clock()
        unless = (
            " WHERE NOT EXISTS (SELECT 1 FROM backup_runs"
            " WHERE finished_at IS NULL AND started_at > :stale)"
        )
        with self._lock, self._db:
            self._db.execute(
                "DELETE FROM backup_runs WHERE started_at < ?",
                ((now - RECORDS_KEPT).isoformat(),),
            )
            # One statement, so that two processes cannot both find none under way.
            begun = self._db.execute(
                "INSERT INTO backup_runs (source, started_at) SELECT :source, :now"
                + (unless if exclusive else ""),
                {"source": source, "now": now.isoformat(), "stale": (now - STALE).isoformat()},
            )
        return begun.lastrowid if begun.rowcount == 1 else None

    def _finish(self, run: int | None, report: BackupReport) -> None:
        with self._lock, self._db:
            self._db.execute(
                "UPDATE backup_runs SET finished_at = ?, exit_code = ?, key = ?, size = ?,"
                " kept = ?, total = ?, over_warning = ?, config_error = ?, export_error = ?,"
                " upload_error = ?, prune_error = ? WHERE id = ?",
                (
                    self._clock().isoformat(), report.exit_code, report.key,
                    report.size if report.key is not None else None, report.kept,
                    report.total, report.space_warning is not None, report.config_error,
                    report.export_error, report.upload_error, report.prune_error, run,
                ),
            )

    def _abandon(self, where: str, values: tuple) -> int:
        with self._lock, self._db:
            abandoned = self._db.execute(
                "UPDATE backup_runs SET finished_at = ?, abandoned = 1"
                f" WHERE finished_at IS NULL AND {where}",
                (self._clock().isoformat(), *values),
            )
        return abandoned.rowcount


def _record(
    source: Source, started_at: str, finished_at: str | None, abandoned: int,
    exit_code: int | None, key: str | None, size: int | None, kept: int | None,
    total: int | None, over_warning: int, *errors: str | None,
) -> BackupRecord:
    return BackupRecord(
        source, started_at, finished_at, bool(abandoned), exit_code, key, size, kept,
        total, bool(over_warning), *errors,
    )


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


async def _prune(bucket: Bucket, before: datetime, report: BackupReport) -> None:
    """Delete the backups made before `before`, save the newest, adding each to the
    report's `deleted` once it is, and keeping its `kept` and `total` to what is left, so
    that what was done before a failure is still reported. Anything else in the bucket is
    left alone."""
    made: dict[str, datetime] = {}
    sizes: dict[str, int] = {}
    for key, listed in (await bucket.objects()).items():
        if match := _NAME.fullmatch(key):
            made[key] = datetime.strptime(match[1], _TIME_FORMAT).replace(tzinfo=UTC)
            sizes[key] = listed.size
    report.kept, report.total = len(made), sum(sizes.values())
    newest = max(made, key=made.__getitem__, default=None)
    for key in sorted(made):
        if key != newest and made[key] < before:
            await bucket.delete(key)
            report.deleted.append(key)
            report.kept -= 1
            report.total -= sizes[key]


async def _ping(url: str, transport: httpx.AsyncBaseTransport | None) -> str | None:
    """Why visiting `url` failed, or None if it did not."""
    async with httpx.AsyncClient(transport=transport, timeout=_PING_TIMEOUT) as client:
        try:
            response = await client.get(url)
        except (httpx.HTTPError, httpx.InvalidURL) as e:
            return f"访问心跳地址失败：{e!r}"
    if not response.is_success:
        return f"心跳地址返回了 {response.status_code}"
    return None
