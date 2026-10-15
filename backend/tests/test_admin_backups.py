"""The backups on the admin's dashboard (`/api/admin/backups`): whether they are set up,
how the last ones went, which is under way, and whether something is wrong, all of it
worked out by the backend; and the button that begins one in the server's process, the
same run as `eidolon backup`'s. Driven through the backend's external API with a clock
the tests control and a fake bucket."""

import asyncio
from dataclasses import replace
from datetime import timedelta

import httpx
import pytest

from eidolon.backup import Backups
from eidolon.config import Settings
from tests.conftest import ClientFactory
from tests.fakes import START, FakeClock, FakeIdentityProvider, FakeLLM
from tests.test_activity_records import admin_client
from tests.test_backup import IDENTITY
from tests.test_stand_upload import FakeBucket

BACKUP_ENV = {
    "EIDOLON_BACKUP_S3_ENDPOINT": "http://storage.test",
    "EIDOLON_BACKUP_S3_BUCKET": "backups",
    "EIDOLON_BACKUP_S3_ACCESS_KEY_ID": "key-id",
    "EIDOLON_BACKUP_S3_SECRET_ACCESS_KEY": "secret",
    "EIDOLON_BACKUP_AGE_RECIPIENT": str(IDENTITY.to_public()),
}


@pytest.fixture
def settings(settings: Settings) -> Settings:
    """The tests' settings, where the GitHub user 1001 is an admin."""
    return replace(settings, admins=frozenset({("github", "1001")}))


@pytest.fixture
def backup_env(monkeypatch: pytest.MonkeyPatch) -> pytest.MonkeyPatch:
    """The backups set up, to the fake bucket, with nothing else of them in the
    environment."""
    for name in [
        *BACKUP_ENV,
        "EIDOLON_BACKUP_PING_URL",
        "EIDOLON_BACKUP_S3_REGION",
        "EIDOLON_BACKUP_S3_ADDRESSING",
        "EIDOLON_BACKUP_KEEP_DAYS",
        "EIDOLON_BACKUP_WARN_GB",
    ]:
        monkeypatch.delenv(name, raising=False)
    for name, value in BACKUP_ENV.items():
        monkeypatch.setenv(name, value)
    return monkeypatch


@pytest.fixture
def storage() -> FakeBucket:
    return FakeBucket("backups")


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
async def admin(
    make_client: ClientFactory, github: FakeIdentityProvider, clock: FakeClock, storage: FakeBucket
) -> httpx.AsyncClient:
    client = await admin_client(
        make_client, github, clock, backup_transport=httpx.MockTransport(storage.handle)
    )
    return client


async def status(client: httpx.AsyncClient) -> dict:
    res = await client.get("/api/admin/backups")
    assert res.status_code == 200, res.text
    return res.json()


async def back_up_now(client: httpx.AsyncClient) -> dict:
    """Press the button, and wait for the backup it began to finish: the status then."""
    res = await client.post("/api/admin/backups")
    assert res.status_code == 200, res.text
    assert res.json()["under_way"] is not None
    for _ in range(500):
        now = await status(client)
        if now["under_way"] is None:
            return now
        await asyncio.sleep(0.01)
    raise AssertionError("the backup never finished")


async def test_only_admins_see_the_backups_or_begin_one(
    make_client: ClientFactory, backup_env: pytest.MonkeyPatch, storage: FakeBucket
):
    producer = make_client(FakeLLM(), backup_transport=httpx.MockTransport(storage.handle))
    signed_out = make_client(FakeLLM(), user=None)

    for client in [producer, signed_out]:
        assert (await client.get("/api/admin/backups")).status_code == 404
        assert (await client.post("/api/admin/backups")).status_code == 404
    assert storage.puts == []


async def test_without_any_backup_settings_backups_are_not_set_up_and_that_is_wrong(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch
):
    for name in BACKUP_ENV:
        backup_env.delenv(name)

    board = await status(admin)

    assert board["configured"] is False
    assert board["config_error"] is None
    assert board["problem"] == "unconfigured"
    assert board["keep_days"] is None
    res = await admin.post("/api/admin/backups")
    assert res.status_code == 400
    assert "EIDOLON_BACKUP_S3_ENDPOINT" in res.json()["detail"]


async def test_settings_that_will_not_do_are_wrong_and_say_why(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch, storage: FakeBucket
):
    backup_env.setenv("EIDOLON_BACKUP_KEEP_DAYS", "60")

    board = await status(admin)

    assert board["configured"] is True
    assert "EIDOLON_BACKUP_KEEP_DAYS" in board["config_error"]
    assert board["problem"] == "misconfigured"
    res = await admin.post("/api/admin/backups")
    assert res.status_code == 400
    assert "EIDOLON_BACKUP_KEEP_DAYS" in res.json()["detail"]
    assert storage.puts == []
    assert (await status(admin))["last"] is None  # the button recorded nothing


async def test_backups_set_up_but_never_made_are_wrong(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch
):
    backup_env.setenv("EIDOLON_BACKUP_KEEP_DAYS", "7")
    backup_env.setenv("EIDOLON_BACKUP_WARN_GB", "2.5")

    board = await status(admin)

    assert board["configured"] is True
    assert board["config_error"] is None
    assert (board["keep_days"], board["warn_gb"]) == (7, 2.5)
    assert board["problem"] == "never_succeeded"
    assert (board["under_way"], board["last_success"], board["last"], board["bucket"]) == (
        None, None, None, None
    )


async def test_the_button_backs_up_in_the_background_as_the_admins_run(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch, storage: FakeBucket, settings: Settings
):
    board = await back_up_now(admin)

    (key,) = storage.puts
    assert board["problem"] is None
    success = board["last_success"]
    assert success["source"] == "admin"
    assert success["started_at"] == START.isoformat()
    assert success["key"] == key
    assert success["size"] == len(storage.objects[key][0])
    assert board["last"]["errors"] == []
    assert board["bucket"] == {
        "kept": 1, "total": success["size"], "over_warning": False, "at": START.isoformat()
    }
    backups = Backups(settings.database_path, FakeClock())
    assert [record.source for record in backups.records()] == ["admin"]
    backups.close()


async def test_a_backup_over_26_hours_ago_is_overdue(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch, clock: FakeClock
):
    await back_up_now(admin)

    clock.advance(hours=25)
    assert (await status(admin))["problem"] is None
    clock.advance(hours=2)
    assert (await status(admin))["problem"] == "overdue"


async def test_a_failed_run_after_the_last_success_says_why_and_who_began_it(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch, storage: FakeBucket, clock: FakeClock
):
    await back_up_now(admin)
    clock.advance(hours=1)
    storage.down = True

    board = await back_up_now(admin)

    assert board["last_success"]["started_at"] == START.isoformat()
    last = board["last"]
    assert last["source"] == "admin"
    assert last["started_at"] == (START + timedelta(hours=1)).isoformat()
    assert [error["stage"] for error in last["errors"]] == ["upload", "prune"]
    assert all("503" in error["error"] for error in last["errors"])
    # It could not list the bucket: what is in it is as the last run that could saw it.
    assert board["bucket"]["at"] == START.isoformat()
    assert board["problem"] is None


async def test_a_run_never_finished_is_shown_abandoned(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch, settings: Settings, clock: FakeClock
):
    cron = Backups(settings.database_path, clock)
    cron.start("cron")
    clock.advance(hours=2)
    cron.close()

    board = await back_up_now(admin)

    assert board["last_success"]["source"] == "admin"
    assert board["last"]["source"] == "admin"  # the latest to finish, not the abandoned
    cron = Backups(settings.database_path, clock)
    (_, abandoned) = cron.records()
    cron.close()
    assert abandoned.abandoned
    clock.advance(minutes=1)
    cron = Backups(settings.database_path, clock)
    cron.start("cron")
    cron.close()
    board = await status(admin)
    assert board["under_way"] == {
        "source": "cron", "started_at": (START + timedelta(hours=2, minutes=1)).isoformat()
    }


async def test_a_run_abandoned_last_is_the_last_and_says_so(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch, settings: Settings, clock: FakeClock
):
    cron = Backups(settings.database_path, clock)
    cron.start("cron")
    cron.abandon_unfinished()
    cron.close()

    board = await status(admin)

    assert board["last"]["source"] == "cron"
    assert board["last"]["errors"] == [{"stage": "abandoned", "error": None}]
    assert board["problem"] == "never_succeeded"


async def test_while_a_backup_is_under_way_the_button_answers_conflict(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch, settings: Settings,
    storage: FakeBucket, clock: FakeClock,
):
    cron = Backups(settings.database_path, clock)
    cron.start("cron")
    cron.close()

    board = await status(admin)
    res = await admin.post("/api/admin/backups")

    assert board["under_way"] == {"source": "cron", "started_at": START.isoformat()}
    assert res.status_code == 409
    assert "上一次备份还没结束" in res.json()["detail"]
    assert storage.puts == []


async def test_a_run_begun_over_an_hour_ago_is_not_under_way(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch, settings: Settings, clock: FakeClock
):
    cron = Backups(settings.database_path, clock)
    cron.start("cron")
    cron.close()
    clock.advance(hours=1, seconds=1)

    assert (await status(admin))["under_way"] is None
    assert (await back_up_now(admin))["last_success"]["source"] == "admin"


async def test_backups_over_the_space_warning_are_marked(
    admin: httpx.AsyncClient, backup_env: pytest.MonkeyPatch
):
    backup_env.setenv("EIDOLON_BACKUP_WARN_GB", "0.000000001")

    board = await back_up_now(admin)

    assert board["bucket"]["over_warning"] is True
    assert board["problem"] is None  # only marked, as the run only warns
