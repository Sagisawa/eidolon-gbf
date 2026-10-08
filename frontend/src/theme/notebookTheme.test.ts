import { describe, expect, it } from "vitest";

import { eidolonNotebookTheme } from "./built/eidolon-notebook";
import { contrast } from "../lib/imageColor";
import { bannerNote, notebookTheme, overlayEdge } from "./notebookTheme";

describe("预构建的主题", () => {
  it("和源文件一致，带着 Lucide 图标表（不一致就运行 npm run theme:build）", () => {
    expect(eidolonNotebookTheme.name).toBe(notebookTheme.name);
    expect(eidolonNotebookTheme.tokens).toEqual(notebookTheme.tokens);
    expect(eidolonNotebookTheme.components).toEqual(notebookTheme.components);
    type WithAxes = { __axes?: unknown };
    expect((eidolonNotebookTheme as WithAxes).__axes).toEqual((notebookTheme as WithAxes).__axes);
    expect(Object.keys(eidolonNotebookTheme.icons ?? {}).sort()).toEqual(Object.keys(notebookTheme.icons ?? {}).sort());
  });

  it("发送键、停止键也换成 Lucide", () => {
    expect(Object.keys(notebookTheme.icons ?? {})).toEqual(expect.arrayContaining(["arrowUp", "stop"]));
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

  it("横幅的说明文字在四种状态的淡底上都 ≥ 4.5（浅色 20%、深色 25% 的状态色叠在纸面、卡片、菜单上）", () => {
    // Astryx 各状态的 muted 底色；信息横幅用 accent（浅色是事务所深蓝，深色是夜间墨水）。
    const modes = [
      { note: bannerNote.light, alpha: 0.2, statuses: ["#e2a400", "#f5394f", "#0b991f", "#1c2a4a"], bases: ["#fbfcfe", "#ffffff"] },
      { note: bannerNote.dark, alpha: 0.25, statuses: ["#e2a400", "#f5394f", "#0b991f", "#a9c6f5"], bases: ["#14171d", "#1f232c", "#262b36"] },
    ];
    for (const { note, alpha, statuses, bases } of modes) {
      for (const base of bases) {
        for (const status of statuses) {
          expect(contrast(note, over(status, alpha, base)), `${note}: ${status} on ${base}`).toBeGreaterThanOrEqual(4.5);
        }
      }
    }
  });
});

/** `color` 以 `alpha` 的不透明度叠在 `base` 上得到的颜色。 */
function over(color: string, alpha: number, base: string): string {
  const channels = (hex: string) => [1, 3, 5].map((i) => parseInt(hex.slice(i, i + 2), 16));
  const [c, b] = [channels(color), channels(base)];
  return `#${c.map((v, i) => Math.round(v * alpha + b[i] * (1 - alpha)).toString(16).padStart(2, "0")).join("")}`;
}
