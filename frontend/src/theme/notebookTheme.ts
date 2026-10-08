import { defineTheme } from "@astryxdesign/core/theme";

// 相对路径而不是 "@/"：`astryx theme build` 在 Next 之外编译这个文件。
import { paperColors } from "../lib/imageColor";
import { notebookIcons } from "./astryxIcons";

const { body, ink } = paperColors;

/** 深色弹层的边线：与底部面板 #1f232c、菜单 #262b36 的底色对比度都 ≥ 3。 */
export const overlayEdge = "#61799c";

/**
 * 横幅说明文字的颜色。Astryx 默认用次要色，压在状态色的淡底上（浅色约 20%、深色约 25%）不够 4.5:1：
 * 深色的警告横幅在卡片底上 4.0、信息横幅在菜单底上 3.3，浅色的信息横幅 3.6、错误 4.0。两种模式都比次要色
 * 再深（浅色）或再亮（深色）一档，四种状态在纸面、卡片、菜单上都 ≥ 4.5，仍和标题分得出主次。
 */
export const bannerNote = { light: "#4a566e", dark: "#c0c8d8" };

/**
 * 制作人的手帐（DESIGN.md）：冷白复印纸、天蓝横线、事务所深蓝墨水，明暗两套。
 * 角色的颜色不在这里，由 herVars() 按对话局部注入。
 *
 * 这是主题的源文件。改了它（或 astryxIcons.ts、imageColor.ts 的 paperColors）之后运行
 * `npm run theme:build` 重新生成 built/ 里的预构建主题；`npm test` 会检查预构建是否过期。
 */
export const notebookTheme = defineTheme({
  name: "eidolon-notebook",
  color: { accent: [ink.light, "#a9c6f5"], neutralStyle: "cool", contrast: "standard" },
  typography: {
    body: { family: "var(--font-zh)", fallbacks: '"PingFang SC", "Microsoft YaHei", system-ui, sans-serif' },
    heading: { weight: "semibold" },
  },
  radius: { base: 4, multiplier: 1.5 },
  // 深色模式下弹层和背后几乎同色，加一圈边线才看得出边界；浅色模式靠阴影就够了。
  // 键名就是 Astryx 的稳定类名 .astryx-<键>；AlertDialog 也渲染成 .astryx-dialog。
  components: {
    dialog: { base: { border: `var(--border-width) solid light-dark(transparent, ${overlayEdge})` } },
    "bottom-sheet": { base: { borderColor: `light-dark(transparent, ${overlayEdge})` } },
    popover: { base: { border: `var(--border-width) solid light-dark(transparent, ${overlayEdge})` } },
    // 横幅的说明文字：次要色压在状态色的淡底上不到 4.5:1（见 bannerNote）。
    "banner-description": { base: { color: `light-dark(${bannerNote.light}, ${bannerNote.dark})` } },
    // 表头比正文小一号、次要色：默认和正文同字号同 semibold，和后台小节标题（h3）分不开。
    "table-header-cell": {
      base: {
        fontSize: "var(--text-supporting-size)",
        fontWeight: "var(--font-weight-medium)",
        color: "var(--color-text-secondary)",
      },
    },
  },
  icons: notebookIcons,
  tokens: {
    // 事务所深蓝墨水：生成的色板会把它提亮，这里钉死。
    "--color-accent": [ink.light, "#a9c6f5"],
    // 全站只有一种墨水：正文也用事务所深蓝。
    "--color-text-primary": [ink.light, ink.dark],
    "--color-background-body": [body.light, body.dark],
    // 弹层（对话框、底部面板、菜单）要比纸面高一层，深色模式下才看得出边。
    "--color-background-surface": [body.light, "#1f232c"],
    "--color-background-card": [body.light, "#1f232c"],
    "--color-background-popover": ["#ffffff", "#262b36"],
    // 挂断等危险操作：白字在上面要 ≥ 4.5（Astryx 默认的深色红只有 3.8）。
    "--color-error": ["#c8283c", "#c8283c"],
    "--color-border-blue": ["#d6e6fb", "#243049"],
    // 手帐的装订边距线，比横线深一档。
    "--color-border-emphasized": ["#8bbaeb", "#3a5580"],
    "--color-text-secondary": ["#5d6b85", "#9aa6bd"],
  },
});
