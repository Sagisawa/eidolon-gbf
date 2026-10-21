#!/usr/bin/env python3
"""Scenario Dialogue Importer for eidolon-gbf.

Ingests Fate Episodes, seasonal lines, or event cutscenes into data/eidolon.db,
linking them to the target character and rebuilding the FTS search index.

Supported input formats:
  - CSV with headers: speaker,ja,zh (or speaker,text)
  - JSON array of objects: [{"speaker": "...", "ja": "...", "zh": "..."}, ...]

Usage:
    python .agents/skills/gbf-character-author/scripts/ingest_episodes.py \\
        --character-id vajra \\
        --category seasonal \\
        --title "ヴァジラ 歴年バレンタイン会話" \\
        --input-file data/vajra_valentine.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import sqlite3
import sys
import uuid
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
DB_PATH = ROOT / "data" / "eidolon.db"


def ingest_file(
    file_path: Path,
    character_id: str,
    category: str,
    title: str,
    source: str = "manual_import",
) -> int:
    if not DB_PATH.exists():
        raise FileNotFoundError(f"Database not found at {DB_PATH}")

    # Read records
    lines: list[tuple[str, str, str]] = []
    if file_path.suffix.lower() == ".json":
        data = json.loads(file_path.read_text(encoding="utf-8"))
        for item in data:
            speaker = item.get("speaker", "")
            ja = item.get("ja") or item.get("text") or ""
            zh = item.get("zh") or ""
            if ja or zh:
                lines.append((speaker, ja, zh))
    else:
        # CSV format
        with file_path.open("r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                speaker = row.get("speaker", "").strip()
                ja = (row.get("ja") or row.get("text") or "").strip()
                zh = row.get("zh", "").strip()
                if ja or zh:
                    lines.append((speaker, ja, zh))

    if not lines:
        print(f"Warning: No dialogue lines parsed from {file_path}")
        return 0

    episode_id = f"ep_{character_id}_{uuid.uuid4().hex[:8]}"
    now_iso = datetime.now().isoformat()

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    try:
        # 1. Insert into episodes
        cursor.execute(
            """
            INSERT INTO episodes (id, category, source, title, imported_from, imported_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (episode_id, category, source, title, file_path.name, now_iso),
        )

        # 2. Insert into episode_cast
        cursor.execute(
            """
            INSERT OR IGNORE INTO episode_cast (episode_id, character_id)
            VALUES (?, ?)
            """,
            (episode_id, character_id),
        )

        # 3. Insert into episode_lines
        for seq, (speaker, ja, zh) in enumerate(lines, start=1):
            cursor.execute(
                """
                INSERT INTO episode_lines (episode_id, seq, speaker, ja, zh)
                VALUES (?, ?, ?, ?, ?)
                """,
                (episode_id, seq, speaker, ja, zh),
            )

        # 4. Rebuild / update FTS index if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='episode_fts'")
        if cursor.fetchone():
            full_text = " ".join(f"{spk} {ja} {zh}" for spk, ja, zh in lines)
            cursor.execute(
                """
                INSERT INTO episode_fts (episode_id, character_id, title, text)
                VALUES (?, ?, ?, ?)
                """,
                (episode_id, character_id, title, full_text),
            )

        conn.commit()
        print(f"Successfully ingested {len(lines)} lines into episode '{episode_id}' ({title}).")
        return len(lines)
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ingest GBF dialogues into eidolon.db")
    parser.add_argument("--character-id", required=True, help="Target character ID (e.g. vajra)")
    parser.add_argument("--category", default="fate", choices=["fate", "seasonal", "event", "main"], help="Episode category")
    parser.add_argument("--title", required=True, help="Episode title (e.g. ヴァジラ 招募ストーリー)")
    parser.add_argument("--input-file", required=True, type=Path, help="Path to CSV or JSON file")
    parser.add_argument("--source", default="wiki", help="Source provenance identifier")
    args = parser.parse_args()

    try:
        ingest_file(args.input_file, args.character_id, args.category, args.title, args.source)
        return 0
    except Exception as ex:
        print(f"Error during ingestion: {ex}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
