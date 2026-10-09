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

// 发送键和更多菜单（shadcn 新代码用；旧的 Astryx 输入栏用 astryxIcons.ts 里注册的图标）。
export { ArrowUp as SendIcon, Ellipsis as MoreIcon } from "lucide-react";

// 失败提示（components/app/FailureNotice）。
export { CircleAlert as FailureIcon } from "lucide-react";

// 对话列表的搜索框；通话条右端「回到通话 ›」的箭头。
export { ChevronRight as ForwardIcon, Search as SearchIcon } from "lucide-react";
