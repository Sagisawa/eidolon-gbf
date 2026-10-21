#!/usr/bin/env python3
"""Automated Character Validation Suite for eidolon-gbf.

Usage:
    python .agents/skills/gbf-character-author/scripts/validate_character.py <character_id>
    python .agents/skills/gbf-character-author/scripts/validate_character.py --all
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

# Add backend/src to path so we can import eidolon modules
ROOT = Path(__file__).resolve().parents[4]
BACKEND_SRC = ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

from eidolon.characters import Character
from eidolon.world import World

FORBIDDEN_PROMPT_TERMS = ["事务所", "283", "制作人"]


def validate_character(
    char_id: str,
    toml_data: dict,
    world: World,
    db_conn: sqlite3.Connection | None,
) -> list[str]:
    errors: list[str] = []

    # 1. Check characters.toml entry
    char_list = toml_data.get("characters", [])
    char_conf = next((c for c in char_list if c.get("id") == char_id), None)
    if not char_conf:
        return [f"characters.toml does not contain entry with id='{char_id}'"]

    required_fields = [
        "id",
        "name",
        "name_zh",
        "name_kana",
        "name_romaji",
        "intro",
        "sheet",
        "avatar",
        "color",
        "background",
        "facts",
        "greeting",
        "greeting_subtitle",
    ]
    for field in required_fields:
        if field not in char_conf or not char_conf[field]:
            errors.append(f"characters.toml [{char_id}] missing required field '{field}'")

    char_name = char_conf.get("name", "")

    # 2. Check avatars and backgrounds (strict <= 224x224 and <= 32KB gate)
    avatar_path = ROOT / "characters" / "avatars" / f"{char_id}.jpg"
    if not avatar_path.exists():
        errors.append(f"Avatar missing: {avatar_path.relative_to(ROOT)}")
    else:
        av_size = avatar_path.stat().st_size
        if av_size > 32768:
            errors.append(f"Avatar {avatar_path.name} exceeds 32KB limit ({av_size} bytes > 32768 bytes)")
        try:
            from PIL import Image
            with Image.open(avatar_path) as im:
                if im.width > 224 or im.height > 224:
                    errors.append(f"Avatar {avatar_path.name} dimensions ({im.width}x{im.height}) exceed maximum 224x224")
        except ImportError:
            pass

    bg_path = ROOT / "characters" / "backgrounds" / f"{char_id}.jpg"
    if not bg_path.exists():
        errors.append(f"Background missing: {bg_path.relative_to(ROOT)}")

    # 3. Check character sheet
    sheet_path = ROOT / "characters" / "sheets" / f"{char_id}.md"
    if not sheet_path.exists():
        errors.append(f"Character sheet missing: {sheet_path.relative_to(ROOT)}")
    else:
        sheet_text = sheet_path.read_text(encoding="utf-8")
        if len(sheet_text.splitlines()) < 20:
            errors.append(f"Character sheet too short (< 20 lines): {sheet_path.relative_to(ROOT)}")
        for bad in FORBIDDEN_PROMPT_TERMS:
            if bad in sheet_text:
                errors.append(f"Character sheet contains forbidden term '{bad}': {sheet_path.relative_to(ROOT)}")

    # 4. Check facts and sources
    facts_path = ROOT / "characters" / "facts" / f"{char_id}.md"
    if not facts_path.exists():
        errors.append(f"Facts file missing: {facts_path.relative_to(ROOT)}")
    else:
        lines = len(facts_path.read_text(encoding="utf-8").splitlines())
        if lines < 50:
            errors.append(f"Facts file has only {lines} lines (recommend >= 80 for rich recall): {facts_path.relative_to(ROOT)}")

    sources_path = ROOT / "characters" / "facts" / f"{char_id}.sources.md"
    if not sources_path.exists():
        errors.append(f"Sources file missing: {sources_path.relative_to(ROOT)}")

    # 5. Check world.json registration
    if char_name:
        idol_names = [i.name for i in world.idols]
        if char_name not in idol_names:
            errors.append(f"Character name '{char_name}' not listed in world.json 'idols'")

        in_any_unit = any(char_name in unit.members for unit in world.units)
        if not in_any_unit:
            errors.append(f"Character name '{char_name}' is not assigned to any faction in world.json 'units'")

        # 6. Render world prompt and inspect for contamination
        try:
            rendered_prompt = world.prompt(char_name, date.today())
            for bad in FORBIDDEN_PROMPT_TERMS:
                if bad in rendered_prompt:
                    errors.append(f"World prompt for '{char_name}' contains forbidden term '{bad}'")
        except Exception as e:
            errors.append(f"Failed to render world prompt for '{char_name}': {e}")

    # 7. Check database dialogues, modular episode granularity, and RAG index health
    if db_conn and char_name:
        try:
            cursor = db_conn.cursor()
            # 7a. Check dialogue lines
            cursor.execute(
                "SELECT COUNT(*) FROM episode_lines WHERE speaker = ? OR ja LIKE ? OR zh LIKE ?",
                (char_name, f"%{char_name}%", f"%{char_name}%"),
            )
            count = cursor.fetchone()[0]
            if count == 0:
                errors.append(f"No dialogue lines found in data/eidolon.db for speaker '{char_name}'")
            elif count < 15:
                errors.append(f"Dialogue lines in data/eidolon.db too few ({count} lines, recommend >= 30) for '{char_name}'")

            # 7b. Check episode granularity (must be modular, not monolithic single episode)
            cursor.execute(
                "SELECT COUNT(DISTINCT episode_id) FROM episode_cast WHERE character_id = ?",
                (char_id,),
            )
            ep_count = cursor.fetchone()[0]
            if ep_count < 15:
                errors.append(
                    f"Episode count for '{char_id}' is only {ep_count} (must be >= 15 modular episodes; do NOT bundle all lines into a single episode)"
                )

            # 7c. Check category coverage (must cover core fate and seasonal cutscenes)
            cursor.execute(
                """SELECT DISTINCT e.category
                   FROM episodes e
                   JOIN episode_cast c ON e.id = c.episode_id
                   WHERE c.character_id = ?""",
                (char_id,),
            )
            categories = {row[0] for row in cursor.fetchall()}
            if "命运篇章" not in categories and "fate" not in categories:
                errors.append(f"Missing core Fate episodes (category '命运篇章') for '{char_id}'")
            if "特别剧情" not in categories and "seasonal" not in categories:
                errors.append(f"Missing seasonal episodes (category '特别剧情') for '{char_id}'")

            # 7d. Check vector passages parity
            cursor.execute(
                """SELECT COUNT(*)
                   FROM episode_passages p
                   JOIN episode_cast c ON p.episode_id = c.episode_id
                   WHERE c.character_id = ?""",
                (char_id,),
            )
            passages_count = cursor.fetchone()[0]
            if passages_count < ep_count:
                errors.append(
                    f"Vector passages missing in episode_passages ({passages_count} passages < {ep_count} episodes) for '{char_id}'"
                )
        except Exception as e:
            errors.append(f"Database query error for '{char_name}': {e}")

    return errors


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

    parser = argparse.ArgumentParser(description="Validate GBF character integration.")
    parser.add_argument("character_id", nargs="?", help="Character ID (e.g. narmaya, vikala)")
    parser.add_argument("--all", action="store_true", help="Validate all characters in characters.toml")
    args = parser.parse_args()

    toml_path = ROOT / "characters" / "characters.toml"
    if not toml_path.exists():
        print(f"Error: {toml_path} not found.", file=sys.stderr)
        return 1

    toml_data = tomllib.loads(toml_path.read_text(encoding="utf-8"))

    world_path = ROOT / "characters" / "world.json"
    if not world_path.exists():
        print(f"Error: {world_path} not found.", file=sys.stderr)
        return 1

    world = World.from_json(json.loads(world_path.read_text(encoding="utf-8")))

    db_path = ROOT / "data" / "eidolon.db"
    db_conn = None
    if db_path.exists():
        db_conn = sqlite3.connect(db_path)

    char_list = toml_data.get("characters", [])
    all_ids = [c["id"] for c in char_list if "id" in c]

    targets = []
    if args.all or not args.character_id:
        targets = all_ids
    else:
        targets = [args.character_id]

    print(f"=== Validating {len(targets)} character(s) in eidolon-gbf ===")
    total_errors = 0

    for target in targets:
        print(f"\nChecking character: '{target}' ...")
        errs = validate_character(target, toml_data, world, db_conn)
        if not errs:
            print(f"  [PASS] Character '{target}' passed all validation gates.")
        else:
            print(f"  [FAIL] Character '{target}' failed with {len(errs)} error(s):")
            for err in errs:
                print(f"    - {err}")
            total_errors += len(errs)

    if db_conn:
        try:
            db_conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        except Exception:
            pass
        db_conn.close()

    print("\n" + "=" * 50)
    if total_errors == 0:
        print("ALL VALIDATION GATES PASSED! Character integration is ready.")
        return 0
    else:
        print(f"VALIDATION FAILED with {total_errors} total error(s). Please fix them before committing.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
