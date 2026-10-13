// 礼物（GLOSSARY.md「礼物」「抽奖」「重置卡」）：礼物页读到的状态，和页上那几句话怎么拼。
// 抽奖次数每天在制作人当地 0 点发 1 次，最多攒 7 次，后端读取时补发；下次什么时候到账固定写「明天 0:00」。

import { api, json } from "@/lib/api";
import type { Tier } from "@/lib/affinity";
import { copy } from "@/i18n";

/** 一位角色现在的好感度，送礼时选人用：档位、是否冷却、冷却的解除时刻（ISO，不在冷却是 null）。 */
export type GiftCharacter = { id: string; tier: Tier; cooling: boolean; cooldown_until: string | null };

/** 背包里的一件礼物和它的件数。 */
export type Owned = { gift_id: string; count: number };

/** 读礼物状态接口给的。没开放（`open` 为 false）时照样给已有的次数、背包和重置卡，角色是空的。 */
export type GiftState = {
  open: boolean;
  draws: number;
  max_draws: number;
  backpack: Owned[];
  reset_cards: number;
  characters: GiftCharacter[];
};

/** 读礼物状态；后端读的时候按制作人当地的今天补发次数。 */
export async function getGiftState(): Promise<GiftState> {
  return json(await api("/api/gifts"));
}

/** 抽奖台小点下面那句：用完了、攒满了、平时三种。 */
export function drawNote(draws: number, max: number): string {
  const t = copy.gifts.draw.notes;
  if (draws <= 0) return t.none;
  if (draws >= max) return t.full(max);
  return t.usual(max);
}

/** 「还没有礼物」下面那句：有次数时叫人抽一次，没有时说明天再发。 */
export function emptyNote(draws: number): string {
  return draws > 0 ? copy.gifts.empty.withDraws : copy.gifts.empty.withoutDraws;
}
