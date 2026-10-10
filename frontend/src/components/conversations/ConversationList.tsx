"use client";

import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SignInButton } from "@/components/app/FailureNotice";
import { MarkedAvatar } from "@/components/app/MarkedAvatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Skeleton } from "@/components/ui/skeleton";
import { copy } from "@/i18n";
import type { Character } from "@/lib/api";
import { showTime } from "@/lib/callTime";
import { dayOf, previewOf, type Preview } from "@/lib/conversationList";
import { cn } from "@/lib/utils";
import { MoreIcon, SearchIcon } from "@/theme/icons";

import { useDirectory, type CallInList } from "./ConversationDirectory";
import { useCallTime } from "./useCallTime";

const t = copy.conversationList;

/**
 * 对话列表（DESIGN.md「Conversation list」）：顶上「对话」大标题和更多菜单，下面一个按名字找人的搜索框；
 * 每位角色一行（56px 头像、名字和时间一行，最后一句一行），选中行铺中性的 bg-muted；底部一行免责声明。
 * 列表栏是实底，不在她的子树里。宽屏时在左栏，窄屏时占满一页。
 */
export function ConversationList({ selectedId }: { selectedId: string | null }) {
  const router = useRouter();
  const { characters, latest, failure, reload, call, leave } = useDirectory();
  const now = useMinute();
  const [query, setQuery] = useState("");
  const shown = characters?.filter((c) => matches(c, query));

  return (
    <div className="flex h-full flex-col bg-background text-foreground">
      <header className="flex shrink-0 items-center gap-2 pt-3 pr-2 pb-2 pl-4">
        <h1 className="flex-1 text-list-title">{t.title}</h1>
        <DropdownMenu>
          <DropdownMenuTrigger render={<Button variant="ghost" size="icon-lg" aria-label={t.menu} />}>
            <MoreIcon />
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end">
            <DropdownMenuItem onClick={() => leave(() => router.push("/memories"))}>{t.memories}</DropdownMenuItem>
            <DropdownMenuItem onClick={() => leave(() => router.push("/settings"))}>{t.settings}</DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </header>

      <div className="shrink-0 px-4 pb-2">
        <label className="flex h-9 items-center gap-2 rounded-lg bg-muted px-3 text-muted-foreground has-focus-visible:ring-3 has-focus-visible:ring-ring/50">
          <SearchIcon aria-hidden className="size-4 shrink-0" />
          <input
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t.search}
            aria-label={t.search}
            className="min-w-0 flex-1 bg-transparent text-body text-foreground outline-none placeholder:text-muted-foreground"
          />
        </label>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto">
        {failure ? (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>{t.loadFailed}</EmptyTitle>
              <EmptyDescription>{failure.message}</EmptyDescription>
            </EmptyHeader>
            <EmptyContent>
              {failure.signedOut ? (
                <SignInButton />
              ) : (
                <Button variant="outline" onClick={reload}>
                  {t.retry}
                </Button>
              )}
            </EmptyContent>
          </Empty>
        ) : !shown ? (
          <Loading />
        ) : shown.length === 0 ? (
          <p className="px-4 py-6 text-center text-preview text-muted-foreground">{t.noMatch}</p>
        ) : (
          <ul aria-label={t.title}>
            {shown.map((c) => (
              <li key={c.id}>
                <Row
                  character={c}
                  preview={previewOf(latest[c.id])}
                  call={call?.characterId === c.id ? call : null}
                  isSelected={c.id === selectedId}
                  now={now}
                  onSelect={() => {
                    if (c.id === selectedId) return;
                    leave(() => router.push(`/conversation/${c.id}`));
                  }}
                />
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="shrink-0 px-4 py-3 text-meta text-muted-foreground">{t.disclaimer}</p>
    </div>
  );
}

/** 列表里的一行：一整个按钮，选中时 `aria-current`，铺中性的 bg-muted（不用她的颜色）。 */
function Row({
  character,
  preview,
  call,
  isSelected,
  now,
  onSelect,
}: {
  character: Character;
  preview: Preview | null;
  call: CallInList;
  isSelected: boolean;
  now: Date;
  onSelect: () => void;
}) {
  const time = useCallTime(call?.state);
  const description = call
    ? time
      ? copy.call.listConnected(showTime(time))
      : copy.call.dialing
    : !preview
      ? t.neverTalked
      : preview.from === "you"
        ? t.you(preview.text)
        : preview.from === "her"
          ? preview.text
          : t.nothingSaidYet;
  return (
    <button
      type="button"
      onClick={onSelect}
      aria-current={isSelected ? "page" : undefined}
      className={cn(
        "flex w-full items-center gap-3 px-4 py-2.5 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50 focus-visible:ring-inset",
        isSelected ? "bg-muted" : "hover:bg-muted/60",
      )}
    >
      <MarkedAvatar name={character.name} src={character.avatar_url} size="list" />
      <span className="flex min-w-0 flex-1 flex-col gap-0.5">
        <span className="flex items-baseline gap-2">
          <span className="min-w-0 flex-1 truncate text-row-name">{character.name}</span>
          {preview && !call && (
            <span className="shrink-0 text-meta text-muted-foreground tabular-nums">
              {listTime(new Date(preview.at), now)}
            </span>
          )}
        </span>
        <span className="truncate text-preview text-muted-foreground tabular-nums">{description}</span>
      </span>
    </button>
  );
}

/** 搜索框：名字里有这几个字就留下（不分大小写，前后空格不算）；空着时全部显示。 */
function matches(character: Character, query: string): boolean {
  const q = query.trim().toLowerCase();
  return !q || character.name.toLowerCase().includes(q);
}

/** 列表里的时间：今天写时刻（和气泡旁的时间一样写成 8:49），昨天写「昨天」，今年写月日，更早写年月日。 */
function listTime(at: Date, now: Date): string {
  const two = (n: number) => String(n).padStart(2, "0");
  switch (dayOf(at, now)) {
    case "today":
      return `${at.getHours()}:${two(at.getMinutes())}`;
    case "yesterday":
      return t.yesterday;
    case "thisYear":
      return t.monthDay(String(at.getMonth() + 1), String(at.getDate()));
    case "earlier":
      return t.fullDate(String(at.getFullYear()), String(at.getMonth() + 1), String(at.getDate()));
  }
}

/** 现在的时间，每分钟更新一次，过了午夜「今天」「昨天」会跟着变。 */
function useMinute(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function Loading() {
  return (
    <div className="flex flex-col" aria-label={t.loading} aria-busy>
      {[0, 1].map((i) => (
        <div key={i} className="flex items-center gap-3 px-4 py-2.5">
          <Skeleton className="size-list-avatar shrink-0 rounded-full" />
          <div className="flex flex-1 flex-col gap-2">
            <Skeleton className="h-4 w-2/5" />
            <Skeleton className="h-3 w-3/4" />
          </div>
        </div>
      ))}
    </div>
  );
}
