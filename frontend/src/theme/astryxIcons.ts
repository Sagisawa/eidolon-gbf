import {
  ArrowUp,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  CircleAlert,
  CircleCheck,
  Ellipsis,
  Info,
  Mic,
  Square,
  TriangleAlert,
  X,
} from "lucide-react";
import { createElement } from "react";

// Astryx 自带图标换成 Lucide，和界面上其余图标同一套（DESIGN.md「The Library Icon Rule」）。
// 单独成一个模块、以具名导出交给主题：`astryx theme build` 只会带上以具名导入方式注册的图标表。
// 用 createElement 而不是 JSX：theme build 编译这个文件时不走 Next 的 JSX 运行时。
export const notebookIcons = {
  // ChatComposer 的发送键和停止键。
  arrowUp: createElement(ArrowUp),
  check: createElement(Check),
  chevronDown: createElement(ChevronDown),
  chevronLeft: createElement(ChevronLeft),
  chevronRight: createElement(ChevronRight),
  close: createElement(X),
  error: createElement(CircleAlert),
  info: createElement(Info),
  microphone: createElement(Mic),
  moreHorizontal: createElement(Ellipsis),
  stop: createElement(Square),
  success: createElement(CircleCheck),
  warning: createElement(TriangleAlert),
};
