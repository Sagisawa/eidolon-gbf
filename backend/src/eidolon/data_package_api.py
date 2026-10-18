"""The user's data package over HTTP (GLOSSARY.md「数据包」): exported at
`GET /api/account/data-package?include=…` as a download, imported by posting the zip itself
to the same address. Only the signed-in user's own, never anyone else's, admins' neither
(ADR-0013). Neither is recorded; a failure is logged without anything of the package.

`include` names the categories, comma-separated (`data_package.CATEGORIES`). Refusals carry
a `code` beside the `detail`, for the page to tell them apart: `too_new` (422) for a package
from a newer version, `broken` (422) for anything else wrong with it."""

import logging
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import cast

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.background import BackgroundTask
from starlette.concurrency import run_in_threadpool

from eidolon.affinity import day_of
from eidolon.assembly import Backend
from eidolon.data_package import CATEGORIES, BrokenPackage, Category, TooNew
from eidolon.sessions import UserId

log = logging.getLogger(__name__)

_TOO_NEW = "这个数据包来自更新的版本，请部署者升级后再导入"
_BROKEN = "这不是一个能用的数据包"


def _categories(include: str) -> list[Category]:
    """The categories `include` names; 422 for one there is no such category."""
    names = [name.strip() for name in include.split(",") if name.strip()]
    unknown = [name for name in names if name not in CATEGORIES]
    if unknown:
        raise HTTPException(422, f"没有这一类：{'、'.join(unknown)}")
    return [cast(Category, name) for name in names]


def _temporary_file() -> Path:
    handle, name = tempfile.mkstemp(prefix="eidolon-data-package-", suffix=".zip")
    os.close(handle)
    return Path(name)


def add_data_package_routes(app: FastAPI, backend: Backend) -> None:
    packages, clock = backend.data_packages, backend.clock

    @app.get("/api/account/data-package")
    async def export_data_package(user_id: UserId, include: str = "") -> FileResponse:
        """The user's data package with the categories `include` names, as a download named
        after the day it is in Beijing, as the deployment's days are: written to a temporary
        file first, streamed from it, then deleted."""
        categories = _categories(include)
        path = _temporary_file()
        try:
            await run_in_threadpool(packages.export, user_id, categories, path)
        except Exception:
            path.unlink(missing_ok=True)
            log.error("exporting a data package failed", exc_info=True)
            raise
        return FileResponse(
            path,
            media_type="application/zip",
            filename=f"eidolon-data-package-{day_of(clock()).isoformat()}.zip",  # Beijing's day
            background=BackgroundTask(path.unlink, missing_ok=True),
        )

    @app.post("/api/account/data-package")
    async def import_data_package(request: Request, user_id: UserId, include: str = "") -> dict:
        """Import the package in the request body, the zip itself, into the user's data: the
        categories both `include` names and the package holds. What it added
        (`data_package.Imported`)."""
        categories = _categories(include)
        path = _temporary_file()
        try:
            with path.open("wb") as file:
                async for chunk in request.stream():
                    file.write(chunk)
            imported = await packages.import_(user_id, path, categories)
        except (TooNew, BrokenPackage):
            raise
        except Exception:
            log.error("importing a data package failed", exc_info=True)
            raise
        finally:
            path.unlink(missing_ok=True)
        return asdict(imported)

    @app.exception_handler(TooNew)
    async def too_new(_: Request, e: TooNew) -> JSONResponse:
        log.info("refused a data package from a newer version")
        return JSONResponse({"detail": _TOO_NEW, "code": "too_new"}, status_code=422)

    @app.exception_handler(BrokenPackage)
    async def broken(_: Request, e: BrokenPackage) -> JSONResponse:
        log.info("refused a broken data package: %s", e)
        return JSONResponse({"detail": _BROKEN, "code": "broken"}, status_code=422)
