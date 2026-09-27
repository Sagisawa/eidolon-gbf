// 自带密钥与限额的关系（CONTEXT.md「限额」「自带密钥」）：回合或通话用到的、可以自带的服务
// 全都用了自带密钥的，才不计入限额。文字对话只用到 LLM；通话要 LLM、语音合成、语音识别三项。

import type { OwnKeys } from "@/lib/api";

/** 哪些用量不计入每小时限额：全部、只有文字对话，或都计入。 */
export type LimitExemption = "all" | "turns" | "none";

export function limitExemption(exempt: OwnKeys["exempt"]): LimitExemption {
  if (exempt.calls) return "all";
  if (exempt.turns) return "turns";
  return "none";
}
