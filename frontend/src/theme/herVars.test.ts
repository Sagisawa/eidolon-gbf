import { describe, expect, it } from "vitest";

import { imageColorScale } from "@/lib/imageColor";

import { herVars, ld, listRow } from "./herVars";

// herVars() 和 listRow() 只是把 imageColorScale() 的结果按名字摆出来，没有按颜色分的分支：
// 用一种印象色就够了。各种印象色推算出的色阶是否达标，由 imageColor.test.ts 检查。
const COLOR = "#ffbad6";

describe("ld", () => {
  it("按系统明暗取一对颜色中的一个", () => {
    expect(ld({ light: "#ffffff", dark: "#000000" })).toBe("light-dark(#ffffff, #000000)");
  });
});

describe("herVars", () => {
  it("shadcn 的 primary、焦点环和 --her-* 都取自成对校验过的色阶，迁移期间 Astryx 的强调色照旧；官方原色只作通话层头像背后的光晕", () => {
    const s = imageColorScale(COLOR);
    const vars = herVars(COLOR) as Record<string, string>;

    // shadcn：primary 换成她的强调色，焦点环换成她的记号色；不碰 --accent（那是悬停底色）。
    expect(vars["--primary"]).toBe(ld(s.accent));
    expect(vars["--primary-foreground"]).toBe(ld(s.onAccent));
    expect(vars["--ring"]).toBe(ld(s.mark));
    expect(vars["--her-wall"]).toBe(ld(s.wall));

    expect(vars["--color-accent"]).toBe(ld(s.accent));
    expect(vars["--color-text-accent"]).toBe(ld(s.accent));
    expect(vars["--color-icon-accent"]).toBe(ld(s.accent));
    expect(vars["--color-on-accent"]).toBe(ld(s.onAccent));
    expect(vars["--color-accent-muted"]).toBe(ld(s.paper));
    expect(vars["--her-mark"]).toBe(ld(s.mark));
    expect(vars["--her-paper"]).toBe(ld(s.paper));
    expect(vars["--her-paper-muted"]).toBe(ld(s.paperMuted));
    expect(vars["--her-button"]).toBe(ld(s.button.bg));
    expect(vars["--her-button-fg"]).toBe(ld(s.button.fg));
    expect(vars["--her-call-top"]).toBe(s.call.top);
    expect(vars["--her-call-deep"]).toBe(s.call.deep);
    expect(vars["--her-call-rule"]).toBe(s.call.rule);

    // 其他颜色在已经达标时可能恰好等于原色，但那是色阶校验过的结果，不是直接取用原色。
    expect(vars["--her-call-glow"]).toBe(s.raw);
    expect(Object.keys(vars)).not.toContain("--her-raw");

    // 只注入 Astryx 强调色、shadcn 的 primary 和焦点环、--her-* 变量。
    const names = Object.keys(vars);
    const shadcn = ["--primary", "--primary-foreground", "--ring"];
    expect(names.every((n) => n.startsWith("--her-") || n.startsWith("--color-") || shadcn.includes(n))).toBe(true);
    expect(names.filter((n) => !n.startsWith("--her-") && !n.startsWith("--color-")).sort()).toEqual(shadcn);
    expect(names.filter((n) => n.startsWith("--color-")).sort()).toEqual([
      "--color-accent",
      "--color-accent-muted",
      "--color-icon-accent",
      "--color-on-accent",
      "--color-text-accent",
    ]);
  });
});

describe("listRow", () => {
  it("行上只带她头像描边的颜色；选中行铺她的纸色，次要字换成纸色上校验过的颜色", () => {
    const s = imageColorScale(COLOR);

    expect(listRow(COLOR, false)).toEqual({ "--her-mark": ld(s.mark) });
    expect(listRow(COLOR, true)).toEqual({
      "--her-mark": ld(s.mark),
      background: ld(s.paper),
      "--color-text-secondary": ld(s.paperMuted),
    });
  });
});
