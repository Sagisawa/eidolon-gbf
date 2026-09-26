"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import { ApiError, clearMemories, deleteMemory, listMemories, type Memory } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

/** The memories every character shares about the user; they can be deleted, not edited. */
export default function MemoriesPage() {
  const [memories, setMemories] = useState<Memory[] | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [deleting, setDeleting] = useState<Set<number>>(new Set());
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    listMemories().then(setMemories, (e) => setFailure(toFailure(e)));
  }, []);

  const forget = (id: number) => setMemories((list) => list?.filter((m) => m.id !== id) ?? null);

  async function remove(id: number) {
    setDeleting((ids) => new Set(ids).add(id));
    setFailure(null);
    try {
      await deleteMemory(id);
      forget(id);
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) forget(id); // already gone
      else setFailure(toFailure(e));
    } finally {
      setDeleting((ids) => {
        const rest = new Set(ids);
        rest.delete(id);
        return rest;
      });
    }
  }

  async function clear() {
    setClearing(true);
    setFailure(null);
    try {
      await clearMemories();
      setMemories([]);
      setConfirmingClear(false);
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setClearing(false);
    }
  }

  return (
    <main className="settings">
      <header className="page-header">
        <h1>记忆</h1>
        <Link href="/settings" className="ghost-link">
          返回
        </Link>
      </header>

      <p className="hint memories-intro">
        角色们在对话中记下的、关于你的事。所有角色共用这些记忆，对一位角色说过的事，其他角色会以转述的口吻知道。删除后，角色不会再想起这件事。
      </p>

      {failure && <FailureNotice failure={failure} />}

      {memories === null ? (
        !failure && <p className="hint">正在读取…</p>
      ) : memories.length === 0 ? (
        <p className="empty memories-empty">角色们还没有记下关于你的事。</p>
      ) : (
        <>
          <ul className="memory-list">
            {memories.map((memory) => (
              <li key={memory.id} className="memory">
                <div className="memory-text">
                  <p>{memory.text}</p>
                  <p className="memory-meta">
                    对{memory.source_character_name ?? "已不在的角色"}说的 ·{" "}
                    {formatDate(memory.created_at)}
                  </p>
                </div>
                <button
                  type="button"
                  className="ghost"
                  onClick={() => remove(memory.id)}
                  disabled={deleting.has(memory.id) || clearing}
                  aria-label={`删除记忆：${memory.text}`}
                >
                  {deleting.has(memory.id) ? "删除中…" : "删除"}
                </button>
              </li>
            ))}
          </ul>

          <div className="field clear-memories">
            {confirmingClear ? (
              <>
                <p className="hint" role="alert">
                  确定清空全部 {memories.length} 条记忆吗？所有角色都会忘记这些事，无法恢复。
                </p>
                <div className="field-row">
                  <button type="button" className="danger" onClick={clear} disabled={clearing}>
                    {clearing ? "正在清空…" : "确定清空"}
                  </button>
                  <button
                    type="button"
                    className="ghost"
                    onClick={() => setConfirmingClear(false)}
                    disabled={clearing}
                  >
                    取消
                  </button>
                </div>
              </>
            ) : (
              <button type="button" className="ghost" onClick={() => setConfirmingClear(true)}>
                清空全部记忆
              </button>
            )}
          </div>
        </>
      )}
    </main>
  );
}

function formatDate(iso: string): string {
  const date = new Date(iso);
  return `${date.getFullYear()}年${date.getMonth() + 1}月${date.getDate()}日`;
}
