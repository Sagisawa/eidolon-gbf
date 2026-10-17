"use client";

import { useState } from "react";

import { Dialog, DialogContent, DialogTitle } from "@/components/ui/dialog";
import { Spinner } from "@/components/ui/spinner";
import { copy } from "@/i18n";
import { photoImageUrl, type Photo } from "@/lib/api";
import { PhotoIcon } from "@/theme/icons";

const t = copy.conversation.photo;

/**
 * 她那条回复的第一块：她发来的照片（GLOSSARY.md「照片」，DESIGN.md「Chat bubbles · 照片」）。
 * 宽 192px，按 832×1216 等比；生成中是同样大小的占位，到了直接换上，位置不跳。点开整屏放大。
 * 没发出来的不在这里显示。
 */
export function PhotoBlock({ photo }: { photo: Photo }) {
  const [viewing, setViewing] = useState(false);
  if (photo.status === "pending") {
    return (
      <div
        role="status"
        aria-label={t.pending}
        className="flex aspect-[832/1216] w-48 flex-col items-center justify-center gap-2 rounded-bubble bg-foreground/8 text-muted-foreground"
      >
        <PhotoIcon aria-hidden className="size-6 motion-safe:animate-pulse" />
        <Spinner className="size-4" />
      </div>
    );
  }
  if (photo.status !== "ready") return null;
  const src = photoImageUrl(photo.id);
  return (
    <>
      <button
        type="button"
        aria-label={t.open}
        onClick={() => setViewing(true)}
        className="w-48 overflow-hidden rounded-bubble outline-none focus-visible:ring-3 focus-visible:ring-ring/50"
      >
        <img src={src} alt={t.sent} width={832} height={1216} className="aspect-[832/1216] w-full object-cover" />
      </button>
      <Dialog open={viewing} onOpenChange={setViewing}>
        <DialogContent variant="viewer">
          <DialogTitle className="sr-only">{t.viewer}</DialogTitle>
          <img src={src} alt={t.sent} className="max-h-full max-w-full rounded-lg object-contain" />
        </DialogContent>
      </Dialog>
    </>
  );
}
