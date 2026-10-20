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

    # 2. Check avatars and backgrounds
    avatar_path = ROOT / "characters" / "avatars" / f"{char_id}.jpg"
    if not avatar_path.exists():
        errors.append(f"Avatar missing: {avatar_path.relative_to(ROOT)}")

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

    # 7. Check database dialogues
    if db_conn and char_name:
        try:
            cursor = db_conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM episode_lines WHERE speaker = ? OR ja LIKE ? OR zh LIKE ?",
                (char_name, f"%{char_name}%", f"%{char_name}%"),
            )
            count = cursor.fetchone()[0]
            if count == 0:
                errors.append(f"No dialogue lines found in data/eidolon.db for speaker '{char_name}'")
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
