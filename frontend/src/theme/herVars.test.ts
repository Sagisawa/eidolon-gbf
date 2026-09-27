import { describe, expect, it } from "vitest";

import { imageColorScale } from "@/lib/imageColor";

import { herVars, ld, listRow } from "./herVars";

const OFFICIAL = ["#ffbad6", "#f84cad", "#144384", "#ffe012", "#92cfbb"];

describe("ld", () => {
  it("按系统明暗取一对颜色中的一个", () => {
    expect(ld({ light: "#ffffff", dark: "#000000" })).toBe("light-dark(#ffffff, #000000)");
  });
});

describe("herVars", () => {
  it.each(OFFICIAL)("%s：强调色和她的颜色都取自成对校验过的色阶", (color) => {
    const s = imageColorScale(color);
    const vars = herVars(color) as Record<string, string>;

    expect(vars["--color-accent"]).toBe(ld(s.accent));
    expect(vars["--color-text-accent"]).toBe(ld(s.accent));
    expect(vars["--color-icon-accent"]).toBe(ld(s.accent));
    expect(vars["--color-on-accent"]).toBe(ld(s.onAccent));
    expect(vars["--color-accent-muted"]).toBe(ld(s.paper));
    expect(vars["--her-mark"]).toBe(ld(s.mark));
    expect(vars["--her-paper"]).toBe(ld(s.paper));
    expect(vars["--her-paper-muted"]).toBe(ld(s.paperMuted));
    expect(vars["--her-note"]).toBe(ld(s.note));
    expect(vars["--her-note-rule"]).toBe(ld(s.noteRule));
    expect(vars["--her-button"]).toBe(ld(s.button.bg));
    expect(vars["--her-button-fg"]).toBe(ld(s.button.fg));
    expect(vars["--her-call-top"]).toBe(s.call.top);
    expect(vars["--her-call-deep"]).toBe(s.call.deep);
    expect(vars["--her-call-rule"]).toBe(s.call.rule);
  });

  it.each(OFFICIAL)("%s：官方原色只作通话层头像背后的光晕，没有单独露出原色的变量", (color) => {
    const vars = herVars(color) as Record<string, string>;

    // 其他颜色在已经达标时可能恰好等于原色，但那是色阶校验过的结果，不是直接取用原色。
    expect(vars["--her-call-glow"]).toBe(imageColorScale(color).raw);
    expect(Object.keys(vars)).not.toContain("--her-raw");
  });

  it("只注入 Astryx 强调色和 --her-* 变量", () => {
    const names = Object.keys(herVars("#ffbad6"));
    expect(names.every((n) => n.startsWith("--her-") || n.startsWith("--color-"))).toBe(true);
    expect(names.filter((n) => n.startsWith("--color-")).sort()).toEqual([
      "--color-accent",
      "--color-accent-muted",
      "--color-icon-accent",
      "--color-on-accent",
      "--color-text-accent",
    ]);
  });

  it("印象色格式不对时报错", () => {
    expect(() => herVars("pink")).toThrow();
  });
});

describe("listRow", () => {
  it.each(OFFICIAL)("%s：行上只带她头像描边的颜色", (color) => {
    expect(listRow(color, false)).toEqual({ "--her-mark": ld(imageColorScale(color).mark) });
  });

  it.each(OFFICIAL)("%s：选中行铺她的纸色，次要字换成纸色上校验过的颜色", (color) => {
    const s = imageColorScale(color);
    expect(listRow(color, true)).toEqual({
      "--her-mark": ld(s.mark),
      background: ld(s.paper),
      "--color-text-secondary": ld(s.paperMuted),
    });
  });
});
