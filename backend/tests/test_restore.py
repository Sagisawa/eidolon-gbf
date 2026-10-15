"""Restoring the database from a backup (`eidolon restore`, ADR-0012 revised 2026-10-15):
the file the deployer decrypted, compressed or not, checked, put in place of the database
all at once, its old write-ahead log gone, and the backup runs it caught under way taken
never to finish; a file that will not do leaves the database as it was."""

import gzip
import re
import sqlite3
from pathlib import Path

import pyrage
import pytest

from eidolon.backup import Backups
from eidolon.clock import utc_now
from eidolon.config import Settings
from eidolon.store import Store
from tests.conftest import Admin
from tests.test_backup import IDENTITY, Deployment


def names(database: Path) -> list[str]:
    db = sqlite3.connect(database)
    try:
        return [name for (name,) in db.execute("SELECT name FROM users ORDER BY name")]
    finally:
        db.close()


def a_database(path: Path, *users: str) -> Path:
    store = Store(path)
    for name in users:
        store.create_user(name)
    store.close()
    return path


@pytest.fixture
def current(settings: Settings) -> Path:
    """The database in use, with a user of its own."""
    return a_database(settings.database_path, "current")


def files_beside(database: Path) -> list[str]:
    return sorted(path.name for path in database.parent.iterdir())


@pytest.mark.parametrize("compressed", [False, True])
def test_the_database_is_replaced_by_the_one_in_the_file(
    admin: Admin, current: Path, tmp_path: Path, compressed: bool
):
    backup = a_database(tmp_path / "backup.db", "kogane", "mano")
    if compressed:
        backup.with_suffix(".db.gz").write_bytes(gzip.compress(backup.read_bytes()))
        backup = backup.with_suffix(".db.gz")
    before = files_beside(current)

    out = admin.run("restore", str(backup))

    assert names(current) == ["kogane", "mano"]
    assert "2 位用户" in out
    assert files_beside(current) == before  # nothing left over


def test_whether_it_is_compressed_is_told_by_what_is_in_it_not_its_name(
    admin: Admin, current: Path, tmp_path: Path
):
    database = a_database(tmp_path / "backup.db", "mano")
    backup = tmp_path / "eidolon.db"
    backup.write_bytes(gzip.compress(database.read_bytes()))

    admin.run("restore", str(backup))

    assert names(current) == ["mano"]


def test_the_old_write_ahead_log_is_deleted(admin: Admin, current: Path, tmp_path: Path):
    backup = a_database(tmp_path / "backup.db", "mano")
    for suffix in ["-wal", "-shm"]:
        Path(f"{current}{suffix}").write_bytes(b"what the old database had not checkpointed")

    admin.run("restore", str(backup))

    assert not Path(f"{current}-wal").exists()
    assert not Path(f"{current}-shm").exists()
    assert names(current) == ["mano"]


def a_broken_database(path: Path) -> Path:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE users (id TEXT PRIMARY KEY, name TEXT)")
    db.executemany("INSERT INTO users VALUES (?, ?)", [(str(i), "x" * 500) for i in range(500)])
    db.commit()
    db.close()
    data = bytearray(path.read_bytes())
    data[8192:16384] = b"\xff" * 8192  # pages of the table overwritten
    path.write_bytes(bytes(data))
    return path


def a_truncated_gzip(path: Path) -> Path:
    data = gzip.compress(a_database(path.with_suffix(".whole"), "mano").read_bytes())
    path.write_bytes(data[: len(data) // 2])
    return path


def not_sqlite(path: Path) -> Path:
    path.write_text("Public key: age1...\n")
    return path


def without_users(path: Path) -> Path:
    db = sqlite3.connect(path)
    db.execute("CREATE TABLE notes (body TEXT)")
    db.close()
    return path


@pytest.mark.parametrize(
    ("make", "why"),
    [
        (a_broken_database, "完整性检查|不是 SQLite"),
        (a_truncated_gzip, "解压"),
        (not_sqlite, "不是 SQLite"),
        (without_users, "users"),
    ],
)
def test_a_file_that_will_not_do_leaves_the_database_alone(
    admin: Admin, current: Path, tmp_path: Path, make, why: str
):
    backup = make(tmp_path / "backup.db")
    before = files_beside(current)

    err = admin.fails("restore", str(backup))

    assert names(current) == ["current"]
    assert files_beside(current) == before
    assert "没有恢复" in err
    assert re.search(why, err)


def test_a_file_that_is_not_there_leaves_the_database_alone(
    admin: Admin, current: Path, tmp_path: Path
):
    err = admin.fails("restore", str(tmp_path / "eidolon-20261003T034300Z.db"))

    assert "找不到" in err
    assert names(current) == ["current"]


def test_backup_runs_the_file_caught_under_way_are_taken_never_to_finish(
    admin: Admin, current: Path, tmp_path: Path
):
    backup = a_database(tmp_path / "backup.db", "mano")
    backups = Backups(backup, utc_now)
    backups.start("cron")
    backups.close()

    out = admin.run("restore", str(backup))

    backups = Backups(current, utc_now)
    try:
        assert [(r.source, r.abandoned) for r in backups.records()] == [("cron", True)]
        assert backups.status().under_way is None
    finally:
        backups.close()
    assert "1 条" in out


async def test_a_backup_decrypted_with_the_deployers_key_restores(
    admin: Admin, current: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    temporary = tmp_path / "tmp"
    temporary.mkdir()
    monkeypatch.setattr("tempfile.tempdir", str(temporary))
    (tmp_path / "old").mkdir()
    old = Deployment(tmp_path / "old")
    report = await old.run("cron")
    assert report.key is not None
    downloaded = tmp_path / "eidolon.db.gz"
    downloaded.write_bytes(pyrage.decrypt(old.storage.objects[report.key][0], [IDENTITY]))

    admin.run("restore", str(downloaded))

    assert names(current) == ["producer"]
    backups = Backups(current, utc_now)
    try:  # the run that made the backup was under way in it
        assert [(r.source, r.abandoned) for r in backups.records()] == [("cron", True)]
    finally:
        backups.close()
