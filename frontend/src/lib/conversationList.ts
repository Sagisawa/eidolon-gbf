// 消息列表每一行的内容：她最新一次对话的最后一句和时间（spec「信息架构」）。
// 只给出结构，文字由界面按当前语言拼（`copy.conversationList`）。

import type { LatestConversation } from "@/lib/api";

/** 列表里的一行预览。`from` 为 null 表示对话已经开了但还没有话。 */
export type Preview = { from: "her" | "you" | null; text: string; at: string };

/** 她说的显示字幕（没有字幕时退回日语原文），自己说的原样；从没聊过的角色没有预览。 */
export function previewOf(latest: LatestConversation | undefined): Preview | null {
  if (!latest) return null;
  const last = latest.last_message;
  if (!last) return { from: null, text: "", at: latest.created_at };
  if (last.role === "user") return { from: "you", text: last.text ?? "", at: last.created_at };
  return { from: "her", text: last.zh || last.ja || "", at: last.created_at };
}

/** 时间按哪一种写法显示：今天只写时刻，昨天写「昨天」，今年写月日，更早写年月日。按本地日历算。 */
export type Day = "today" | "yesterday" | "thisYear" | "earlier";

export function dayOf(at: Date, now: Date): Day {
  const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const startOfYesterday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 1);
  if (at >= startOfToday) return "today";
  if (at >= startOfYesterday) return "yesterday";
  if (at.getFullYear() === now.getFullYear()) return "thisYear";
  return "earlier";
}
