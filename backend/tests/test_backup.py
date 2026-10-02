"""Backing the database up (`eidolon backup`, ADR-0012): a consistent copy, checked,
compressed and encrypted to the deployer's age key, put in a private bucket; backups
over 30 days old deleted, save the newest; a ping when all went well. Checked against a
fake bucket that keeps what it is sent, and a fake ping service."""

import gzip
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import httpx
import pyrage
import pytest

from eidolon.backup import BackupSettings, back_up, backup_key
from eidolon.s3 import S3Settings
from eidolon.store import Store
from tests.conftest import Admin
from tests.fakes import START
from tests.test_stand_upload import FakeBucket

IDENTITY = pyrage.x25519.Identity.generate()
PING = "https://ping.test/backup"


class Deployment:
    """The database with a user in it, the private bucket, the ping service, and where
    the temporary files go."""

    def __init__(self, tmp_path: Path) -> None:
        self.database = tmp_path / "eidolon.db"
        store = Store(self.database)
        store.create_user("producer")
        store.close()
        self.storage = FakeBucket("backups")
        self.refuses_puts = False
        self.refuses_deletes = False
        self.pings: list[str] = []
        self.ping_down = False

    def settings(self, ping_url: str | None = PING) -> BackupSettings:
        return BackupSettings(
            S3Settings("http://storage.test", "backups", "key-id", "secret"),
            IDENTITY.to_public(),
            ping_url,
        )

    def keep(self, at: datetime) -> str:
        """A backup made at `at`, already in the bucket."""
        key = backup_key(at)
        self.storage.objects[key] = (b"earlier", {})
        return key

    async def back_up(self, now: datetime = START, ping_url: str | None = PING):
        return await back_up(
            self.database, self.settings(ping_url), now=now, transport=httpx.MockTransport(self._handle)
        )

    def restore(self, key: str, to: Path) -> list[str]:
        """The names of the users in the backup, decrypted with the deployer's key."""
        encrypted, _ = self.storage.objects[key]
        to.write_bytes(gzip.decompress(pyrage.decrypt(encrypted, [IDENTITY])))
        with sqlite3.connect(to) as db:
            assert db.execute("PRAGMA integrity_check").fetchone() == ("ok",)
            names = [name for (name,) in db.execute("SELECT name FROM users")]
        db.close()
        return names

    def _handle(self, request: httpx.Request) -> httpx.Response:
        if request.url.host == "ping.test":
            self.pings.append(str(request.url))
            return httpx.Response(503 if self.ping_down else 200)
        if request.method == "PUT" and self.refuses_puts:
            return httpx.Response(507, text="<Error><Code>InsufficientStorage</Code></Error>")
        if request.method == "DELETE" and self.refuses_deletes:
            return httpx.Response(403, text="<Error><Code>AccessDenied</Code></Error>")
        return self.storage.handle(request)


@pytest.fixture
def deployment(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Deployment:
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(temporary))
    return Deployment(tmp_path)


async def test_the_backup_is_the_database_encrypted_to_the_deployers_key(
    deployment: Deployment, tmp_path: Path
):
    report = await deployment.back_up()

    assert report.exit_code == 0
    assert report.key == "eidolon-20260925T120000Z.db.gz.age"
    assert list(deployment.storage.objects) == [report.key]
    assert deployment.restore(report.key, tmp_path / "restored.db") == ["producer"]
    assert list((tmp_path / "tmp").iterdir()) == []  # the temporary files are gone


async def test_backups_over_30_days_old_are_deleted_and_nothing_else(deployment: Deployment):
    old = deployment.keep(START - timedelta(days=30, minutes=1))
    recent = deployment.keep(START - timedelta(days=29, hours=23))
    deployment.storage.objects["notes.txt"] = (b"the deployer's", {})

    report = await deployment.back_up()

    assert report.exit_code == 0
    assert report.deleted == [old]
    assert report.key is not None
    assert sorted(deployment.storage.objects) == sorted([recent, report.key, "notes.txt"])
    assert report.kept == 2


async def test_when_the_upload_fails_old_backups_are_still_deleted_save_the_newest(
    deployment: Deployment,
):
    oldest = deployment.keep(START - timedelta(days=40))
    newest = deployment.keep(START - timedelta(days=35))
    deployment.refuses_puts = True

    report = await deployment.back_up()

    assert report.exit_code == 3
    assert report.upload_error is not None and "507" in report.upload_error
    assert report.deleted == [oldest]
    assert list(deployment.storage.objects) == [newest]
    assert deployment.pings == []


async def test_a_database_that_cannot_be_copied_whole_is_not_uploaded(deployment: Deployment):
    store = Store(deployment.database)
    for n in range(500):
        store.create_user(f"user {n:03d} " + "x" * 200)
    store.close()
    middle = deployment.database.stat().st_size // 2 // 4096 * 4096
    with deployment.database.open("r+b") as file:  # break a page among the users
        file.seek(middle)
        file.write(b"\xff" * 200)
    old = deployment.keep(START - timedelta(days=31))
    deployment.keep(START - timedelta(days=1))

    report = await deployment.back_up()

    assert report.exit_code == 2
    assert report.export_error is not None
    assert deployment.storage.puts == []
    assert report.deleted == [old]
    assert deployment.pings == []


async def test_old_backups_that_cannot_be_deleted_fail_the_backup_without_a_ping(
    deployment: Deployment,
):
    deployment.keep(START - timedelta(days=31))
    deployment.refuses_deletes = True

    report = await deployment.back_up()

    assert report.exit_code == 4
    assert report.key is not None and report.key in deployment.storage.objects
    assert report.prune_error is not None and "AccessDenied" in report.prune_error
    assert deployment.pings == []


async def test_a_backup_that_went_well_pings_once(deployment: Deployment):
    await deployment.back_up()

    assert deployment.pings == [PING]


async def test_a_ping_that_fails_is_only_a_warning(deployment: Deployment):
    deployment.ping_down = True

    report = await deployment.back_up()

    assert report.exit_code == 0
    assert report.ping_error is not None and "503" in report.ping_error


async def test_without_a_ping_url_there_is_no_ping(deployment: Deployment):
    report = await deployment.back_up(ping_url=None)

    assert report.exit_code == 0
    assert deployment.pings == []


BACKUP_ENV = {
    "EIDOLON_BACKUP_S3_ENDPOINT": "https://account.r2.cloudflarestorage.com",
    "EIDOLON_BACKUP_S3_BUCKET": "eidolon-backups",
    "EIDOLON_BACKUP_S3_ACCESS_KEY_ID": "key-id",
    "EIDOLON_BACKUP_S3_SECRET_ACCESS_KEY": "secret",
    "EIDOLON_BACKUP_AGE_RECIPIENT": str(IDENTITY.to_public()),
}


@pytest.fixture
def backup_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    for name in [*BACKUP_ENV, "EIDOLON_BACKUP_PING_URL", "EIDOLON_BACKUP_S3_REGION"]:
        monkeypatch.delenv(name, raising=False)
    for name, value in BACKUP_ENV.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


def test_settings_come_from_the_environment(backup_env: pytest.MonkeyPatch):
    backup_env.setenv("EIDOLON_BACKUP_PING_URL", PING)

    settings = BackupSettings.from_env()

    assert settings.bucket == S3Settings(
        "https://account.r2.cloudflarestorage.com", "eidolon-backups", "key-id", "secret"
    )
    assert str(settings.recipient) == str(IDENTITY.to_public())
    assert settings.ping_url == PING


@pytest.mark.parametrize(
    "missing", ["EIDOLON_BACKUP_S3_SECRET_ACCESS_KEY", "EIDOLON_BACKUP_AGE_RECIPIENT"]
)
def test_settings_missing_from_the_environment_are_an_error(
    backup_env: pytest.MonkeyPatch, missing: str
):
    backup_env.delenv(missing)

    with pytest.raises(RuntimeError, match=missing):
        BackupSettings.from_env()


def test_a_recipient_that_is_not_an_age_public_key_is_an_error(backup_env: pytest.MonkeyPatch):
    backup_env.setenv("EIDOLON_BACKUP_AGE_RECIPIENT", str(IDENTITY))  # the private key

    with pytest.raises(RuntimeError, match="age1"):
        BackupSettings.from_env()


def test_backing_up_without_the_settings_exits_1(admin: Admin, backup_env: pytest.MonkeyPatch):
    backup_env.delenv("EIDOLON_BACKUP_S3_BUCKET")

    code, _, err = admin.invoke("backup")

    assert code == 1
    assert "EIDOLON_BACKUP_S3_BUCKET" in err
