import { describe, expect, it } from "vitest";
import { signInFailure, signInUrl } from "@/lib/signIn";

describe("signInFailure", () => {
  it("says nothing when signing in did not fail", () => {
    expect(signInFailure(null)).toBeNull();
    expect(signInFailure("")).toBeNull();
  });

  it("explains each reason the backend gives", () => {
    expect(signInFailure("too_new")).toContain("一年");
    expect(signInFailure("email_unverified")).toContain("验证");
    expect(signInFailure("banned")).toContain("封禁");
  });

  it("still says signing in failed for a reason it does not know", () => {
    expect(signInFailure("something_new")).toBe("登录失败，请重新登录。");
  });
});

describe("signInUrl", () => {
  it("starts at the backend, which sends the browser on to the provider", () => {
    expect(signInUrl("github")).toBe("/api/auth/github/start");
  });
});
