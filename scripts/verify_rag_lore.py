"""Verify RAG retrieval (BM25 and vector search) against data/eidolon.db:
- Character song titles (泡沫夢幻・胡蝶刃, Welcome to the PARADE)
- Joya bell event (除夜の鐘, ジョヤ, 煩悩)
- Birthday wishes (お誕生日おめでとう, 団長ちゃん)
- Valentine chocolates (バレンタイン, 手作りチョコ)
- World setting & character configuration loading
"""

import math
import sqlite3
import struct
import sys
from pathlib import Path

# Fix Windows stdout encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path("backend/src").resolve()))

from eidolon.characters import load_characters
from eidolon.world import load_world

DB_PATH = Path("data/eidolon.db")
CHARS_FILE = Path("characters/characters.toml")
WORLD_FILE = Path("characters/world.json")


def compute_vector(text: str, dim: int = 1536) -> list[float]:
    import hashlib
    vec = [0.0] * dim
    for ch in text:
        h = int(hashlib.md5(ch.encode("utf-8")).hexdigest()[:8], 16) % dim
        vec[h] += 1.0
    for i in range(len(text) - 1):
        bi = text[i:i+2]
        h = int(hashlib.md5(bi.encode("utf-8")).hexdigest()[:8], 16) % dim
        vec[h] += 2.0
    for i in range(len(text) - 2):
        tri = text[i:i+3]
        h = int(hashlib.md5(tri.encode("utf-8")).hexdigest()[:8], 16) % dim
        vec[h] += 3.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


def cosine_sim(v1: list[float], v2_bytes: bytes) -> float:
    dim = len(v1)
    v2 = struct.unpack(f"<{dim}f", v2_bytes)
    return sum(a * b for a, b in zip(v1, v2))


def test_retrieval():
    print("=== 1. 验证角色配置与世界设定加载 ===")
    chars = load_characters(CHARS_FILE)
    print(f"已加载角色: {[c.name for c in chars.values()]}")
    assert "narmaya" in chars and "vikala" in chars, "Characters missing"

    world = load_world(WORLD_FILE)
    assert world is not None, "Failed to load world.json"
    world.check_characters(chars, WORLD_FILE)
    print(f"世界设定校验通过！")
    print(f"  - 骑空团常驻核心 (Staff): {len(world.staff)} 人 ({', '.join(s.name for s in world.staff)})")
    print(f"  - 空之势力/组织 (Units): {len(world.units)} 个 ({', '.join(u.name for u in world.units)})")
    print(f"  - 核心角色 (Idols): {len(world.idols)} 人")
    print(f"  - 官方角色单曲 (Songs): {len(world.songs)} 首")
    print(f"  - 官方 CD 唱片 (Releases): {len(world.releases)} 张")
    print(f"  - 官方 Fes 舞台演出 (Lives): {len(world.lives)} 场")

    db = sqlite3.connect(DB_PATH)

    print("\n=== 2. 验证 FTS5 BM25 检索 ===")
    test_queries = [
        ("泡沫夢幻・胡蝶刃", "角色歌检索（娜露梅）"),
        ("Welcome to the PARADE", "角色歌检索（维卡拉）"),
        ("除夜 ジョヤ 煩悩", "重大事件《除夜の終わりに響く鐘》检索"),
        ("お誕生日おめでとう 団長ちゃん", "历年生日祝词检索（娜露梅）"),
        ("ビッキー 団長っち", "历年生日与问候检索（维卡拉）"),
        ("バレンタイン チョコ", "历年情人节对话检索"),
    ]

    for q, desc in test_queries:
        print(f"\n[测试项] {desc}: 「{q}」")
        # Search world FTS
        w_cur = db.execute(
            "SELECT kind, title, bm25(world_fts) as rank, text FROM world_fts WHERE world_fts MATCH ? ORDER BY rank LIMIT 2",
            (q,)
        )
        w_hits = w_cur.fetchall()
        if w_hits:
            print(f"  -> 【世界设定匹配】(Top {len(w_hits)}):")
            for kind, title, rank, text in w_hits:
                snippet = text.replace("\n", " ")[:90]
                print(f"     * [{kind}] {title} (BM25: {rank:.4f}): {snippet}...")

        # Search episodes FTS
        e_cur = db.execute(
            "SELECT character_id, title, bm25(episode_fts) as rank, text FROM episode_fts WHERE episode_fts MATCH ? ORDER BY rank LIMIT 2",
            (q,)
        )
        e_hits = e_cur.fetchall()
        if e_hits:
            print(f"  -> 【剧情台词匹配】(Top {len(e_hits)}):")
            for cid, title, rank, text in e_hits:
                snippet = text.replace("\n", " ")[:90]
                print(f"     * [{cid}] {title} (BM25: {rank:.4f}): {snippet}...")
        
        assert w_hits or e_hits, f"Query '{q}' failed to match any results!"

    print("\n=== 3. 验证向量语义检索 (Vector Cosine Similarity) ===")
    vector_queries = [
        ("ナルメアの誕生日のお祝い", "narmaya"),
        ("除夜の鐘の事件について教えて", "vikala"),
    ]

    for query_text, char_id in vector_queries:
        q_vec = compute_vector(query_text)
        cur = db.execute(
            """SELECT p.episode_id, e.title, p.text, p.embedding
               FROM episode_passages p
               JOIN episode_cast c ON c.episode_id = p.episode_id
               JOIN episodes e ON e.id = p.episode_id
               WHERE c.character_id = ?""",
            (char_id,)
        )
        scored = []
        for ep_id, title, text, emb_blob in cur.fetchall():
            score = cosine_sim(q_vec, emb_blob)
            scored.append((score, title, text))
        scored.sort(key=lambda x: x[0], reverse=True)

        print(f"\n[向量检索] 角色 [{char_id}] 提问: 「{query_text}」")
        top3 = scored[:3]
        for score, title, text in top3:
            snippet = text.replace("\n", " ")[:90]
            print(f"  * 相似度 {score:.4f} | {title}: {snippet}...")
        assert len(top3) > 0 and top3[0][0] > 0.05, f"Vector search returned poor results for {query_text}"

    print("\n=== 所有 RAG 与知识库检索验证 100% 通过！ ===")


if __name__ == "__main__":
    test_retrieval()
