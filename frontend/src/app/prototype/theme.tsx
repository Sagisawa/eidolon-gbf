import { defineTheme } from "@astryxdesign/core/theme";
import {
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Ellipsis,
  Info,
  Mic,
  TriangleAlert,
  X,
} from "lucide-react";

import { paperColors } from "@/lib/imageColor";

const { body, ink } = paperColors;

/** 深色弹层的边线：与弹层底色 #1f232c 对比度 ≥ 3。 */
const overlayEdge = "#5a7194";

// 制作人手帐：冷白复印纸、天蓝横线、事务所深蓝墨水。角色的颜色不在这里，按对话局部注入。
export const notebookTheme = defineTheme({
  name: "eidolon-notebook",
  color: { accent: [ink.light, "#a9c6f5"], neutralStyle: "cool", contrast: "standard" },
  typography: {
    body: { family: "var(--font-zh)", fallbacks: '"PingFang SC", "Microsoft YaHei", system-ui, sans-serif' },
    heading: { weight: "semibold" },
  },
  radius: { base: 4, multiplier: 1.5 },
  // 深色模式下弹层和背后几乎同色，加一圈边线才看得出边界；浅色模式靠阴影就够了。
  components: {
    // 键名就是 Astryx 的稳定类名 .astryx-<键>；AlertDialog 也渲染成 .astryx-dialog。
    dialog: { base: { border: `var(--border-width) solid light-dark(transparent, ${overlayEdge})` } },
    "bottom-sheet": { base: { borderColor: `light-dark(transparent, ${overlayEdge})` } },
    popover: { base: { border: `var(--border-width) solid light-dark(transparent, ${overlayEdge})` } },
  },
  // Astryx 自带图标换成 Lucide，和界面上其余图标同一套。
  icons: {
    check: <Check />,
    chevronDown: <ChevronDown />,
    chevronLeft: <ChevronLeft />,
    chevronRight: <ChevronRight />,
    close: <X />,
    error: <CircleAlert />,
    info: <Info />,
    microphone: <Mic />,
    moreHorizontal: <Ellipsis />,
    success: <CircleCheck />,
    warning: <TriangleAlert />,
  },
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
