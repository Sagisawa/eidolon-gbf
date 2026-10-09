import { describe, expect, it } from "vitest";

import { contrast } from "@/lib/imageColor";

import { MODES, type Mode, themeColor as color } from "./themeCss";

// 主题（globals.css）里规格要求的几对颜色。

describe("主题对比度", () => {
  for (const mode of MODES) {
    describe(mode, () => {
      it("次要文字在页面底和 muted 底上都 ≥ 4.5", () => {
        expect(pair("--muted-foreground", "--background", mode)).toBeGreaterThanOrEqual(4.5);
        expect(pair("--muted-foreground", "--muted", mode)).toBeGreaterThanOrEqual(4.5);
      });

      // --hangup 就是 var(--destructive)，不另测。
      it("挂断红（--destructive）上的白字 ≥ 4.5", () => {
        expect(contrast(color("--destructive", mode), "#ffffff")).toBeGreaterThanOrEqual(4.5);
      });

      it("制作人气泡（事务所深蓝墨水）上的字 ≥ 4.5", () => {
        expect(pair("--on-producer-ink", "--producer-ink", mode)).toBeGreaterThanOrEqual(4.5);
      });

      it("她的气泡上的日语原文和中文字幕都 ≥ 4.5", () => {
        expect(pair("--foreground", "--bubble-her", mode)).toBeGreaterThanOrEqual(4.5);
        expect(pair("--muted-foreground", "--bubble-her", mode)).toBeGreaterThanOrEqual(4.5);
      });
    });
  }

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
