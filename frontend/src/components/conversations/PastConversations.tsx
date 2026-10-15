"use client";

import { useEffect, useState } from "react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Drawer, DrawerContent, DrawerDescription, DrawerHeader, DrawerTitle } from "@/components/ui/drawer";
import { Spinner } from "@/components/ui/spinner";
import { copy } from "@/i18n";
import { listConversations, type Character } from "@/lib/api";
import { pastDay, pastRows, type PastRow } from "@/lib/pastConversations";
import { cn } from "@/lib/utils";
import { herVars } from "@/theme/herVars";
import { EndedIcon } from "@/theme/icons";

import { PreviewText } from "./PreviewText";

const t = copy.conversation.past;

/**
 * 「历史对话」面板（DESIGN.md「Overlays」）：宽屏居中的 Dialog，窄屏底部的 Drawer，都用她的颜色。
 * 和她的所有对话一行一段，最新开的在上：当前对话第一行、标「当前」，空的历史对话不列（`pastRows`）。
 * 每行第一行是最后一次往来的日期（北京时间），她结束了的标「她结束了」；第二行是最后一句，写法同对话列表（`PreviewText`）。
 * 正在看的那一段（没在看历史对话时是当前对话）铺中性的 bg-muted。只有当前对话时下面一句说明。
 * 每次打开都重新读一遍列表，读的时候转圈。点一行交给 `onPick`。
 */
export function PastConversations({
  isOpen,
  onOpenChange,
  isWide,
  character,
  viewingId,
  onPick,
}: {
  isOpen: boolean;
  onOpenChange: (open: boolean) => void;
  isWide: boolean;
  character: Character;
  /** 正在看的历史对话；看着当前对话时是 null。 */
  viewingId: string | null;
  onPick: (row: PastRow) => void;
}) {
  const [rows, setRows] = useState<PastRow[] | "failed" | null>(null);
  const [attempt, setAttempt] = useState(0);

  // 打开时重读；收起时留着，收起的动画里内容不消失。
  useEffect(() => {
    if (!isOpen) return;
    let gone = false;
    setRows(null);
    listConversations(character.id).then(
      (listed) => !gone && setRows(pastRows(listed)),
      () => !gone && setRows("failed"),
    );
    return () => {
      gone = true;
    };
  }, [isOpen, character.id, attempt]);

  const now = new Date();
  const body =
    rows === null ? (
      <div className="flex justify-center p-6">
        <Spinner className="size-6 text-muted-foreground" aria-label={t.loading} />
      </div>
    ) : rows === "failed" ? (
      <div className="flex flex-col items-center gap-3 p-6">
        <p className="text-sm text-muted-foreground">{t.loadFailed}</p>
        <Button variant="outline" onClick={() => setAttempt((n) => n + 1)}>
          {t.retry}
        </Button>
      </div>
    ) : (
      <div className="flex flex-col">
        {rows.map((row) => {
          const isSelected = viewingId === null ? row.isCurrent : row.conversation.id === viewingId;
          return (
            <button
              key={row.conversation.id}
              type="button"
              aria-current={isSelected ? "true" : undefined}
              onClick={() => onPick(row)}
              className={cn(
                "flex min-h-14 w-full flex-col gap-0.5 rounded-lg px-3 py-2 text-left outline-none focus-visible:ring-3 focus-visible:ring-ring/50",
                isSelected ? "bg-muted" : "hover:bg-muted/60",
              )}
            >
              <span className="flex items-center gap-2">
                <span className="min-w-0 flex-1 truncate text-sm font-medium tabular-nums">
                  {pastDay(row.preview.at, now)}
                </span>
                {row.conversation.ended && (
                  <span className="flex shrink-0 items-center gap-1 text-meta text-muted-foreground">
                    <EndedIcon aria-hidden className="size-3" />
                    {t.ended}
                  </span>
                )}
                {row.isCurrent && <Badge variant="secondary">{t.current}</Badge>}
              </span>
              <span className="truncate text-preview text-muted-foreground tabular-nums">
                <PreviewText preview={row.preview} name={character.name} />
              </span>
            </button>
          );
        })}
        {rows.length === 1 && <p className="px-3 py-4 text-sm text-muted-foreground">{t.onlyCurrent}</p>}
      </div>
    );

  // 浮层渲染到对话子树外面，在内容上再注入一次她的颜色（DESIGN.md「The Scoped Colour Rule」）。
  const her = herVars(character.color);
  if (isWide) {
    return (
      <Dialog open={isOpen} onOpenChange={onOpenChange}>
        <DialogContent style={her} className="flex max-h-[80dvh] flex-col sm:max-w-md">
          <DialogHeader>
            <DialogTitle>{t.title}</DialogTitle>
            <DialogDescription>{t.description(character.name)}</DialogDescription>
          </DialogHeader>
          <div className="-mx-2 min-h-0 overflow-y-auto">{body}</div>
        </DialogContent>
      </Dialog>
    );
  }
  return (
    <Drawer open={isOpen} onOpenChange={onOpenChange} showSwipeHandle>
      <DrawerContent style={her}>
        <DrawerHeader>
          <DrawerTitle>{t.title}</DrawerTitle>
          <DrawerDescription>{t.description(character.name)}</DrawerDescription>
        </DrawerHeader>
        <div className="min-h-0 overflow-y-auto px-2 pb-4">{body}</div>
      </DrawerContent>
    </Drawer>
  );
}
