// 测试用：读 globals.css 里的主题颜色（shadcn neutral 加少数覆盖值，DESIGN.md「Colors」）。
// 颜色变量写在 :root 里，是 light-dark(浅色, 深色)、两种模式共用的一个值，或 var(--另一个变量)。
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import type { ModePair } from "@/lib/imageColor";

const css = readFileSync(fileURLToPath(new URL("../app/globals.css", import.meta.url)), "utf8");

export const MODES = ["light", "dark"] as const;
export type Mode = (typeof MODES)[number];

/** 主题变量（例如 `--muted-foreground`）在某个模式下的颜色，换成 `#rrggbb`。 */
export function themeColor(name: string, mode: Mode): string {
  const declared = css.match(new RegExp(`(?<![\\w-])${name}:\\s*(.+?);`))?.[1];
  if (!declared) throw new Error(`globals.css 里没有 ${name}`);
  const alias = declared.match(/^var\((--[\w-]+)\)$/);
  if (alias) return themeColor(alias[1], mode);
  const pair = declared.match(/^light-dark\((.+?),\s*(.+)\)$/);
  return toHex((pair ? pair[mode === "light" ? 1 : 2] : declared).trim());
}

/** 主题变量在两种模式下的颜色。 */
export function themePair(name: string): ModePair {
  return { light: themeColor(name, "light"), dark: themeColor(name, "dark") };
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
