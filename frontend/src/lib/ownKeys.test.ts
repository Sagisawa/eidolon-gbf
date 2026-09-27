import { describe, expect, it } from "vitest";
import { limitExemption } from "@/lib/ownKeys";

describe("limitExemption", () => {
  it("三项都自带时，文字对话和通话都不计入限额", () => {
    expect(limitExemption({ turns: true, calls: true })).toBe("all");
  });

  it("只自带 LLM 时，只有文字对话不计入限额", () => {
    expect(limitExemption({ turns: true, calls: false })).toBe("turns");
  });

  it("没有自带时，都计入限额", () => {
    expect(limitExemption({ turns: false, calls: false })).toBe("none");
  });
});
