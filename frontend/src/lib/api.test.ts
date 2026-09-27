import { describe, expect, it } from "vitest";
import { CONSENT_REQUIRED, redirectFor } from "@/lib/api";

describe("redirectFor", () => {
  it("sends a browser that is not signed in to sign in", () => {
    expect(redirectFor(401)).toBe("/login");
  });

  it("sends a user who has not agreed to the terms to agree first", () => {
    expect(redirectFor(CONSENT_REQUIRED)).toBe("/consent");
  });

  it("lets every other response through to the page", () => {
    for (const status of [200, 204, 403, 404, 422, 429, 500, 503]) {
      expect(redirectFor(status)).toBeNull();
    }
  });
});
