import { describe, expect, it } from "vitest";

import {
  banAction,
  deployerLlm,
  deployerLlmAllowable,
  describeLimit,
  describeLimits,
  limitDraft,
  limitsInput,
  headerSort,
  pageOffset,
  usageRows,
  describeCount,
  type AdminUser,
  type AdminUserLimits,
  type UserLimit,
} from "@/lib/adminUsers";

const USER: AdminUser = {
  id: "u1",
  name: "octo",
  sign_in_methods: [],
  created_at: "2026-10-01T00:00:00+00:00",
  last_active_at: null,
  banned: false,
  is_admin: false,
  limits: null,
  usage_24h: { turns: 0, calls: 0 },
};

describe("banAction", () => {
  it("offers to ban a user, to lift a ban, and nothing for an admin", () => {
    expect(banAction(USER)).toBe("ban");
    expect(banAction({ ...USER, banned: true })).toBe("unban");
    expect(banAction({ ...USER, is_admin: true })).toBeNull();
  });
});

describe("pageOffset", () => {
  it("skips the users of the pages before", () => {
    expect(pageOffset(1)).toBe(0);
    expect(pageOffset(3)).toBe(100);
  });
});

describe("describeLimit", () => {
  it("says what a user's own limit is: the deployment's, unlimited, own keys only, or a number", () => {
    expect(describeLimit(null)).toBe("跟随全站");
    expect(describeLimit("unlimited")).toBe("不限");
    expect(describeLimit(0)).toBe("只能用自带密钥");
    expect(describeLimit(3)).toBe("每小时 3 次");
  });
});

describe("limitDraft and limitsInput", () => {
  it("round-trips each kind of limit through the editor", () => {
    for (const limit of [null, "unlimited", 0, 5] as const) {
      expect(limitsInput(limitDraft(limit), limitDraft(5), false), String(limit)).toEqual({
        input: { turns_per_hour: limit, calls_per_hour: 5, deployer_llm_allowed: false },
      });
    }
  });

  it("keeps own keys only apart from a number: 0 is never typed in", () => {
    expect(limitDraft(0)).toEqual({ choice: "own_keys", count: null });
    expect(limitsInput({ choice: "number", count: 0 }, limitDraft(5), false)).toEqual({
      problems: [{ field: "turns", reason: "count" }],
    });
  });

  it("names why there is nothing to save: both follow the deployment, or a number is chosen but not given", () => {
    expect(limitsInput(limitDraft(null), limitDraft(null), false)).toEqual({
      problems: [{ field: "turns", reason: "needsOne" }],
    });
    expect(limitsInput({ choice: "number", count: null }, limitDraft(null), false)).toEqual({
      problems: [{ field: "turns", reason: "count" }],
    });
    expect(limitsInput({ choice: "number", count: null }, { choice: "number", count: null }, false)).toEqual({
      problems: [
        { field: "turns", reason: "count" },
        { field: "calls", reason: "count" },
      ],
    });
  });

  it("saves letting the user use the deployer's LLM alone, both limits following the deployment", () => {
    expect(limitsInput(limitDraft(null), limitDraft(null), true)).toEqual({
      input: { turns_per_hour: null, calls_per_hour: null, deployer_llm_allowed: true },
    });
  });

  it("lets no one use the deployer's LLM when both limits leave them their own keys only, where it would do nothing", () => {
    expect(deployerLlmAllowable(limitDraft(0), limitDraft(0))).toBe(false);
    expect(limitsInput(limitDraft(0), limitDraft(0), true)).toEqual({
      input: { turns_per_hour: 0, calls_per_hour: 0, deployer_llm_allowed: false },
    });
    // Calls on the deployment's limit still use the deployer's LLM.
    expect(deployerLlmAllowable(limitDraft(0), limitDraft(null))).toBe(true);
    expect(limitsInput(limitDraft(0), limitDraft(null), true)).toEqual({
      input: { turns_per_hour: 0, calls_per_hour: null, deployer_llm_allowed: true },
    });
  });
});

describe("deployerLlm", () => {
  const limits = (turns: UserLimit, calls: UserLimit, deployer_llm_allowed: boolean): AdminUserLimits => ({
    turns_per_hour: turns,
    calls_per_hour: calls,
    note: null,
    updated_at: "2026-10-11T00:00:00+00:00",
    deployer_llm_allowed,
  });

  it("says whether the user may use the deployer's LLM, and when it does nothing for their own limits of 0", () => {
    expect(deployerLlm(null)).toBe("不可以");
    expect(deployerLlm(limits(5, null, false))).toBe("不可以");
    expect(deployerLlm(limits(null, null, true))).toBe("可以");
    expect(deployerLlm(limits(0, 0, true))).toBe("可以，但两项都只能用自带密钥，不起作用");
  });

  it("adds it to the limits' summary only when the user may", () => {
    expect(describeLimits(limits(5, null, false))).toBe("回合 每小时 5 次 · 通话 跟随全站");
    expect(describeLimits(limits(null, null, true))).toBe("回合 跟随全站 · 通话 跟随全站 · 可以用部署者的 LLM");
  });
});

describe("headerSort", () => {
  it("sorts by a usage column, most first, and back to newest when its header is clicked again", () => {
    expect(headerSort("newest", "turns")).toBe("turns");
    expect(headerSort("turns", "calls")).toBe("calls");
    expect(headerSort("turns", "turns")).toBe("newest");
  });
});

describe("describeCount", () => {
  it("gives the total, and on whose keys when there are any", () => {
    expect(describeCount({ deployer: 0, own_keys: 0 })).toEqual({ total: "0", split: null });
    expect(describeCount({ deployer: 3, own_keys: 2 })).toEqual({
      total: "5",
      split: "部署者 3 · 自带密钥 2",
    });
  });
});

describe("usageRows", () => {
  it("has a row for turns, calls and rejections, each with the three ranges", () => {
    const counted = (deployer: number, own_keys: number) => ({ deployer, own_keys });
    const range = (n: number) => ({ turns: counted(n, 0), calls: counted(0, n), rejected: counted(0, 0) });
    const rows = usageRows({ "24h": range(1), "7d": range(2), "30d": range(3) });

    expect(rows.map((row) => [row.what, row.label])).toEqual([
      ["turns", "回合"],
      ["calls", "通话"],
      ["rejected", "被拒绝"],
    ]);
    expect([rows[0]["24h"], rows[0]["7d"], rows[0]["30d"]]).toEqual([counted(1, 0), counted(2, 0), counted(3, 0)]);
    expect(rows[1]["30d"]).toEqual(counted(0, 3));
  });
});
