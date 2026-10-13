import type { EventKind } from "@/lib/api";
import { HangUpIcon } from "@/theme/icons";

/** 每种对话事件的图标：消息区的分隔线和列表的「最后一句」共用。 */
export const EVENT_ICONS: Record<EventKind, typeof HangUpIcon> = {
  hung_up: HangUpIcon,
};
