import { describe, expect, it } from "vitest";
import { limitExemption } from "@/lib/ownKeys";

describe("limitExemption", () => {
  it("三项都自带时，文字对话和通话都不计入限额", () => {
    expect(limitExemption(["llm", "tts", "stt"])).toBe("all");
  });

  it("自带了 LLM 但语音没有都自带时，只有文字对话不计入限额", () => {
    expect(limitExemption(["llm", "tts"])).toBe("turns");
  });

  it("没有自带 LLM 时，都计入限额", () => {
    expect(limitExemption(["tts", "stt"])).toBe("none");
  });
});
