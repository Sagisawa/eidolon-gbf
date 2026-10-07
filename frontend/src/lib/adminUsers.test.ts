import { describe, expect, it } from "vitest";

import {
  banAction,
  broughtKeys,
  describeLimit,
  limitDraft,
  limitsInput,
  pageOffset,
  type AdminUser,
} from "@/lib/adminUsers";

const USER: AdminUser = {
  id: "u1",
  name: "octo",
  sign_in_methods: [],
  created_at: "2026-10-01T00:00:00+00:00",
  last_active_at: null,
  banned: false,
  is_admin: false,
  own_keys: { llm: false, tts: false, stt: false },
  limits: null,
};

describe("banAction", () => {
  it("offers to ban a user, to lift a ban, and nothing for an admin", () => {
    expect(banAction(USER)).toBe("ban");
    expect(banAction({ ...USER, banned: true })).toBe("unban");
    expect(banAction({ ...USER, is_admin: true })).toBeNull();
  });
});

describe("broughtKeys", () => {
  it("lists the services the user brought their own keys for, in the settings page's order", () => {
    expect(broughtKeys({ llm: false, tts: false, stt: false })).toEqual([]);
    expect(broughtKeys({ stt: true, llm: true, tts: false })).toEqual(["llm", "stt"]);
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
      expect(limitsInput(limitDraft(limit), limitDraft(5)), String(limit)).toEqual({
        turns_per_hour: limit,
        calls_per_hour: 5,
      });
    }
  });

  it("has nothing to save when both follow the deployment or a number is chosen but not given", () => {
    expect(limitsInput(limitDraft(null), limitDraft(null))).toBeNull();
    expect(limitsInput({ choice: "number", count: null }, limitDraft(null))).toBeNull();
  });
});
