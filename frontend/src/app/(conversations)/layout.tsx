"use client";

import { LayoutPanel } from "@astryxdesign/core/Layout";
import { useParams } from "next/navigation";
import type { CSSProperties, ReactNode } from "react";

import { DirectoryProvider, useWide } from "@/components/conversations/ConversationDirectory";
import { ConversationList } from "@/components/conversations/ConversationList";
import { PageShell } from "@/components/PageShell";
import { copy } from "@/i18n";

/**
 * 消息列表和对话共用的双栏外壳（spec「信息架构」）。
 * - 宽屏：左栏 320px 是列表，右栏是这一路由的内容（对话，或者没选角色时的一句提示）；换角色时列表不动。
 * - 窄屏：两级页面。首页只显示列表，进了对话只显示对话（对话页首有返回键）。
 * 角色和摘要由这里载入一次，列表和对话从 DirectoryProvider 取。
 */
export default function ConversationsLayout({ children }: { children: ReactNode }) {
  const wide = useWide();
  const { characterId } = useParams<{ characterId?: string }>();
  const list = <ConversationList selectedId={wide ? (characterId ?? null) : null} />;

  return (
    <DirectoryProvider>
      <PageShell
        padding={0}
        isScrollable={false}
        start={
          wide ? (
            <LayoutPanel
              width={320}
              padding={0}
              isScrollable={false}
              role="navigation"
              label={copy.conversationList.title}
              style={columnRule}
            >
              {list}
            </LayoutPanel>
          ) : undefined
        }
      >
        {wide || characterId ? children : list}
      </PageShell>
    </DirectoryProvider>
  );
}

/** 列表栏和对话栏之间的一条天蓝细线（DESIGN.md「Layout」）。 */
const columnRule: CSSProperties = { borderInlineEnd: "var(--border-width) solid var(--color-border-blue)" };
