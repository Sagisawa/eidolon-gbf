import { describe, expect, it } from "vitest";

import { currentNavItem, departure, isInShell, isTyping, navDestination, showsShellCallBar } from "@/lib/navShell";

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

describe("导航栏和 dock 的当前项", () => {
  it.each([
    ["/conversations", "conversations"],
    ["/conversation/mano", "conversations"],
    ["/settings", "settings"],
    ["/settings?tab=call", "settings"],
    ["/settings/own-keys", "settings"],
  ] as const)("%s 的当前项是 %s", (href, item) => {
    expect(currentNavItem(href)).toBe(item);
  });

  it.each(["/memories", "/admin", "/about", "/conversations-old", "/settingsx", "/"])("%s 没有当前项", (href) => {
    expect(currentNavItem(href)).toBeNull();
  });
});

describe("点导航栏、dock 里的一项去哪", () => {
  it("点别的项，去那一项的第一级", () => {
    expect(navDestination("settings", "/conversations")).toBe("/settings");
    expect(navDestination("settings", "/conversation/mano")).toBe("/settings");
    expect(navDestination("conversations", "/settings")).toBe("/conversations");
    expect(navDestination("conversations", "/settings/own-keys")).toBe("/conversations");
  });

  it("在二级页面上再点当前那一项，回到这一项的第一级", () => {
    expect(navDestination("conversations", "/conversation/mano")).toBe("/conversations");
    expect(navDestination("settings", "/settings/own-keys")).toBe("/settings");
  });

  it("已经在第一级时再点当前那一项，不动", () => {
    expect(navDestination("conversations", "/conversations")).toBeNull();
    expect(navDestination("settings", "/settings")).toBeNull();
    expect(navDestination("settings", "/settings?tab=call")).toBeNull();
  });

  it("通话中点导航栏去的地方都在外壳里，通话留着", () => {
    for (const [item, from] of [
      ["settings", "/conversation/mano"],
      ["conversations", "/conversation/mano"],
      ["conversations", "/settings"],
    ] as const) {
      const to = navDestination(item, from);
      expect(to && departure(to, "mano"), `${item} 从 ${from}`).toBe("keep");
    }
  });
});

describe("手机上在打字（dock 藏起来）", () => {
  it.each([
    ["textarea", { tagName: "TEXTAREA" }],
    ["搜索框", { tagName: "INPUT", type: "search" }],
    ["文字框", { tagName: "INPUT", type: "text" }],
    ["可编辑元素", { tagName: "DIV", isContentEditable: true }],
  ])("焦点在%s上算", (_, focused) => {
    expect(isTyping(focused)).toBe(true);
  });

  it.each([
    ["没有焦点", null],
    ["勾选框", { tagName: "INPUT", type: "checkbox" }],
    ["按钮", { tagName: "BUTTON" }],
    ["链接", { tagName: "A" }],
  ])("%s不算", (_, focused) => {
    expect(isTyping(focused)).toBe(false);
  });
});
