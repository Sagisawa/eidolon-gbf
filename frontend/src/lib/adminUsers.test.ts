import { describe, expect, it } from "vitest";

import { banAction, broughtKeys, pageOffset, type AdminUser } from "@/lib/adminUsers";

const USER: AdminUser = {
  id: "u1",
  name: "octo",
  sign_in_methods: [],
  created_at: "2026-10-01T00:00:00+00:00",
  last_active_at: null,
  banned: false,
  is_admin: false,
  own_keys: { llm: false, tts: false, stt: false },
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
