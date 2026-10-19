"""Import scraped GBF scenario CSVs into the Eidolon SQLite database."""

import asyncio
import os
import sqlite3
import sys
from pathlib import Path

# Add backend to sys.path
sys.path.insert(0, str(Path("backend/src").resolve()))

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from eidolon.characters import load_characters
from eidolon.corpus import _SCHEMA, Line, Episode
from eidolon.database import connect
from eidolon.story_import import _csv_scripts, _speaker_index, _cast, ImportReport

DB_PATH = Path("data/eidolon.db")
CORPUS_DIR = Path("corpus/gbf")
CHARS_FILE = Path("characters/characters.toml")

def main():
    print(f"=== 正在导入 GBF 原作剧本到数据库: {DB_PATH} ===")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = connect(DB_PATH)
    with db:
        db.executescript(_SCHEMA)

    chars = load_characters(CHARS_FILE)
    sp_idx = _speaker_index(chars.values())
    report = ImportReport()
    scripts = list(_csv_scripts(CORPUS_DIR, report))
    print(f"读取到 CSV 文件数: {len(scripts)}")

    episodes_count = 0
    lines_count = 0

    with db:
        for s in scripts:
            cast = _cast(s.lines, sp_idx)
            if not cast:
                continue
            episodes_count += 1
            lines_count += len(s.lines)

            # Insert episode
            db.execute(
                """INSERT OR REPLACE INTO episodes (id, category, source, title, imported_from, imported_at)
                   VALUES (?, ?, ?, ?, 'csv', datetime('now'))""",
                (s.source_id, "命运篇章", s.source, s.title),
            )
            # Insert cast
            db.execute("DELETE FROM episode_cast WHERE episode_id = ?", (s.source_id,))
            for char_id in cast:
                db.execute(
                    "INSERT INTO episode_cast (episode_id, character_id) VALUES (?, ?)",
                    (s.source_id, char_id),
                )
            # Insert lines
            db.execute("DELETE FROM episode_lines WHERE episode_id = ?", (s.source_id,))
            for seq, line in enumerate(s.lines):
                db.execute(
                    "INSERT INTO episode_lines (episode_id, seq, speaker, ja, zh) VALUES (?, ?, ?, ?, ?)",
                    (s.source_id, seq, line.speaker, line.ja, line.zh),
                )

    print(f"\n=== 导入成功！ ===")
    print(f"已录入正史剧情段数: {episodes_count} 段")
    print(f"已录入真实台词总句数: {lines_count} 句")
    for cid in chars:
        cur = db.execute("SELECT COUNT(*) FROM episode_cast WHERE character_id = ?", (cid,))
        c = cur.fetchone()[0]
        print(f"  - 角色 [{chars[cid].name}] ({cid}) 关联出场剧情: {c} 段")

if __name__ == "__main__":
    main()
