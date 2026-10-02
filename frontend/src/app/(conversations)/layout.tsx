"use client";

import { LayoutPanel } from "@astryxdesign/core/Layout";
import { ResizeHandle } from "@astryxdesign/core/Resizable";
import { useParams } from "next/navigation";
import type { CSSProperties, ReactNode } from "react";

import { DirectoryProvider, useWide } from "@/components/conversations/ConversationDirectory";
import { ConversationList } from "@/components/conversations/ConversationList";
import { useSavedSize } from "@/components/conversations/useSavedSize";
import { PageShell } from "@/components/PageShell";
import { copy } from "@/i18n";

/**
 * 消息列表和对话共用的双栏外壳（spec「信息架构」）。
 * - 宽屏：左栏是列表，默认 320px，拖动两栏之间的竖线可以调宽窄（记在这台设备上）；右栏是这一路由的内容
 *   （对话，或者没选角色时的一句提示）；换角色时列表不动。
 * - 窄屏：两级页面。首页只显示列表，进了对话只显示对话（对话页首有返回键）。
 * 角色和摘要由这里载入一次，列表和对话从 DirectoryProvider 取。
 */
export default function ConversationsLayout({ children }: { children: ReactNode }) {
  const wide = useWide();
  const { characterId } = useParams<{ characterId?: string }>();
  const list = <ConversationList selectedId={wide ? (characterId ?? null) : null} />;
  // 上限是定值而不是窗口的几成：上限一变 useResizable 就把拖到的宽度截下来，窗口缩到窄屏再放大会丢掉它。
  // 最宽 480，最窄的宽屏（768px）上对话栏还有将近 300px。
  const column = useSavedSize("list", { defaultSize: 320, minSize: 240, maxSize: 480 });

  return (
    <DirectoryProvider>
      <PageShell
        padding={0}
        isScrollable={false}
        start={
          wide ? (
            <>
              <LayoutPanel
                width={column.size}
                padding={0}
                isScrollable={false}
                role="navigation"
                label={copy.conversationList.title}
                style={columnRule}
              >
                {list}
              </LayoutPanel>
              <ResizeHandle
                direction="horizontal"
                resizable={column.props}
                isAlwaysVisible={false}
                label={copy.conversationList.resize}
              />
            </>
          ) : undefined
        }
      >
        {wide || characterId ? children : list}
      </PageShell>
    </DirectoryProvider>
  );
}

/** 列表栏和对话栏之间的一条天蓝细线（DESIGN.md「Layout」），也是拖动调宽窄的地方。 */
const columnRule: CSSProperties = { borderInlineEnd: "var(--border-width) solid var(--color-border-blue)" };
