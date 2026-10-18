"""Data packages (GLOSSARY.md「数据包」, ADR-0025): a user's own data as a zip they keep,
exported here and imported into this deployment or another, under this account or another.
The format is described for people in `docs/data-package-format.md`.

A package holds `manifest.json` first, stored uncompressed so that a browser can read it
from the start of the file alone; then `data.json`, indented, in English keys; and nothing
else. The manifest says which format the package is in (`FORMAT`), when it was exported,
which categories it holds and how many of each. A deployment imports packages of its own
format and older ones, and refuses newer ones (`TooNew`) rather than drop what it cannot
read. Anything else wrong with a package refuses it as broken (`BrokenPackage`).

Importing writes everything in one transaction of its own, through a connection of its own
to the database, so that a package fails as a whole and leaves nothing behind. Neither
exporting nor importing is recorded: no activity record, nothing an admin sees."""

import json
import zipfile
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Literal, get_args

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationError,
    model_validator,
)

from eidolon.database import connect
from eidolon.producer import (
    MAX_FORM_OF_ADDRESS_LENGTH,
    Birthday,
    Gender,
    ProducerProfile,
    is_day_of_the_year,
)
from eidolon.store import Store, write_profile

FORMAT = 1
"""The newest format this version reads, and the one it exports. Changing the format adds
one to it, and keeps reading the older ones."""

Category = Literal["conversations", "photos", "memories", "profile"]
CATEGORIES: tuple[Category, ...] = get_args(Category)
"""What a package may hold, in the order a manifest lists them. Photos go with the
conversations they were sent in, never without them."""

MANIFEST = "manifest.json"
DATA = "data.json"


class TooNew(Exception):
    """A package in a format newer than this version reads: the deployer should upgrade."""


class BrokenPackage(Exception):
    """Not a package this version can import: not a zip, entries it should not have, or
    JSON not in the format."""


def _stored_time(value: str) -> str:
    """A time as the database writes it (`_written`), from any ISO 8601 time with its zone:
    conversations and events are ordered by their times as text."""
    at = datetime.fromisoformat(value)
    if at.tzinfo is None:
        raise ValueError("a time without its zone")
    return _written(at)


def _written(at: datetime) -> str:
    """`at` as packages and the database write times: UTC, ISO 8601 with microseconds."""
    return at.astimezone(UTC).isoformat(timespec="microseconds")


Time = Annotated[str, AfterValidator(_stored_time)]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class PackagedProfile(_Strict):
    form_of_address: Annotated[str, Field(max_length=MAX_FORM_OF_ADDRESS_LENGTH)] | None
    gender: Gender | None
    timezone: Annotated[str, Field(max_length=100)] | None
    """As kept, even a zone this server does not know: it is passed over for the device's
    (`producer.effective_timezone`)."""
    birthday_month: int | None
    birthday_day: int | None

    @model_validator(mode="after")
    def _birthday(self) -> "PackagedProfile":
        month, day = self.birthday_month, self.birthday_day
        if (month is None) != (day is None):
            raise ValueError("half a birthday")
        if month is not None and day is not None and not is_day_of_the_year(month, day):
            raise ValueError("no such day")
        return self

    @classmethod
    def of(cls, profile: ProducerProfile) -> "PackagedProfile":
        birthday = profile.birthday
        return cls(
            form_of_address=profile.form_of_address,
            gender=profile.gender,
            timezone=profile.timezone,
            birthday_month=birthday and birthday.month,
            birthday_day=birthday and birthday.day,
        )

    def profile(self) -> ProducerProfile:
        birthday = (
            Birthday(self.birthday_month, self.birthday_day)
            if self.birthday_month is not None and self.birthday_day is not None
            else None
        )
        return ProducerProfile(
            self.form_of_address or None, self.gender, self.timezone or None, birthday
        )


class PackageData(_Strict):
    """`data.json`: a key for each category the package holds, none for the others."""

    profile: PackagedProfile | None = None


class Manifest(_Strict):
    format: StrictInt
    exported_at: Time
    categories: list[Category]
    counts: dict[Category, StrictInt]


class _Format(BaseModel):
    """Just the format of a manifest, read before the rest, whose shape it decides."""

    format: StrictInt


@dataclass
class Skipped:
    """Her conversations in a package that were not imported: she is not here."""

    character_name: str
    conversations: int


@dataclass
class Imported:
    """What an import added: only what is new, so importing the same package twice adds
    nothing the second time. `profile` is whether the producer profile was overwritten."""

    conversations: int = 0
    photos: int = 0
    memories: int = 0
    profile: bool = False
    skipped: list[Skipped] = field(default_factory=list)


def chosen(include: Iterable[Category]) -> list[Category]:
    """The categories asked for, in their order; photos only with conversations."""
    asked = set(include)
    if "conversations" not in asked:
        asked.discard("photos")
    return [c for c in CATEGORIES if c in asked]


class DataPackages:
    """Exports a user's data package, and imports one into a user's data."""

    def __init__(self, database_path: Path, store: Store, clock: Callable[[], datetime]) -> None:
        self._database_path = database_path
        self._store = store
        self._clock = clock

    def export(self, user_id: str, include: Iterable[Category], to: Path) -> None:
        """Write the user's package, with the categories in `include`, to the file `to`."""
        categories = chosen(include)
        data = PackageData()
        counts: dict[Category, int] = {}
        if "profile" in categories:
            data.profile = PackagedProfile.of(self._store.get_profile(user_id))
            counts["profile"] = 1
        now = self._clock()
        manifest = Manifest(
            format=FORMAT, exported_at=_written(now), categories=categories, counts=counts
        )
        with zipfile.ZipFile(to, "w") as package:
            package.writestr(
                zipfile.ZipInfo(MANIFEST, _zip_time(now)),
                _json(manifest.model_dump()),
                compress_type=zipfile.ZIP_STORED,
            )
            package.writestr(
                zipfile.ZipInfo(DATA, _zip_time(now)),
                _json(data.model_dump(exclude_unset=True)),
                compress_type=zipfile.ZIP_DEFLATED,
            )

    def import_(self, user_id: str, package: Path, include: Iterable[Category]) -> Imported:
        """Import the categories of the package at `package` that `include` names into the
        user's data, all in one transaction; raises `TooNew` or `BrokenPackage` having
        written nothing."""
        manifest, data = _read(package)
        categories = set(chosen(include)) & set(manifest.categories)
        imported = Imported()
        db = connect(self._database_path)
        try:
            with db:
                if "profile" in categories and data.profile is not None:
                    write_profile(db, user_id, data.profile.profile())
                    imported.profile = True
        finally:
            db.close()
        return imported


def _read(package: Path) -> tuple[Manifest, PackageData]:
    """The manifest and data of the package at `package`, checked."""
    try:
        with zipfile.ZipFile(package) as zipped:
            entries = zipped.infolist()
            if sorted(e.filename for e in entries) != sorted([MANIFEST, DATA]):
                raise BrokenPackage("entries it should not have")
            first = entries[0]
            if first.filename != MANIFEST or first.compress_type != zipfile.ZIP_STORED:
                raise BrokenPackage("its manifest not first, stored")
            raw_manifest = json.loads(zipped.read(MANIFEST))
            if _Format.model_validate(raw_manifest).format > FORMAT:
                raise TooNew()
            manifest = Manifest.model_validate(raw_manifest)
            data = PackageData.model_validate_json(zipped.read(DATA))
    except (zipfile.BadZipFile, ValueError, ValidationError, KeyError) as e:
        # json.JSONDecodeError and UnicodeDecodeError are ValueErrors
        raise BrokenPackage(type(e).__name__) from None
    held = {c for c in CATEGORIES if getattr(data, c, None) is not None}
    if held != set(manifest.categories) - {"photos"}:
        raise BrokenPackage("categories not as the manifest lists them")
    return manifest, data


def _json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2) + "\n"


def _zip_time(now: datetime) -> tuple[int, int, int, int, int, int]:
    return now.astimezone(UTC).timetuple()[:6]
