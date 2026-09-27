"use client";

import { useMediaQuery } from "@astryxdesign/core/hooks";
import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import {
  getAccount,
  listCharacters,
  listLatestConversations,
  type Character,
  type LatestConversation,
} from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import type { CallPhase } from "@/lib/liveConversation";

/** 正在和谁通话，列表那一行据此显示「正在呼叫…」「通话中」。 */
export type CallInList = { characterId: string; phase: Exclude<CallPhase, "idle"> } | null;

/** 列表和对话共用的数据：有哪些角色、和每位最新一次对话的摘要。由双栏外壳载入一次。 */
export type Directory = {
  /** 还在载入时为 null。 */
  characters: Character[] | null;
  latest: Record<string, LatestConversation>;
  failure: Failure | null;
  /** 重新拉一遍摘要，例如一个回合记下之后、开了新对话之后。 */
  refresh: () => void;
  /** 从头重新载入，给「重试」用。 */
  reload: () => void;
  call: CallInList;
  /** 对话页把通话的进展告诉列表。 */
  setCall: (call: CallInList) => void;
};

/** 宽屏（≥ 768px）是左右双栏，窄屏是两级页面（DESIGN.md「Layout」）。服务端先按宽屏渲染。 */
export function useWide(): boolean {
  return useMediaQuery("(min-width: 768px)", true);
}

const DirectoryContext = createContext<Directory | null>(null);

export function useDirectory(): Directory {
  const directory = useContext(DirectoryContext);
  if (!directory) throw new Error("useDirectory 只能在对话外壳里用");
  return directory;
}

export function DirectoryProvider({ children }: { children: ReactNode }) {
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [latest, setLatest] = useState<Record<string, LatestConversation>>({});
  const [failure, setFailure] = useState<Failure | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [call, setCall] = useState<CallInList>(null);

  const refresh = useCallback(() => {
    listLatestConversations().then(
      (all) => setLatest(Object.fromEntries(all.map((c) => [c.character_id, c]))),
      () => {}, // 摘要只是预览，拉不到时留着上一次的
    );
  }, []);

  useEffect(() => {
    let cancelled = false;
    // 先问账户：没登录或还没同意条款的浏览器会被送去该去的页面。
    getAccount()
      .then(() => Promise.all([listCharacters(), listLatestConversations()]))
      .then(
        ([all, summaries]) => {
          if (cancelled) return;
          setCharacters(all);
          setLatest(Object.fromEntries(summaries.map((c) => [c.character_id, c])));
        },
        (e) => !cancelled && setFailure(toFailure(e)),
      );
    return () => {
      cancelled = true;
    };
  }, [attempt]);

  const reload = useCallback(() => {
    setFailure(null);
    setCharacters(null);
    setAttempt((n) => n + 1);
  }, []);

  return (
    <DirectoryContext.Provider value={{ characters, latest, failure, refresh, reload, call, setCall }}>
      {children}
    </DirectoryContext.Provider>
  );
}
