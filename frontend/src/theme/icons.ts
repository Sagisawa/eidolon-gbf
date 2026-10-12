// 界面上的图标统一用 Lucide，以语义别名导出，不手绘 SVG（DESIGN.md「The Library Icon Rule」；品牌标志是例外，见文件末尾）。
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

// 发送键和更多菜单。
export { ArrowUp as SendIcon, Ellipsis as MoreIcon } from "lucide-react";

// 失败提示（components/app/FailureNotice）。
export { CircleAlert as FailureIcon } from "lucide-react";

// 设置页「已绑定」的提示和它的关闭键（shadcn-redesign 18）。
export { CircleCheck as SuccessIcon, X as CloseIcon } from "lucide-react";

// 对话列表的搜索框；通话条右端「回到通话 ›」的箭头。
export { ChevronRight as ForwardIcon, Search as SearchIcon } from "lucide-react";

// 对话列表搜索框右边的筛选按钮；置顶那一行的图钉。
export { ListFilter as FilterIcon, Pin as PinIcon } from "lucide-react";

// 后台用户列表可以排序的表头：按它从多到少排着的，和还没按它排的（shadcn-redesign 22）。
export { ArrowDown as SortedIcon, ArrowUpDown as SortableIcon } from "lucide-react";

// 通话层右上角的「只看文字」胶囊。
export { Captions as TextOnlyIcon } from "lucide-react";

// 对话列表页首的 GitHub 仓库链接；品牌标志 Lucide 不收，是 The Library Icon Rule 的例外。
export { GitHubIcon } from "./GitHubIcon";
