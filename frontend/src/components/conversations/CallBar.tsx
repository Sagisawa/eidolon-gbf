"use client";

import type { Ref } from "react";

import { copy } from "@/i18n";
import { showTime } from "@/lib/callTime";
import type { LiveCall } from "@/lib/liveConversation";
import { cn } from "@/lib/utils";
import { ForwardIcon } from "@/theme/icons";

import { useCallTime } from "./useCallTime";

/**
 * 通话层收起后，对话页首下面的通话条（DESIGN.md「Call layer」的「收起后：通话条」，取代上一版的便利贴）：
 * 40px 高、铺满对话栏宽，底是她的 `--her-call-deep`、白字；左边一个白色小圆点（呼叫中闪烁），
 * 接着「通话中 mm:ss」或「正在呼叫…」，右端「回到通话 ›」。整条是一个按钮，点了展开通话层；
 * 收起后焦点落在这里（useFocusBack），回车或空格再展开。
 */
export function CallBar({ call, onExpand, ref }: { call: LiveCall; onExpand: () => void; ref?: Ref<HTMLButtonElement> }) {
  const time = useCallTime(call);
  return (
    <button
      ref={ref}
      type="button"
      onClick={onExpand}
      className="flex h-call-bar w-full shrink-0 items-center gap-2 bg-her-call-deep px-4 text-left text-white outline-none focus-visible:ring-3 focus-visible:ring-white/60 focus-visible:ring-inset"
    >
      <span
        aria-hidden
        className={cn("size-2 shrink-0 rounded-full bg-white", !time && "motion-safe:animate-pulse")}
      />
      <span className="min-w-0 flex-1 truncate text-sm font-medium tabular-nums">
        {time ? copy.call.listConnected(showTime(time)) : copy.call.dialing}
      </span>
      <span className="flex shrink-0 items-center text-sm text-white/80">
        {copy.call.expand}
        <ForwardIcon aria-hidden className="size-4" />
      </span>
    </button>
  );
}
