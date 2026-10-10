import { describe, expect, it } from "vitest";

import type { LatestConversation } from "@/lib/api";
import { arrange, dayOf, previewOf } from "@/lib/conversationList";

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

describe("arrange", () => {
  // 接口给的顺序，即原作的偶像顺序。
  const characters = ["mano", "hiori", "meguru", "kogane", "mamimi"].map((id) => ({ id }));

  /** 她最新的对话：`opened` 时开的，最后一句在 `lastAt`（null 表示还没有话）。 */
  function talked(id: string, opened: string, lastAt: string | null = opened): LatestConversation {
    return {
      character_id: id,
      conversation_id: `c-${id}`,
      created_at: opened,
      last_message: lastAt === null ? null : { role: "user", text: "早", ja: null, zh: null, created_at: lastAt },
    };
  }

  function order(...summaries: LatestConversation[]): string[] {
    const latest = Object.fromEntries(summaries.map((s) => [s.character_id, s]));
    return arrange(characters, latest).map((c) => c.id);
  }

  it("聊过的按最后一句从新到旧排，没聊过的在后面、保持原顺序", () => {
    expect(
      order(
        talked("meguru", "2026-10-01T00:00:00Z", "2026-10-01T09:00:00Z"),
        talked("mamimi", "2026-10-01T00:00:00Z", "2026-10-02T09:00:00Z"),
        talked("hiori", "2026-09-01T00:00:00Z", "2026-09-30T23:00:00Z"),
      ),
    ).toEqual(["mamimi", "meguru", "hiori", "mano", "kogane"]);
  });

  it("开了新对话还没说话的，按开对话的时间算", () => {
    expect(
      order(
        talked("mano", "2026-10-01T00:00:00Z", "2026-10-01T09:00:00Z"),
        talked("kogane", "2026-10-01T10:00:00Z", null),
      ),
    ).toEqual(["kogane", "mano", "hiori", "meguru", "mamimi"]);
  });

  it("时间相同时按原顺序", () => {
    expect(
      order(talked("kogane", "2026-10-01T00:00:00Z"), talked("hiori", "2026-10-01T00:00:00Z")),
    ).toEqual(["hiori", "kogane", "mano", "meguru", "mamimi"]);
  });

  it("时间的写法不同也按实际先后比", () => {
    expect(
      order(talked("hiori", "2026-10-01T09:00:00+09:00"), talked("kogane", "2026-10-01T01:00:00Z")),
    ).toEqual(["kogane", "hiori", "mano", "meguru", "mamimi"]);
  });

  it("一位都没聊过时就是原顺序", () => {
    expect(order()).toEqual(["mano", "hiori", "meguru", "kogane", "mamimi"]);
  });

  it("摘要里有配置中已经不存在的角色时不出错，也不多出一行", () => {
    expect(order(talked("gone", "2026-10-02T00:00:00Z"), talked("meguru", "2026-10-01T00:00:00Z"))).toEqual([
      "meguru", "mano", "hiori", "kogane", "mamimi",
    ]);
  });
});
