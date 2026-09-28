import { describe, expect, it } from "vitest";

import { eidolonNotebookTheme } from "./built/eidolon-notebook";
import { contrast } from "../lib/imageColor";
import { notebookTheme, overlayEdge } from "./notebookTheme";

describe("预构建的主题", () => {
  it("和源文件一致（不一致就运行 npm run theme:build）", () => {
    expect(eidolonNotebookTheme.name).toBe(notebookTheme.name);
    expect(eidolonNotebookTheme.tokens).toEqual(notebookTheme.tokens);
    expect(eidolonNotebookTheme.components).toEqual(notebookTheme.components);
    type WithAxes = { __axes?: unknown };
    expect((eidolonNotebookTheme as WithAxes).__axes).toEqual((notebookTheme as WithAxes).__axes);
  });

  it("发送键、停止键也换成 Lucide", () => {
    expect(Object.keys(notebookTheme.icons ?? {})).toEqual(expect.arrayContaining(["arrowUp", "stop"]));
  });

  it("带着 Lucide 图标表", () => {
    expect(Object.keys(eidolonNotebookTheme.icons ?? {}).sort()).toEqual(Object.keys(notebookTheme.icons ?? {}).sort());
  });
});

describe("深色模式修补", () => {
  const tokens = notebookTheme.tokens as Record<string, string>;

  it("危险红两种模式都是挂断红", () => {
    expect(tokens["--color-error"]).toMatch(/#c8283c.*#c8283c/i);
  });

  it("弹层在深色模式下比纸面高一层", () => {
    expect(tokens["--color-background-popover"]).toContain("#262b36");
    expect(tokens["--color-background-surface"]).toContain("#1f232c");
  });

  it("深色弹层的边线在面板和菜单的底色上都看得出（≥ 3）", () => {
    // 两种底色就是上一条测试钉住的深色值。
    expect(contrast(overlayEdge, "#1f232c")).toBeGreaterThanOrEqual(3);
    expect(contrast(overlayEdge, "#262b36")).toBeGreaterThanOrEqual(3);
  });
});
