import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

import { contrast } from "@/lib/imageColor";

// 主题（shadcn neutral 加少数覆盖值，DESIGN.md「Colors」）写在 globals.css 的 :root 里，
// 颜色变量是 light-dark(浅色, 深色)，或两种模式共用的一个值。这里直接读那份 CSS，检查规格要求的几对颜色。
const css = readFileSync(fileURLToPath(new URL("../app/globals.css", import.meta.url)), "utf8");

const MODES = ["light", "dark"] as const;
type Mode = (typeof MODES)[number];

describe("主题对比度", () => {
  for (const mode of MODES) {
    describe(mode, () => {
      it("次要文字在页面底和 muted 底上都 ≥ 4.5", () => {
        expect(pair("--muted-foreground", "--background", mode)).toBeGreaterThanOrEqual(4.5);
        expect(pair("--muted-foreground", "--muted", mode)).toBeGreaterThanOrEqual(4.5);
      });

      it("挂断红（--destructive）上的白字 ≥ 4.5", () => {
        expect(contrast(color("--destructive", mode), "#ffffff")).toBeGreaterThanOrEqual(4.5);
      });
    });
  }

  it("挂断红两种模式都是 DESIGN.md 的 #c8283c", () => {
    expect(color("--destructive", "light")).toBe("#c8283c");
    expect(color("--destructive", "dark")).toBe("#c8283c");
  });

  describe("深色浮层", () => {
    it("浮层比页面高一层色调", () => {
      // 和黑色的对比度越大就越亮。
      const lift = (name: string) => contrast(color(name, "dark"), "#000000");
      expect(lift("--popover")).toBeGreaterThan(lift("--background"));
    });

    it("边线和浮层底、页面底都 ≥ 3", () => {
      expect(pair("--overlay-edge", "--popover", "dark")).toBeGreaterThanOrEqual(3);
      expect(pair("--overlay-edge", "--background", "dark")).toBeGreaterThanOrEqual(3);
    });
  });
});

function pair(a: string, b: string, mode: Mode): number {
  return contrast(color(a, mode), color(b, mode));
}

/** 变量在某个模式下的颜色，换成 `#rrggbb`。 */
function color(name: string, mode: Mode): string {
  const declared = css.match(new RegExp(`(?<![\\w-])${name}:\\s*(.+?);`))?.[1];
  if (!declared) throw new Error(`globals.css 里没有 ${name}`);
  const pair = declared.match(/^light-dark\((.+?),\s*(.+)\)$/);
  return toHex((pair ? pair[mode === "light" ? 1 : 2] : declared).trim());
}

function toHex(value: string): string {
  if (/^#[0-9a-f]{6}$/i.test(value)) return value.toLowerCase();
  const oklch = value.match(/^oklch\(([\d.]+)\s+([\d.]+)\s+([\d.]+)\)$/);
  if (!oklch) throw new Error(`不认识的颜色写法：${value}（只认 #rrggbb 和不透明的 oklch）`);
  const [L, C, h] = oklch.slice(1).map(Number);
  const a = C * Math.cos((h * Math.PI) / 180);
  const b = C * Math.sin((h * Math.PI) / 180);
  const l = (L + 0.3963377774 * a + 0.2158037573 * b) ** 3;
  const m = (L - 0.1055613458 * a - 0.0638541728 * b) ** 3;
  const s = (L - 0.0894841775 * a - 1.291485548 * b) ** 3;
  const linear = [
    4.0767416621 * l - 3.3077115913 * m + 0.2309699292 * s,
    -1.2684380046 * l + 2.6097574011 * m - 0.3413193965 * s,
    -0.0041960863 * l - 0.7034186147 * m + 1.707614701 * s,
  ];
  const encode = (v: number) => {
    const c = Math.min(1, Math.max(0, v));
    const srgb = c <= 0.0031308 ? 12.92 * c : 1.055 * c ** (1 / 2.4) - 0.055;
    return Math.round(srgb * 255).toString(16).padStart(2, "0");
  };
  return `#${linear.map(encode).join("")}`;
}
