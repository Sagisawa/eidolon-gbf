// 礼物（GLOSSARY.md「礼物」「抽奖」「重置卡」）：礼物页读到的状态，和页上那几句话怎么拼、我的礼物怎么筛。
// 抽奖次数每天在制作人当地 0 点发 1 次，最多攒 7 次，后端读取时补发；下次什么时候到账固定写「明天 0:00」。

import { api, json } from "@/lib/api";
import type { Tier } from "@/lib/affinity";
import { copy } from "@/i18n";

/** 礼物的类别：吃的、饮品、花草、小物件。 */
export type Category = "food" | "drink" | "flower" | "trinket";

/** 稀有度：普通、少见、稀有。 */
export type Rarity = "common" | "uncommon" | "rare";

/** 目录里的一件礼物。下架的（`retired`）不再从抽奖里出，持有的照样显示、照样能送。不带谁喜欢它。 */
export type GiftInfo = { id: string; name: string; category: Category; rarity: Rarity; retired: boolean };

/** 一位角色现在的好感度，送礼时选人用：档位、是否冷却、冷却的解除时刻（ISO，不在冷却是 null）。 */
export type GiftCharacter = { id: string; tier: Tier; cooling: boolean; cooldown_until: string | null };

/** 背包里的一件礼物和它的件数。 */
export type Owned = { gift_id: string; count: number };

/** 读礼物状态接口给的。没开放（`open` 为 false）时照样给已有的次数、背包和重置卡，角色是空的。 */
export type GiftState = {
  open: boolean;
  draws: number;
  max_draws: number;
  /** 只列持有的，按目录的顺序。 */
  backpack: Owned[];
  reset_cards: number;
  characters: GiftCharacter[];
};

/** 抽一次抽到的：一件礼物，或一张重置卡。 */
export type Drawn = { kind: "gift"; gift_id: string } | { kind: "reset_card" };

/** 抽奖接口给的：按抽出的顺序排的结果，和抽完还剩几次。 */
export type DrawResult = { drawn: Drawn[]; draws: number };

/** 读礼物状态；后端读的时候按制作人当地的今天补发次数。 */
export async function getGiftState(): Promise<GiftState> {
  return json(await api("/api/gifts"));
}

/** 读礼物目录（含下架的）。 */
export async function getGiftCatalog(): Promise<GiftInfo[]> {
  return json(await api("/api/gifts/catalog"));
}

/** 抽一次，或 `all` 时把攒下的全部抽完。没开放时抛 `giftsClosed` 的 ApiError。 */
export async function drawGifts(all: boolean): Promise<DrawResult> {
  return json(
    await api("/api/gifts/draws", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ all }),
    }),
  );
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

/** 我的礼物的筛选：全部，或某一类。 */
export type GiftFilter = "all" | Category;

export const GIFT_FILTERS: readonly GiftFilter[] = ["all", "food", "drink", "flower", "trinket"];

/** 持有的一件礼物和件数。 */
export type Held = { gift: GiftInfo; count: number };

/** 我的礼物网格里列的：背包里属于 `filter` 这一类的，按背包的顺序；目录里找不到的不列。 */
export function shownGifts(backpack: Owned[], catalog: GiftInfo[], filter: GiftFilter): Held[] {
  const byId = new Map(catalog.map((g) => [g.id, g]));
  return backpack.flatMap(({ gift_id, count }) => {
    const gift = byId.get(gift_id);
    return gift && (filter === "all" || gift.category === filter) ? [{ gift, count }] : [];
  });
}
