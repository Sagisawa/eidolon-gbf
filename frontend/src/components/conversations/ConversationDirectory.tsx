"use client";

import { createContext, useCallback, useContext, useEffect, useState, useSyncExternalStore, type ReactNode } from "react";

import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from "@/components/ui/alert-dialog";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { copy } from "@/i18n";

import {
  getAccount,
  listCharacters,
  listLatestConversations,
  type Account,
  type Character,
  type LatestConversation,
} from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { keepListPreferences, listPreferences, NO_PREFERENCES, type ListPreferences } from "@/lib/listPreferences";
import { isLive, NOT_OPEN, type LiveCall, type LiveConversation } from "@/lib/liveConversation";

/** 正在和谁通话，列表那一行据此显示「正在呼叫…」「通话中 mm:ss」；从对话页交来的 LiveConversation 的快照算出。 */
export type CallInList = { characterId: string; state: LiveCall } | null;

/** 列表和对话共用的数据：有哪些角色、和每位最新一次对话的摘要。由双栏外壳载入一次。 */
export type Directory = {
  /** 登录的用户（浏览器里的自带密钥按他的 ID 分开存；他现在是否必须自带 LLM）；和角色一起载入，还在载入时为 null。
   * 进设置页再回来时外壳重新挂载，账号随之重新载入。 */
  account: Account | null;
  /** 还在载入时为 null。 */
  characters: Character[] | null;
  latest: Record<string, LatestConversation>;
  failure: Failure | null;
  /** 重新拉一遍摘要，例如一个回合记下之后、开了新对话之后。 */
  refresh: () => void;
  /** 从头重新载入，给「重试」用。 */
  reload: () => void;
  /** 这台设备上的隐藏和置顶；和角色一起读出，读不到时什么都没整理。 */
  preferences: ListPreferences;
  /** 整理列表（隐藏、显示、置顶…），立即生效并存下；存不进去时只在这次页面里生效。 */
  tidy: (change: (preferences: ListPreferences) => ListPreferences) => void;
  call: CallInList;
  /** 对话页建好它的 LiveConversation 后交给列表，离开时交回 null；列表自己订阅这份快照。 */
  handOver: (live: LiveConversation | null) => void;
  /**
   * 离开对话页（换一位角色、进设置或记忆、回列表）：通话中先确认会挂断，确认了才 `go`。
   * 离开后对话页卸下，照常挂断（GLOSSARY.md「通话」）。
   */
  leave: (go: () => void) => void;
};

/** 宽屏（≥ 768px）是左右双栏，窄屏是两级页面（DESIGN.md「Layout」）。服务端先按宽屏渲染。 */
export function useWide(): boolean {
  return useMediaQuery("(min-width: 768px)", true);
}

const DirectoryContext = createContext<Directory | null>(null);

/** 对话页还没交出它的 LiveConversation 时，列表看到的那份空快照。 */
const notHanded = () => NOT_OPEN;
const noSubscription = () => () => {};

export function useDirectory(): Directory {
  const directory = useContext(DirectoryContext);
  if (!directory) throw new Error("useDirectory 只能在对话外壳里用");
  return directory;
}

export function DirectoryProvider({ children }: { children: ReactNode }) {
  const [account, setAccount] = useState<Account | null>(null);
  const userId = account?.id ?? null;
  const [characters, setCharacters] = useState<Character[] | null>(null);
  const [latest, setLatest] = useState<Record<string, LatestConversation>>({});
  const [preferences, setPreferences] = useState<ListPreferences>(NO_PREFERENCES);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [live, setLive] = useState<LiveConversation | null>(null);
  const [leaving, setLeaving] = useState<(() => void) | null>(null);
  // 订阅对话页交来的那一份快照：列表那一行和隐藏时留下的角色都从它算出来，不再抄一份 call。
  const liveSnapshot = useSyncExternalStore(live?.subscribe ?? noSubscription, live?.snapshot ?? notHanded, notHanded);
  const liveCall = live && isLive(liveSnapshot.call) ? liveSnapshot.call : null;
  const call: CallInList = live && liveCall ? { characterId: live.characterId, state: liveCall } : null;

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
      .then((account) => Promise.all([account, listCharacters(), listLatestConversations()]))
      .then(
        ([account, all, summaries]) => {
          if (cancelled) return;
          setAccount(account);
          setCharacters(all);
          setPreferences(listPreferences(account.id, all.map((c) => c.id)));
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

  const tidy = useCallback(
    (change: (preferences: ListPreferences) => ListPreferences) => {
      setPreferences((current) => {
        const next = change(current);
        if (userId) keepListPreferences(userId, next); // 写同样的值，重复执行也无妨
        return next;
      });
    },
    [userId],
  );

  const leave = useCallback(
    (go: () => void) => {
      // 在点击这一刻读快照：通话正在进行中就先问一句会不会挂断。
      if (live && isLive(live.snapshot().call)) setLeaving(() => go);
      else go();
    },
    [live],
  );

  const callee = characters?.find((c) => c.id === call?.characterId);
  return (
    <DirectoryContext.Provider
      value={{ account, characters, latest, preferences, tidy, failure, refresh, reload, call, handOver: setLive, leave }}
    >
      {children}
      {/* 确认框不在她的子树里：只有中性色和挂断红（DESIGN.md「Hang-up Red」：「挂断并离开」用它）。 */}
      <AlertDialog open={leaving !== null} onOpenChange={(open) => !open && setLeaving(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>{copy.call.leaveTitle(callee?.name ?? "")}</AlertDialogTitle>
            <AlertDialogDescription>{copy.call.leaveDescription}</AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>{copy.call.stay}</AlertDialogCancel>
            <AlertDialogAction
              variant="destructive"
              onClick={() => {
                const go = leaving;
                setLeaving(null);
                go?.();
              }}
            >
              {copy.call.leaveConfirm}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </DirectoryContext.Provider>
  );
}
