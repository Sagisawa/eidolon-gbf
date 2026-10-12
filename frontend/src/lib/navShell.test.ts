import { describe, expect, it } from "vitest";

import { departure, isInShell, showsShellCallBar } from "@/lib/navShell";

describe("在不在导航外壳里", () => {
  it.each([
    "/conversations",
    "/conversation/mano",
    "/conversation/mano?x=1",
    "/settings",
    "/settings?tab=own-keys",
    "/settings/own-keys",
  ])("%s 在外壳里", (href) => {
    expect(isInShell(href)).toBe(true);
  });

  it.each([
    "/",
    "/about",
    "/privacy",
    "/terms",
    "/memories",
    "/admin",
    "/admin/users/1",
    "/login",
    "/consent",
    "/conversation",
    "/conversations-old",
    "/settingsx",
    "/api/auth/link/google",
  ])("%s 在外壳外面", (href) => {
    expect(isInShell(href)).toBe(false);
  });

  it("别的网站上的网址不算，哪怕路径一样", () => {
    expect(isInShell("https://github.com/conversations")).toBe(false);
  });
});

describe("外壳顶上的通话条", () => {
  it("没在通话时哪里都没有", () => {
    expect(showsShellCallBar("/settings", null)).toBe(false);
    expect(showsShellCallBar("/conversations", null)).toBe(false);
  });

  it("通话中在设置、对话列表、别人的对话页上出现", () => {
    expect(showsShellCallBar("/settings", "mano")).toBe(true);
    expect(showsShellCallBar("/settings?tab=call", "mano")).toBe(true);
    expect(showsShellCallBar("/conversations", "mano")).toBe(true);
    expect(showsShellCallBar("/conversation/hiori", "mano")).toBe(true);
  });

  it("她自己的对话页上不出现：那里有页首下面那条", () => {
    expect(showsShellCallBar("/conversation/mano", "mano")).toBe(false);
  });

  it("外壳外面不出现", () => {
    expect(showsShellCallBar("/memories", "mano")).toBe(false);
    expect(showsShellCallBar("/admin", "mano")).toBe(false);
  });
});

describe("去某个网址时通话怎么样", () => {
  it("没在通话时哪里都直接走", () => {
    for (const to of ["/conversations", "/conversation/hiori", "/settings", "/admin", "/about", "/memories"])
      expect(departure(to, null), to).toBe("go");
  });

  it("通话中在外壳里换页，通话留着", () => {
    expect(departure("/conversations", "mano")).toBe("keep");
    expect(departure("/settings", "mano")).toBe("keep");
    expect(departure("/settings?tab=own-keys", "mano")).toBe("keep");
    expect(departure("/settings/call", "mano")).toBe("keep");
  });

  it("通话中回她自己的对话页，通话留着", () => {
    expect(departure("/conversation/mano", "mano")).toBe("keep");
  });

  it("通话中打开另一位角色的对话，先问再挂断", () => {
    expect(departure("/conversation/hiori", "mano")).toBe("ask");
  });

  it("通话中离开外壳，先问再挂断", () => {
    for (const to of ["/admin", "/about", "/privacy", "/terms", "/memories", "/", "/api/auth/link/google"])
      expect(departure(to, "mano"), to).toBe("ask");
  });
});
