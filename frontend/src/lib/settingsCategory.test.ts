import { describe, expect, it } from "vitest";

import { settingsCategory, settingsHref, settingsRedirect, shownCategory } from "@/lib/settingsCategory";

describe("路径和类别互转", () => {
  it("一类的路径读回来还是这一类", () => {
    expect(settingsHref("own-keys")).toBe("/settings/own-keys");
    expect(settingsCategory(settingsHref("own-keys"))).toBe("own-keys");
  });

  it.each(["/settings", "/settings/xxx"])("%s 不是哪一类的二级页面", (path) => {
    expect(settingsCategory(path)).toBeNull();
  });

  it("只打开 /settings 时右栏显示档案，二级页面显示它自己那一类", () => {
    expect(shownCategory("/settings")).toBe("profile");
    expect(shownCategory("/settings/call")).toBe("call");
  });
});

describe("旧地址和不认识的地址换成哪个路径", () => {
  it.each([
    ["/settings?tab=own-keys", "/settings/own-keys"],
    ["/memories", "/settings/memories"],
  ])("旧地址 %s 换成 %s", (from, to) => {
    expect(settingsRedirect(from)).toBe(to);
  });

  it("换的时候留着地址里别的参数", () => {
    expect(settingsRedirect("/settings?tab=sign-in&linked=google")).toBe("/settings/sign-in?linked=google");
  });

  it.each(["/settings?tab=xxx", "/settings/xxx"])("不认识的 %s 回到 /settings", (from) => {
    expect(settingsRedirect(from)).toBe("/settings");
  });

  it.each(["/settings", "/settings/own-keys"])("%s 不用换", (href) => {
    expect(settingsRedirect(href)).toBeNull();
  });
});
