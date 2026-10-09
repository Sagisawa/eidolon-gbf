import { createCn } from "cn/config";

// globals.css 的 @theme 里按 DESIGN.md 注册的具名字号、圆角和尺寸。不告诉 cn 的话，
// text-body 这类字号会被当成字色，和 text-foreground 一起出现时被合并掉。
// 在 @theme 里新增这三类 token 时要同步加到这里（utils.test.ts 管着）；通话层的曲线 ease-call 也在这里。
export const cn = createCn({
  extend: {
    theme: {
      text: [
        "list-title",
        "header",
        "row-name",
        "body",
        "japanese-line",
        "preview",
        "subtitle",
        "meta",
        "call-name",
        "call-line",
      ],
      radius: ["bubble", "bubble-inner"],
      spacing: ["list-avatar", "bubble-avatar", "call-dock-control", "call-bar"],
      ease: ["call"],
    },
  },
});
