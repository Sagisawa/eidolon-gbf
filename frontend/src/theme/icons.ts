// 界面上的图标统一用 Lucide，以语义别名导出，不手绘 SVG（DESIGN.md「The Library Icon Rule」）。
// Astryx 组件内部用的图标在 astryxIcons.ts 里注册到主题。
export {
  ArrowRightLeft as MicSwitchIcon,
  ChevronDown as CollapseIcon,
  ChevronLeft as BackIcon,
  Mic as MicIcon,
  MicOff as MicOffIcon,
  Phone as PhoneIcon,
  PhoneOff as HangUpIcon,
  Shirt as OutfitIcon,
} from "lucide-react";

// 记忆页、设置页用的图标（ticket 06）。
export { Trash2 as TrashIcon } from "lucide-react";

// 后台导航用的图标。
export {
  LayoutDashboard as DashboardIcon,
  SlidersHorizontal as ConfigIcon,
  Users as UsersIcon,
} from "lucide-react";
