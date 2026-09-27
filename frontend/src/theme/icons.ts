// 界面上的图标统一用 Lucide，以语义别名导出，不手绘 SVG（DESIGN.md「The Library Icon Rule」）。
// Astryx 组件内部用的图标在 astryxIcons.ts 里注册到主题。
export {
  ArrowRightLeft as MicSwitchIcon,
  Check as CheckIcon,
  ChevronDown as CollapseIcon,
  ChevronLeft as BackIcon,
  Mic as MicIcon,
  MicOff as MicOffIcon,
  Phone as PhoneIcon,
  PhoneOff as HangUpIcon,
  SendHorizontal as SendIcon,
} from "lucide-react";
