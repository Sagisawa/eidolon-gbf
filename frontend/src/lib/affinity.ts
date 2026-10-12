// 好感度（GLOSSARY.md「好感度」「冷却」）：她对制作人的态度，用户只看到档位，看不到数值。
// 这里把读到的状态换成页首标识要显示的东西：哪种心形、写什么、读屏读什么；冷却中换成解除时刻。

import { api, json } from "@/lib/api";
import { copy } from "@/i18n";

export const TIERS = ["cold", "distant", "trust", "close", "intimate"] as const;
/** 冷淡、疏远、信任、亲近、亲密，从低到高。 */
export type Tier = (typeof TIERS)[number];

/** 读状态接口给的：档位，冷却中的解除时刻（ISO，不在冷却是 null）。 */
export type AffinityStatus = { tier: Tier; cooldown_until: string | null };

/** 五档的心形：冷淡 HeartOff、疏远 HeartCrack、信任空心、亲近半心（空心叠一层只露下半的实心）、亲密实心。 */
export type Heart = "off" | "crack" | "outline" | "half" | "filled";

const HEARTS: Record<Tier, Heart> = {
  cold: "off",
  distant: "crack",
  trust: "outline",
  close: "half",
  intimate: "filled",
};

export function heartOf(tier: Tier): Heart {
  return HEARTS[tier];
}

/** 页首标识：一档的心形加档名，或者冷却中的沙漏加解除时刻；`label` 是读屏读的名字。 */
export type Badge =
  | { kind: "tier"; tier: Tier; heart: Heart; text: string; label: string }
  | { kind: "cooldown"; until: string; text: string; label: string };

export function badgeOf(status: AffinityStatus, name: string, now: Date, timeZone: string): Badge {
  const t = copy.conversation.affinity;
  if (status.cooldown_until !== null) {
    const until = untilText(new Date(status.cooldown_until), now, timeZone);
    return { kind: "cooldown", until, text: until, label: t.cooling(name) };
  }
  const text = t.tiers[status.tier];
  return { kind: "tier", tier: status.tier, heart: heartOf(status.tier), text, label: t.label(text) };
}

/** 解除时刻按制作人的时区写成「今天 HH:MM」或「明天 HH:MM」（冷却最长 24 小时，不会更远）。 */
export function untilText(until: Date, now: Date, timeZone: string): string {
  const t = copy.conversation.affinity;
  const day = (at: Date) => new Intl.DateTimeFormat("en-CA", { timeZone }).format(at);
  const time = new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hourCycle: "h23",
    timeZone,
  }).format(until);
  return `${day(until) === day(now) ? t.today : t.tomorrow} ${time}`;
}

/** 她现在对这位用户的好感度；好感度不可用（没配判断模型或开关关着）时是 null。 */
export async function getAffinity(characterId: string): Promise<AffinityStatus | null> {
  return json(await api(`/api/characters/${encodeURIComponent(characterId)}/affinity`));
}
