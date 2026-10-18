"""Data packages (GLOSSARY.md「数据包」): a user exports their data as a zip, and imports
it into this deployment or another, under this account or another. Checked only through
the API: what a package holds by unzipping it, what an import did by the read endpoints."""

import io
import json
import zipfile
from dataclasses import replace
from pathlib import Path

import httpx

from eidolon.config import Settings
from tests.conftest import ClientFactory
from tests.fakes import FakeLLM

PROFILE = {
    "form_of_address": "小林",
    "gender": "female",
    "timezone": "Asia/Tokyo",
    "birthday": {"month": 2, "day": 29},
}
EMPTY_PROFILE = {"form_of_address": None, "gender": None, "timezone": None, "birthday": None}
NOTHING_ELSE = {"conversations": 0, "photos": 0, "memories": 0, "skipped": []}


def other_deployment(make_client: ClientFactory, settings: Settings, tmp_path: Path,
                     user: str = "producer") -> httpx.AsyncClient:
    """A client of another deployment: the same characters, a database of its own."""
    return make_client(
        FakeLLM(), user, settings=replace(settings, database_path=tmp_path / "other.db")
    )


async def export(client: httpx.AsyncClient, include: str) -> bytes:
    res = await client.get("/api/account/data-package", params={"include": include})
    assert res.status_code == 200, res.text
    return res.content


async def import_package(client: httpx.AsyncClient, package: bytes, include: str) -> httpx.Response:
    return await client.post(
        "/api/account/data-package",
        params={"include": include},
        content=package,
        headers={"content-type": "application/zip"},
    )


def unzipped(package: bytes) -> tuple[list[zipfile.ZipInfo], dict, dict]:
    """The entries of a package, and its manifest and data read."""
    with zipfile.ZipFile(io.BytesIO(package)) as zipped:
        return (
            zipped.infolist(),
            json.loads(zipped.read("manifest.json")),
            json.loads(zipped.read("data.json")),
        )


def package_of(manifest: dict, data: dict, *, extra: dict[str, str] | None = None) -> bytes:
    """A package made by hand."""
    return _zip(
        {"manifest.json": json.dumps(manifest), "data.json": json.dumps(data), **(extra or {})}
    )


MANIFEST = {
    "format": 1,
    "exported_at": "2026-10-19T08:00:00.000000+00:00",
    "categories": ["profile"],
    "counts": {"profile": 1},
}
PACKAGED_PROFILE = {
    "form_of_address": "小林",
    "gender": "male",
    "timezone": "Asia/Tokyo",
    "birthday_month": 5,
    "birthday_day": 3,
}


async def test_the_producer_profile_moves_to_another_deployment(
    make_client: ClientFactory, settings: Settings, tmp_path: Path
):
    here = make_client(FakeLLM())
    await here.put("/api/profile", json=PROFILE)
    there = other_deployment(make_client, settings, tmp_path)
    await there.put("/api/profile", json={"form_of_address": "P", "gender": "male"})

    res = await here.get("/api/account/data-package", params={"include": "profile"})
    assert res.status_code == 200, res.text
    assert res.headers["content-type"] == "application/zip"
    disposition = res.headers["content-disposition"]
    assert disposition.startswith("attachment")
    assert "eidolon-data-package-" in disposition and disposition.endswith('.zip"')
    entries, manifest, data = unzipped(res.content)
    assert [e.filename for e in entries] == ["manifest.json", "data.json"]
    assert entries[0].compress_type == zipfile.ZIP_STORED
    assert manifest["format"] == 1
    assert manifest["categories"] == ["profile"]
    assert manifest["counts"] == {"profile": 1}
    assert data == {"profile": {
        "form_of_address": "小林", "gender": "female", "timezone": "Asia/Tokyo",
        "birthday_month": 2, "birthday_day": 29,
    }}

    res = await import_package(there, res.content, "profile")

    assert res.status_code == 200, res.text
    assert res.json() == {**NOTHING_ELSE, "profile": True}
    assert (await there.get("/api/profile")).json() == PROFILE


async def test_a_profile_left_unset_in_the_package_clears_the_one_here(
    make_client: ClientFactory, settings: Settings, tmp_path: Path
):
    here = make_client(FakeLLM())
    there = other_deployment(make_client, settings, tmp_path)
    await there.put("/api/profile", json=PROFILE)

    package = await export(here, "profile")
    _, _, data = unzipped(package)
    assert data == {"profile": {
        "form_of_address": None, "gender": None, "timezone": None,
        "birthday_month": None, "birthday_day": None,
    }}
    res = await import_package(there, package, "profile")

    assert res.json()["profile"] is True
    assert (await there.get("/api/profile")).json() == EMPTY_PROFILE


async def test_categories_left_out_are_neither_exported_nor_imported(
    make_client: ClientFactory, settings: Settings, tmp_path: Path
):
    here = make_client(FakeLLM())
    await here.put("/api/profile", json=PROFILE)
    there = other_deployment(make_client, settings, tmp_path)
    await there.put("/api/profile", json={"form_of_address": "P"})

    _, manifest, data = unzipped(await export(here, ""))
    assert manifest["categories"] == [] and manifest["counts"] == {}
    assert data == {}

    res = await import_package(there, await export(here, "profile"), "")
    assert res.status_code == 200, res.text
    assert res.json() == {**NOTHING_ELSE, "profile": False}
    assert (await there.get("/api/profile")).json()["form_of_address"] == "P"


async def test_a_user_exports_only_their_own_profile(make_client: ClientFactory):
    await make_client(FakeLLM(), "friend").put("/api/profile", json=PROFILE)

    _, _, data = unzipped(await export(make_client(FakeLLM()), "profile"))

    assert data["profile"]["form_of_address"] is None


async def test_signing_in_is_needed_to_export_or_import(make_client: ClientFactory):
    stranger = make_client(FakeLLM(), None)

    assert (await stranger.get(
        "/api/account/data-package", params={"include": "profile"}
    )).status_code == 401
    res = await import_package(stranger, package_of(MANIFEST, {"profile": PACKAGED_PROFILE}), "profile")
    assert res.status_code == 401


async def test_a_package_from_a_newer_version_is_refused(make_client: ClientFactory):
    client = make_client(FakeLLM())

    res = await import_package(
        client, package_of({**MANIFEST, "format": 2, "categories": ["albums"]}, {}), "profile"
    )

    assert res.status_code == 422
    assert res.json()["code"] == "too_new"
    assert (await client.get("/api/profile")).json() == EMPTY_PROFILE


async def test_a_broken_package_is_refused_and_nothing_is_imported(make_client: ClientFactory):
    client = make_client(FakeLLM())
    profile = {"profile": PACKAGED_PROFILE}
    broken = {
        "not a zip": b"PK\x03\x04 not really a zip",
        "an entry too many": package_of(MANIFEST, profile, extra={"notes.txt": "hi"}),
        "a manifest not first": _zip(
            {"data.json": json.dumps(profile), "manifest.json": json.dumps(MANIFEST)}
        ),
        "a manifest not JSON": _zip({"manifest.json": "{", "data.json": json.dumps(profile)}),
        "a time not a time": package_of({**MANIFEST, "exported_at": "yesterday"}, profile),
        "a time without its zone": package_of(
            {**MANIFEST, "exported_at": "2026-10-19T08:00:00"}, profile
        ),
        "a day not of the year": package_of(
            MANIFEST, {"profile": {**PACKAGED_PROFILE, "birthday_month": 2, "birthday_day": 30}}
        ),
        "data of a category not listed": package_of({**MANIFEST, "categories": []}, profile),
    }

    for case, package in broken.items():
        res = await import_package(client, package, "profile")

        assert res.status_code == 422, case
        assert res.json()["code"] == "broken", case
    assert (await client.get("/api/profile")).json() == EMPTY_PROFILE


def _zip(entries: dict[str, str]) -> bytes:
    """A zip of `entries`, in their order, none of them compressed."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name, content in entries.items():
            zipped.writestr(name, content)
    return buffer.getvalue()
