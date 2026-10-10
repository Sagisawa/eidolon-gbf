import { afterEach, describe, expect, it, vi } from "vitest";

import { isSignedIn } from "@/lib/backend";

function backendAnswers(status: number) {
  const fetch = vi.fn(async (_url: string, _init: RequestInit) => new Response(null, { status }));
  vi.stubGlobal("fetch", fetch);
  return fetch;
}

describe("isSignedIn: whether the browser asking for a page has a live session", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it("is not, without asking the backend, when the browser has no session cookie", async () => {
    const fetch = backendAnswers(200);
    expect(await isSignedIn("theme=dark; eidolon_oauth_state=x")).toBe(false);
    expect(fetch).not.toHaveBeenCalled();
  });

  it("asks the backend with the browser's cookies when it has one", async () => {
    const fetch = backendAnswers(200);
    expect(await isSignedIn("theme=dark; eidolon_session=abc")).toBe(true);
    const [url, init] = fetch.mock.calls[0];
    expect(url).toMatch(/\/api\/account$/);
    expect(new Headers(init.headers).get("cookie")).toBe("theme=dark; eidolon_session=abc");
  });

  it("is signed in when the user has yet to agree to the terms", async () => {
    backendAnswers(428);
    expect(await isSignedIn("eidolon_session=abc")).toBe(true);
  });

  it("is not when the session has expired or ended", async () => {
    backendAnswers(401);
    expect(await isSignedIn("eidolon_session=old")).toBe(false);
  });

  it("is not when the backend cannot be reached", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("fetch failed"))));
    expect(await isSignedIn("eidolon_session=abc")).toBe(false);
  });
});
