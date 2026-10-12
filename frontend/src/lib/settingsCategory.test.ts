import { describe, expect, it } from "vitest";

import {
  SETTINGS_CATEGORIES,
  SETTINGS_GROUPS,
  settingsCategory,
  settingsHref,
  settingsRedirect,
  shownCategory,
} from "@/lib/settingsCategory";

describe("设置的类别", () => {
  it("一级六项分四组：档案、记忆／通话、自带密钥／登录与数据／关于", () => {
    expect(SETTINGS_GROUPS).toEqual([["profile", "memories"], ["call", "own-keys"], ["sign-in"], ["about"]]);
    expect(SETTINGS_CATEGORIES).toEqual(["profile", "memories", "call", "own-keys", "sign-in", "about"]);
  });
});

describe("路径和类别互转", () => {
  it("每一类一个路径，读回来还是这一类", () => {
    for (const category of SETTINGS_CATEGORIES) {
      expect(settingsHref(category), category).toBe(`/settings/${category}`);
      expect(settingsCategory(settingsHref(category)), category).toBe(category);
    }
  });

  it.each(["/settings", "/settings/xxx", "/settings/profile/x", "/conversations", "/memories"])(
    "%s 不是哪一类的二级页面",
    (path) => {
      expect(settingsCategory(path)).toBeNull();
    },
  );

  it("只打开 /settings 时右栏显示档案，二级页面显示它自己那一类", () => {
    expect(shownCategory("/settings")).toBe("profile");
    expect(shownCategory("/settings/call")).toBe("call");
  });
});

describe("旧地址和不认识的地址换成哪个路径", () => {
  it.each([
    ["/settings?tab=own-keys", "/settings/own-keys"],
    ["/settings?tab=profile", "/settings/profile"],
    ["/memories", "/settings/memories"],
  ])("旧地址 %s 换成 %s", (from, to) => {
    expect(settingsRedirect(from)).toBe(to);
  });

  it("换的时候留着地址里别的参数", () => {
    expect(settingsRedirect("/settings?tab=sign-in&linked=google")).toBe("/settings/sign-in?linked=google");
  });

  it.each(["/settings?tab=xxx", "/settings?tab=", "/settings/xxx", "/settings/profile/x"])(
    "不认识的 %s 回到 /settings",
    (from) => {
      expect(settingsRedirect(from)).toBe("/settings");
    },
  );

  it.each(["/settings", "/settings/own-keys", "/settings/sign-in?linked=google", "/conversations", "/settingsx"])(
    "%s 不用换",
    (href) => {
      expect(settingsRedirect(href)).toBeNull();
    },
  );
});
