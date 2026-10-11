// 自带密钥与限额的关系（GLOSSARY.md「限额」「自带密钥」）：回合或通话用到的、可以自带的服务
// 全都用了自带密钥的，才不计入限额。文字对话只用到 LLM；通话要 LLM、语音合成、语音识别三项。

import type { OwnService } from "@/lib/localOwnKeys";

/** 哪些用量不计入每小时限额：全部、只有文字对话，或都计入。 */
export type LimitExemption = "all" | "turns" | "none";

/** 自带了 `own` 这几项服务的 key 时，哪些用量不计入限额。 */
export function limitExemption(own: readonly OwnService[]): LimitExemption {
  if (!own.includes("llm")) return "none";
  return own.includes("tts") && own.includes("stt") ? "all" : "turns";
}
