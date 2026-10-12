import { describe, expect, it } from "vitest";

import { EXCERPT_LENGTH, excerpt } from "@/lib/announcements";

describe("excerpt", () => {
  it("keeps a short body as it is", () => {
    expect(excerpt("今晚 23 点维护")).toBe("今晚 23 点维护");
  });

  it("drops the Markdown marks, keeping the words of links and code", () => {
    expect(excerpt("**新角色**上线了：*樱木真乃*，见[说明](https://example.com)和 `设置`")).toBe(
      "新角色上线了：樱木真乃，见说明和 设置",
    );
  });

  it("drops the marks starting a line: list items, numbers, headings and quotes", () => {
    expect(excerpt("# 更新\n- 第一条\n* 第二条\n1. 第三条\n> 引用")).toBe("更新 第一条 第二条 第三条 引用");
  });

  it("joins the lines and runs of spaces with one space", () => {
    expect(excerpt("  第一段\n\n第二段   还有  ")).toBe("第一段 第二段 还有");
  });

  it("cuts a long body short with an ellipsis", () => {
    const body = "字".repeat(EXCERPT_LENGTH + 10);

    expect(excerpt(body)).toBe(`${"字".repeat(EXCERPT_LENGTH)}…`);
  });

  it("leaves a body exactly as long as an excerpt uncut", () => {
    const body = "字".repeat(EXCERPT_LENGTH);

    expect(excerpt(body)).toBe(body);
  });

  it("keeps the words of an image's description", () => {
    expect(excerpt("![立绘](a.png) 新衣装")).toBe("立绘 新衣装");
  });
});
