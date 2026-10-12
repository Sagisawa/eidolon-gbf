import { describe, expect, it } from "vitest";

import type { AffinityChange } from "@/lib/affinity";
import type { Entry } from "@/lib/conversationLog";
import { linesOf } from "@/lib/messageLines";

const UP: AffinityChange = { up: true, tier_changed: false, tier: "trust", cooldown: false };

function user(key: string, at = "2026-09-28T01:00:00Z"): Entry {
  return { kind: "user", key, text: "在吗", at };
}

function her(key: string, affinity: AffinityChange | null = null, at = "2026-09-28T01:00:01Z"): Entry {
  return { kind: "character", key, segments: [{ ja: "はい", zh: "好的" }], pending: false, at, affinity };
}

const NOW = new Date("2026-09-28T12:00:00Z");

describe("linesOf", () => {
  it("好感度不可用时，存下的变化不出胶囊", () => {
    const lines = linesOf([user("m1"), her("m2", UP)], NOW, false);

    expect(lines.some((line) => line.kind === "cue")).toBe(false);
  });

  it("变化的胶囊挂在改变了好感度的那条回复后面；换了一天先放日期条；同一个人连着发、中间没有日期条或胶囊的算一组", () => {
    const lines = linesOf(
      [
        user("m1", "2026-09-27T01:00:00Z"),
        user("m2", "2026-09-28T01:00:00Z"),
        user("m3", "2026-09-28T01:00:02Z"),
        her("m4", UP, "2026-09-28T01:00:03Z"),
        her("m5", null, "2026-09-28T01:00:04Z"),
      ],
      NOW,
      true,
    );

    const groups = lines.flatMap((line) =>
      line.kind === "entry" ? [`${line.entry.key}${line.first ? "<" : ""}${line.last ? ">" : ""}`] : [line.kind],
    );
    expect(groups).toEqual(["day", "m1<>", "day", "m2<", "m3>", "m4<>", "cue", "m5<>"]);
    expect(lines.find((line) => line.kind === "cue")).toEqual({ kind: "cue", key: "cue-m4", change: UP });
  });
});
