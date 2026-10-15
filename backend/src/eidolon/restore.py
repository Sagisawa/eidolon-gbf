"""Restoring the database from a backup (`eidolon restore`, ADR-0012 revised 2026-10-15),
run by `deploy/db-restore.sh` in a container of its own while the server is stopped.

The file is a backup the deployer decrypted on their own computer, `.db.gz` as `age -d`
leaves it or `.db` once uncompressed; which, is told by what is in it. It is written
beside the database, in the same volume, and checked there; only then put in its place,
by a rename, so the database is either the old one or the new one, never part of each.
The old database's write-ahead log goes with it: left behind, it would be taken as part
of the new one."""

import gzip
import os
import shutil
import sqlite3
import tempfile
import zlib
from pathlib import Path

from eidolon.backup import Backups
from eidolon.clock import Clock
from eidolon.database import connect

_GZIP = b"\x1f\x8b"
_CORE_TABLES = ["users"]
"""Tables a database of this project has, whatever its version."""


class NotRestored(Exception):
    """Why the database was left as it was."""


def restore(source: Path, database: Path, clock: Clock) -> tuple[int, int]:
    """Put the database in `source` in place of the one at `database`, if it is whole and
    one of this project's, raising NotRestored, the database left alone, if not; how many
    users it has, and how many backup runs it caught under way, taken never to finish."""
    if not source.is_file():
        raise NotRestored(f"找不到文件 {source}")
    database.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".restoring-", suffix=".db", dir=database.parent)
    os.close(fd)
    copy = Path(name)
    try:
        _unpack(source, copy)
        users = _check(copy)
        backups = Backups(copy, clock)
        try:
            abandoned = backups.abandon_unfinished()
        finally:
            backups.close()
        if database.exists():
            shutil.copymode(database, copy)
        os.replace(copy, database)
    except BaseException:
        _remove(copy)
        raise
    _remove(database, only_log=True)
    return users, abandoned


def _unpack(source: Path, to: Path) -> None:
    try:
        with source.open("rb") as file:
            compressed = file.read(len(_GZIP)) == _GZIP
        with (gzip.open if compressed else open)(source, "rb") as file, to.open("wb") as copy:
            shutil.copyfileobj(file, copy)
    except (EOFError, gzip.BadGzipFile, zlib.error) as e:
        raise NotRestored(f"{source} 解压失败，可能没下载完整或者解密出错：{e}") from None
    except OSError as e:  # unreadable, a full disk
        raise NotRestored(f"没能把 {source} 写进数据库所在的目录：{e}") from None


def _check(copy: Path) -> int:
    """How many users the database at `copy` has, if it will do."""
    try:
        db = connect(copy)
        try:
            check = [row for (row,) in db.execute("PRAGMA integrity_check")]
            if check != ["ok"]:
                raise NotRestored(f"文件没有通过完整性检查：{'；'.join(check[:5])}")
            tables = {name for (name,) in db.execute("SELECT name FROM sqlite_master")}
            missing = [table for table in _CORE_TABLES if table not in tables]
            if missing:
                raise NotRestored(
                    f"文件是 SQLite 数据库，但不是本项目的（没有 {'、'.join(missing)} 表）"
                )
            (users,) = db.execute("SELECT count(*) FROM users").fetchone()
        finally:
            db.close()
    except sqlite3.DatabaseError as e:  # not a database, or too broken to check
        raise NotRestored(f"文件不是 SQLite 数据库，或者已经损坏：{e}") from None
    return users


def _remove(database: Path, *, only_log: bool = False) -> None:
    """Delete the database at `database` with its write-ahead log, or only the log."""
    for path in ([] if only_log else [database]) + [
        Path(f"{database}-wal"),
        Path(f"{database}-shm"),
    ]:
        path.unlink(missing_ok=True)
