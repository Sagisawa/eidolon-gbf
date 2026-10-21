"""Verify RAG retrieval specifically for the 14 new companions."""

import sqlite3
import sys

# Fix Windows stdout encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

conn = sqlite3.connect("data/eidolon.db")
c = conn.cursor()

# In FTS5 trigram tokenization, queries must be at least 3 characters
test_queries = [
    ("chichiri", "朱雀の炎"),
    ("uruki", "玄武の氷"),
    ("shushuku", "神鋼拳"),
    ("ami", "魔導銃"),
    ("wilnas", "ステーキ"),
    ("wamdus", "アイス"),
    ("galleon", "我が子"),
    ("ewiyar", "プリン"),
    ("luwoh", "秩序の調和"),
    ("fediel", "冥府死炎"),
    ("yggdrasil", "大地生機"),
    ("europa", "清浄奔流"),
    ("brodia", "金剛盾"),
    ("grimnir", "狂風神槍"),
]

print("=== 验证 14 位新伙伴的 FTS5 Trigram BM25 检索能力 ===")
all_pass = True
for cid, keyword in test_queries:
    sql = """
        SELECT title, snippet(episode_fts, 3, '【', '】', '...', 10), bm25(episode_fts)
        FROM episode_fts
        WHERE character_id = ? AND episode_fts MATCH ?
        ORDER BY bm25(episode_fts)
        LIMIT 1
    """
    row = c.execute(sql, (cid, f'"{keyword}"')).fetchone()
    if row:
        title, snip, score = row
        print(f"[{cid:10}] 命中: {title} (BM25: {score:.3f})")
    else:
        print(f"[{cid:10}] ❌ 未命中: {keyword}")
        all_pass = False

if all_pass:
    print("\n✅ 14 位新伙伴的剧情检索 100% 验证成功！")
else:
    print("\n⚠️ 有部分查询未命中")
