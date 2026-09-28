import { describe, expect, it } from "vitest";

import type { LatestConversation } from "@/lib/api";
import { dayOf, previewOf } from "@/lib/conversationList";

function latest(last: LatestConversation["last_message"]): LatestConversation {
  return {
    character_id: "mano",
    conversation_id: "c1",
    created_at: "2026-09-28T01:00:00Z",
    last_message: last,
  };
}

describe("previewOf", () => {
  it("她的最后一句显示字幕，时间取这句话的", () => {
    const preview = previewOf(
      latest({ role: "character", text: null, ja: "ほわっ", zh: "哇", created_at: "2026-09-28T02:00:00Z" }),
    );

    expect(preview).toEqual({ from: "her", text: "哇", at: "2026-09-28T02:00:00Z" });
  });

  it("没有字幕时退回她的日语原文", () => {
    const preview = previewOf(
      latest({ role: "character", text: null, ja: "えっと", zh: "", created_at: "2026-09-28T02:00:00Z" }),
    );

    expect(preview?.text).toBe("えっと");
  });

  it("自己的话标成制作人说的", () => {
    const preview = previewOf(
      latest({ role: "user", text: "晚安", ja: null, zh: null, created_at: "2026-09-28T02:00:00Z" }),
    );

    expect(preview).toEqual({ from: "you", text: "晚安", at: "2026-09-28T02:00:00Z" });
  });

  it("刚开的新对话没有最后一句，时间是对话开始的时间", () => {
    expect(previewOf(latest(null))).toEqual({ from: null, text: "", at: "2026-09-28T01:00:00Z" });
  });

  it("从没聊过的角色没有预览", () => {
    expect(previewOf(undefined)).toBeNull();
  });
});

describe("dayOf", () => {
  // 按本地日历算，不按相差多少小时算。
  const now = new Date(2026, 8, 28, 0, 30);

  it.each([
    [new Date(2026, 8, 28, 0, 5), "today"],
    [new Date(2026, 8, 27, 23, 50), "yesterday"],
    [new Date(2026, 8, 26, 12, 0), "thisYear"],
    [new Date(2026, 0, 1, 0, 0), "thisYear"],
    [new Date(2025, 11, 31, 23, 0), "earlier"],
  ] as const)("%s → %s", (at, day) => {
    expect(dayOf(at, now)).toBe(day);
  });

  it("年初的「昨天」跨了年也还是昨天", () => {
    expect(dayOf(new Date(2025, 11, 31, 22, 0), new Date(2026, 0, 1, 8, 0))).toBe("yesterday");
  });
});
