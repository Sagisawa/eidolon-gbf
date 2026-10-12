import { describe, expect, it } from "vitest";

import { badgeOf, heartOf, TIERS, untilText } from "./affinity";

// 时刻都按东京时区写，测试不随跑测试的机器变。
const zone = "Asia/Tokyo";
const now = new Date("2026-10-13T20:00:00+09:00");

describe("heartOf：五档各一种心形", () => {
  it("冷淡 HeartOff、疏远 HeartCrack、信任空心、亲近半心、亲密实心", () => {
    expect(TIERS.map(heartOf)).toEqual(["off", "crack", "outline", "half", "filled"]);
  });
});

describe("badgeOf：页首标识显示什么、读屏读什么", () => {
  it("不在冷却：她的颜色的心形加档名，读作「你们的关系：{档名}」", () => {
    expect(badgeOf({ tier: "close", cooldown_until: null }, "凛世", now, zone)).toEqual({
      kind: "tier",
      tier: "close",
      heart: "half",
      text: "亲近",
      label: "你们的关系：亲近",
    });
  });

  it("冷却中：沙漏加解除时刻，读作「{角色名}现在不想说话」", () => {
    expect(badgeOf({ tier: "cold", cooldown_until: "2026-10-14T06:30:00+09:00" }, "凛世", now, zone)).toEqual({
      kind: "cooldown",
      until: "明天 06:30",
      text: "明天 06:30",
      label: "凛世现在不想说话",
    });
  });
});

describe("untilText：解除时刻按制作人的时区写成今天或明天加时刻", () => {
  it("同一天是今天", () => {
    expect(untilText(new Date("2026-10-13T23:05:00+09:00"), now, zone)).toBe("今天 23:05");
  });

  it("过了当地 0 点是明天", () => {
    expect(untilText(new Date("2026-10-14T00:00:00+09:00"), now, zone)).toBe("明天 00:00");
  });

  it("按给定的时区判断，不按 UTC 的日期", () => {
    // 东京已经是 14 日，UTC 还是 13 日。
    const tokyoMorning = new Date("2026-10-13T16:00:00Z");
    expect(untilText(new Date("2026-10-13T20:00:00Z"), tokyoMorning, zone)).toBe("今天 05:00");
    expect(untilText(new Date("2026-10-13T20:00:00Z"), now, zone)).toBe("明天 05:00");
  });
});
