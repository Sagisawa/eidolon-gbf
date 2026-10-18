"""Data packages (GLOSSARY.md「数据包」): a user exports their data as a zip, and imports
it into this deployment or another, under this account or another. Checked only through
the API: what a package holds by unzipping it, what an import did by the read endpoints."""

import io
import json
import zipfile
from collections.abc import Callable
from dataclasses import replace
from datetime import datetime
from pathlib import Path

import httpx

from eidolon.config import Settings
from tests.conftest import ClientFactory
from tests.fakes import (
    FakeBackgroundLLM,
    FakeEmbedder,
    FakeJudge,
    FakeLLM,
    FakeReranker,
    context_of,
)
from tests.test_memories import KYOTO, OSAKA, TOKYO, superseding
from tests.test_memory_management import memories
from tests.test_shared_memory import CAT, REPLY, memories_section, memorized, turn
from tests.test_text_turn import start_conversation

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


def remembering(
    make_client: ClientFactory, *answers: str | Callable[[str], str], **options: object
) -> httpx.AsyncClient:
    """A client with memory on, whose background model answers each turn with the next of
    `answers`, and whose reranker finds every memory relevant."""
    return make_client(
        FakeLLM(*[REPLY] * 5), retrieval_judge=FakeJudge(), embedder=FakeEmbedder(),
        reranker=FakeReranker("制作人"), background_llm=FakeBackgroundLLM(*answers), **options,
    )


async def remembered(client: httpx.AsyncClient) -> list[tuple]:
    """The memories page: each memory's text, who it was told to, when, and whether it has
    been superseded, newest first."""
    return [
        (m["text"], m["source_character_id"], m["source_character_name"],
         datetime.fromisoformat(m["created_at"]), m["superseded"])
        for m in await memories(client)
    ]


async def test_memories_move_to_another_deployment_superseded_as_they_were(
    make_client: ClientFactory, settings: Settings, tmp_path: Path
):
    here = remembering(make_client, memorized(OSAKA), superseding(TOKYO, OSAKA), memorized(CAT))
    await turn(here, await start_conversation(here, "mano"), "我住在大阪")
    await turn(here, await start_conversation(here, "kogane"), "我搬到东京了")
    await turn(here, await start_conversation(here, "mano"), "我家的猫叫小白哦")
    there = other_deployment(make_client, settings, tmp_path)

    package = await export(here, "memories")
    _, manifest, data = unzipped(package)
    assert manifest["categories"] == ["memories"]
    assert manifest["counts"] == {"memories": 3}
    osaka, tokyo, cat = data["memories"]
    assert osaka["text"] == OSAKA and tokyo["text"] == TOKYO and cat["text"] == CAT
    assert osaka["superseded_by"] == tokyo["id"]
    assert tokyo["superseded_by"] is None and cat["superseded_by"] is None
    assert (tokyo["source_character_id"], tokyo["source_character_name"]) == ("kogane", "月岡恋鐘")
    assert all(m["conversation"] is None for m in data["memories"])
    assert set(osaka) == {
        "id", "source_character_id", "source_character_name", "conversation", "text",
        "created_at", "superseded_by",
    }
    res = await import_package(there, package, "memories")

    assert res.status_code == 200, res.text
    assert res.json() == {**NOTHING_ELSE, "memories": 3, "profile": False}
    assert await remembered(there) == await remembered(here)
    assert [m[4] for m in await remembered(there)] == [False, False, True]


def memories_package(*memories: dict) -> bytes:
    return package_of(
        {**MANIFEST, "categories": ["memories"], "counts": {"memories": len(memories)}},
        {"memories": list(memories)},
    )


def packaged_memory(id: int, text: str, superseded_by: int | None = None, *,
                    source: tuple[str, str] = ("mano", "櫻木真乃")) -> dict:
    return {
        "id": id, "source_character_id": source[0], "source_character_name": source[1],
        "conversation": None, "text": text, "created_at": f"2026-09-0{id}T08:00:00.000000+00:00",
        "superseded_by": superseded_by,
    }


async def test_a_memory_already_here_is_not_added_again_and_stands_in_for_it(
    make_client: ClientFactory,
):
    client = remembering(make_client, memorized(TOKYO))
    await turn(client, await start_conversation(client, "kogane"), "我搬到东京了")
    package = memories_package(
        packaged_memory(1, OSAKA, superseded_by=2),
        packaged_memory(2, TOKYO, superseded_by=3),  # here, holding: left holding
        packaged_memory(3, KYOTO),
    )

    res = await import_package(client, package, "memories")

    assert res.status_code == 200, res.text
    assert res.json()["memories"] == 2
    listed = await memories(client)
    assert [(m["text"], m["superseded"]) for m in listed] == [
        (KYOTO, False), (OSAKA, True), (TOKYO, False),
    ]
    # Osaka is superseded by Tokyo here: with Tokyo gone, it holds again.
    tokyo = next(m for m in listed if m["text"] == TOKYO)
    assert (await client.delete(f"/api/memories/{tokyo['id']}")).status_code == 204
    assert [(m["text"], m["superseded"]) for m in await memories(client)] == [
        (KYOTO, False), (OSAKA, False),
    ]


async def test_importing_the_same_memories_twice_adds_nothing_the_second_time(
    make_client: ClientFactory, settings: Settings, tmp_path: Path
):
    here = remembering(make_client, memorized(OSAKA), superseding(TOKYO, OSAKA))
    await turn(here, await start_conversation(here, "mano"), "我住在大阪")
    await turn(here, await start_conversation(here, "kogane"), "我搬到东京了")
    there = other_deployment(make_client, settings, tmp_path)
    package = await export(here, "memories")

    assert (await import_package(there, package, "memories")).json()["memories"] == 2
    res = await import_package(there, package, "memories")

    assert res.json() == {**NOTHING_ELSE, "profile": False}
    assert await remembered(there) == await remembered(here)


async def test_memories_told_to_someone_not_here_are_imported_all_the_same(
    make_client: ClientFactory,
):
    client = remembering(make_client)

    res = await import_package(
        client, memories_package(packaged_memory(1, CAT, source=("hazuki", "七草はづき"))),
        "memories",
    )

    assert res.json()["memories"] == 1
    assert [(m["text"], m["source_character_id"], m["source_character_name"])
            for m in await memories(client)] == [(CAT, "hazuki", None)]


async def test_she_recalls_imported_memories_in_her_next_turn(make_client: ClientFactory):
    llm, embedder = FakeLLM(REPLY), FakeEmbedder()
    client = make_client(
        llm, retrieval_judge=FakeJudge(), embedder=embedder, reranker=FakeReranker("猫"),
        background_llm=FakeBackgroundLLM(memorized()),
    )

    await import_package(client, memories_package(packaged_memory(1, CAT)), "memories")

    await memories(client)  # waits for them to be embedded, as her turns do
    assert embedder.documents == [CAT]  # embedded by the server, not when first searched
    await turn(client, await start_conversation(client, "kogane"), "你知道我家的猫吗？")
    assert CAT in memories_section(context_of(llm.prompts[-1]))
    assert embedder.documents == [CAT]


async def test_memories_superseded_by_what_the_package_does_not_hold_are_refused(
    make_client: ClientFactory,
):
    client = remembering(make_client)
    broken = {
        "superseded by no memory": [packaged_memory(1, OSAKA, superseded_by=9)],
        "superseded by itself": [packaged_memory(1, OSAKA, superseded_by=1)],
        "two under one id": [packaged_memory(1, OSAKA), packaged_memory(1, TOKYO)],
    }

    for case, packaged in broken.items():
        res = await import_package(client, memories_package(*packaged), "memories")

        assert res.status_code == 422, case
        assert res.json()["code"] == "broken", case
    assert await memories(client) == []


def _zip(entries: dict[str, str]) -> bytes:
    """A zip of `entries`, in their order, none of them compressed."""
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zipped:
        for name, content in entries.items():
            zipped.writestr(name, content)
    return buffer.getvalue()
