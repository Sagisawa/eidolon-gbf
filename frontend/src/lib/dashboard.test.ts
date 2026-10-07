import { describe, expect, it } from "vitest";

import {
  countTicks,
  formatCount,
  formatMs,
  formatShare,
  formatUsage,
  healthStatus,
  isDashboardRange,
  labelledStretches,
  stretchLabel,
  stretchSpan,
} from "@/lib/dashboard";

/** An ISO time at a local hour, as the backend sends a stretch's start. */
const local = (month: number, day: number, hour: number) =>
  new Date(2026, month - 1, day, hour).toISOString();

describe("isDashboardRange", () => {
  it("只认后端给的四种时间范围", () => {
    for (const [value, known] of [["24h", true], ["90d", true], ["1y", false], ["", false]] as const)
      expect(isDashboardRange(value), value).toBe(known);
  });
});

describe("number formats", () => {
  it("counts are comma'd, and in 万 from ten thousand on", () => {
    const cases: [number, string][] = [[0, "0"], [1284, "1,284"], [12_900, "1.3万"], [40_000, "4万"]];
    for (const [n, shown] of cases) expect(formatCount(n), String(n)).toBe(shown);
  });

  it("shares are to one decimal, a sliver is never 0, and of nothing there is none", () => {
    const cases: [number, number, string][] = [
      [1, 4, "25%"], [1, 3, "33.3%"], [0, 5, "0%"], [1, 5000, "<0.1%"], [0, 0, "—"],
    ];
    for (const [part, whole, shown] of cases) expect(formatShare(part, whole), `${part}/${whole}`).toBe(shown);
  });

  it("durations are in ms under a second, then in seconds", () => {
    const cases: [number | null, string][] = [[null, "—"], [842.4, "842 ms"], [1250, "1.3 s"], [3000, "3 s"]];
    for (const [ms, shown] of cases) expect(formatMs(ms), String(ms)).toBe(shown);
  });
});

describe("healthStatus", () => {
  it("goes by the error rate, and says nothing without calls", () => {
    const cases: [number, number, ReturnType<typeof healthStatus>][] = [
      [0, 0, "idle"], [100, 0.01, "ok"], [100, 0.05, "degraded"], [100, 0.5, "failing"],
    ];
    for (const [calls, rate, status] of cases)
      expect(healthStatus({ calls, error_rate: rate }), `${calls} ${rate}`).toBe(status);
  });
});

describe("formatUsage", () => {
  it("shows input and output where billed apart, input alone otherwise, and the calls that did not say", () => {
    expect(formatUsage([{ unit: "tokens", input: 12_345, output: 678 }], 0)).toBe(
      "输入 1.2万 · 输出 678 tokens",
    );
    expect(formatUsage([{ unit: "tokens", input: 300, output: null }], 2)).toBe("300 tokens；2 次未知");
    expect(formatUsage([], 0)).toBe("—");
  });
});

describe("stretches of the trend", () => {
  it("are labelled by hour, by day, or by day at midnight for six-hour stretches", () => {
    expect(stretchLabel(local(10, 7, 14), "hour")).toBe("14:00");
    expect(stretchLabel(local(10, 7, 6), "6h")).toBe("06:00");
    expect(stretchLabel(local(10, 7, 0), "6h")).toBe("10月7日");
    expect(stretchLabel(local(10, 7, 0), "day")).toBe("10月7日");
  });

  it("span their whole length in the tooltip", () => {
    expect(stretchSpan(local(10, 7, 14), "hour")).toBe("10月7日 14:00–15:00");
    expect(stretchSpan(local(10, 7, 18), "6h")).toBe("10月7日 18:00–00:00");
    expect(stretchSpan(local(10, 7, 0), "day")).toBe("10月7日");
  });

  it("label at most so many, always the latest", () => {
    expect([...labelledStretches(24, 6)].sort((a, b) => a - b)).toEqual([3, 7, 11, 15, 19, 23]);
    expect(labelledStretches(4, 6).size).toBe(4);
  });
});

describe("countTicks", () => {
  it("are whole, clean steps from 0 past the largest count", () => {
    const cases: [number, number[]][] = [
      [0, [0, 1]],
      [3, [0, 1, 2, 3]],
      [37, [0, 10, 20, 30, 40]],
      [1200, [0, 500, 1000, 1500]],
    ];
    for (const [max, ticks] of cases) expect(countTicks(max), String(max)).toEqual(ticks);
  });
});
