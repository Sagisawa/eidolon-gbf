"use client";

import { ClickableCard } from "@astryxdesign/core/ClickableCard";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { CSSProperties } from "react";

import { copy } from "@/i18n";
import { showTime } from "@/lib/callTime";
import type { LiveCall } from "@/lib/liveConversation";
import { lineState } from "@/theme/lineState";

import { useCallTime } from "./useCallTime";

/**
 * 通话层收起后贴在消息区顶端的便利贴（DESIGN.md「Call note」）：她的 note 底、一条半透明胶带、略斜、
 * 柔和投影；字带 noteRule 的下划线，实线=通话中，虚线=拨打中。点一下展开通话层。
 */
export function CallNote({ call, onExpand }: { call: LiveCall; onExpand: () => void }) {
  const time = useCallTime(call);
  const text = time ? copy.call.noteConnected(showTime(time)) : copy.call.noteDialing;
  return (
    <HStack hAlign="center" paddingBlock={3} style={{ background: "var(--color-background-body)" }}>
      <ClickableCard label={text} onClick={onExpand} padding={0} style={note}>
        <VStack paddingBlock={2} paddingInline={5}>
          <VStack as="span" aria-hidden style={tape} />
          <Text weight="medium" hasTabularNumbers style={lineState(time ? "solid" : "dashed", "var(--her-note-rule)")}>
            {text}
          </Text>
        </VStack>
      </ClickableCard>
    </HStack>
  );
}

/** 唯一直角、-1.2° 倾斜的纸片，Sticky note lift 阴影。 */
const note: CSSProperties = {
  position: "relative",
  overflow: "visible",
  background: "var(--her-note)",
  color: "var(--color-text-primary)",
  border: 0,
  borderRadius: "var(--radius-none)",
  transform: "rotate(-1.2deg)",
  boxShadow: "0 var(--spacing-0-5) var(--spacing-2) var(--color-shadow)",
};

/** 顶上一条 48×16、+2° 的半透明胶带。 */
const tape: CSSProperties = {
  position: "absolute",
  insetBlockStart: "calc(var(--spacing-2) * -1)",
  insetInlineStart: "50%",
  width: "var(--spacing-12)",
  height: "var(--spacing-4)",
  transform: "translateX(-50%) rotate(2deg)",
  background: "color-mix(in srgb, var(--color-background-body) 55%, transparent)",
  boxShadow: "0 0 0 var(--border-width) color-mix(in srgb, var(--color-border-blue) 60%, transparent)",
};
