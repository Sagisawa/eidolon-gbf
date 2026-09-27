import { describe, expect, it } from "vitest";

import { copy, type Messages } from "./index";
import { zh } from "./zh";

/** 把文案树摊平成「路径 → 文案」，函数形式的文案用占位参数调用一次。 */
function leaves(tree: object, prefix = ""): [string, string][] {
  return Object.entries(tree).flatMap(([key, value]): [string, string][] => {
    const path = prefix ? `${prefix}.${key}` : key;
    if (typeof value === "string") return [[path, value]];
    if (typeof value === "function") return [[path, String(value("甲", "乙", "丙"))]];
    return leaves(value, path);
  });
}

describe("界面文案", () => {
  it("这次只有简体中文", () => {
    expect(copy).toBe(zh);
  });

  it("每一条都有字", () => {
    const empty = leaves(zh).filter(([, text]) => text.trim() === "");
    expect(empty).toEqual([]);
  });

  it("带参数的文案把参数放进句子里", () => {
    const withArgs = leaves(zh).filter(([path]) => {
      const node = path.split(".").reduce<unknown>((n, k) => (n as Record<string, unknown>)[k], zh);
      return typeof node === "function";
    });
    for (const [path, text] of withArgs) expect(text, path).toMatch(/甲/);
  });

  it("以后的语言要和中文有同样的键（类型层面）", () => {
    const sameShape: Messages = zh;
    expect(sameShape).toBeDefined();
  });
});
