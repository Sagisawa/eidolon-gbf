import { describe, expect, it } from "vitest";

import { drawNote, emptyNote } from "@/lib/gifts";

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
