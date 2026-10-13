import { describe, expect, it } from "vitest";

import type { AffinityChange } from "@/lib/affinity";
import { drawNote, emptyNote, givenNote, shownGifts, type GiftInfo, type Given } from "@/lib/gifts";

describe("抽奖台那句话", () => {
  it("平时：明天再发，最多攒几次", () => {
    expect(drawNote(3, 7)).toBe("明天 0:00 再发 1 次，最多攒 7 次");
  });

  it("攒满了：抽掉之前不会再发", () => {
    expect(drawNote(7, 7)).toBe("已攒满 7 次，抽掉之前不会再发");
  });

  it("用完了：今天的已经抽了", () => {
    expect(drawNote(0, 7)).toBe("今天的已经抽了，明天 0:00 再发 1 次");
  });
});

describe("还没有礼物时的说明", () => {
  it("有次数时叫人抽一次", () => {
    expect(emptyNote(1)).toBe("抽一次，抽到的礼物会放在这里。");
  });

  it("没有次数时说明天再发", () => {
    expect(emptyNote(0)).toBe("明天 0:00 会发一次抽奖，抽到的礼物会放在这里。");
  });
});

describe("我的礼物按类别筛选", () => {
  const catalog: GiftInfo[] = [
    { id: "cake", name: "蛋糕", category: "food", rarity: "common", retired: false },
    { id: "tea", name: "红茶", category: "drink", rarity: "common", retired: false },
    { id: "cocoa", name: "热可可", category: "drink", rarity: "uncommon", retired: true },
    { id: "rose", name: "玫瑰", category: "flower", rarity: "rare", retired: false },
  ];
  const backpack = [
    { gift_id: "cake", count: 2 },
    { gift_id: "cocoa", count: 1 },
    { gift_id: "tea", count: 3 },
  ];

  it("全部：持有的每件，按背包的顺序，下架的照常列出", () => {
    expect(shownGifts(backpack, catalog, "all").map((h) => [h.gift.id, h.count])).toEqual([
      ["cake", 2],
      ["cocoa", 1],
      ["tea", 3],
    ]);
  });

  it("一类：只列这一类的", () => {
    expect(shownGifts(backpack, catalog, "drink").map((h) => h.gift.id)).toEqual(["cocoa", "tea"]);
  });

  it("这一类一件都没有时是空的", () => {
    expect(shownGifts(backpack, catalog, "flower")).toEqual([]);
  });

  it("目录里没有的不列", () => {
    expect(shownGifts([{ gift_id: "gone", count: 1 }], catalog, "all")).toEqual([]);
  });
});

describe("送出后底部提示的那句话", () => {
  // 时刻按东京时区写，测试不随跑测试的机器变。
  const now = new Date("2026-10-13T20:00:00+09:00");
  const up = (change: Partial<AffinityChange>): AffinityChange => ({
    up: true,
    tier_changed: false,
    tier: "trust",
    cooldown: false,
    thawed: false,
    ...change,
  });
  const given = (change: AffinityChange | null, cooldown_until: string | null = null): Given => ({
    conversation_id: "c1",
    change,
    affinity: { tier: change?.tier ?? "cold", cooling: cooldown_until !== null, cooldown_until },
    left: 0,
  });
  const note = (g: Given) => givenNote(g, "凛世", now, "Asia/Tokyo");

  it("有变化：就是变化胶囊的话", () => {
    expect(note(given(up({ tier_changed: true, tier: "close" })))).toBe("和凛世更近了一步：亲近");
  });

  it("冷却中送了还没解除：写解除时刻，和对话页的写法一样", () => {
    expect(note(given(null, "2026-10-14T05:30:00+09:00"))).toBe("凛世还没消气，明天 05:30 就会愿意说话了");
  });

  it("到顶了没有变化：只写已经送到", () => {
    expect(note(given(null))).toBe("已经送给凛世");
  });
});
