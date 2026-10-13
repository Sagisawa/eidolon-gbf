import { copy } from "@/i18n";
import type { EventKind } from "@/lib/api";
import { GiftIcon, HangUpIcon } from "@/theme/icons";

/** 每种对话事件的图标：消息区的分隔线和列表的「最后一句」共用。 */
export const EVENT_ICONS: Record<EventKind, typeof HangUpIcon> = {
  hung_up: HangUpIcon,
  gift: GiftIcon,
};

/** 对话事件给用户看的那句话，两处共用；送礼记录写上礼物名（`gift`）。 */
export function eventText(event: EventKind, name: string, gift: string | null): string {
  const t = copy.conversation.events;
  return event === "gift" ? t.gift(name, gift ?? "") : t[event](name);
}
