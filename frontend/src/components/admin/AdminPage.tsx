"use client";

import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { StackItem } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { ReactNode } from "react";

import { PROSE_WIDTH } from "@/components/SettingsSection";

const WIDTHS = { wide: 1200, narrow: 960 } as const;


// 后台的字号层级（DESIGN.md「Typography」的后台部分）：页标题 h1 用 Heading 默认的 heading-1（24px），
// 组标题 h2 是 Title（17px，SettingsSection），组里的小节 h3 和正文同字号、靠 semibold 区分，
// 表头小一号、medium、次要色（主题里覆盖），数字卡的数字 20px，不和页标题抢。

type Props = {
  title: ReactNode;
  intro?: ReactNode;
  /** 标题上方的一行，例如返回列表的链接。 */
  above?: ReactNode;
  /** 标题下方、说明之前的一行，例如状态标签。 */
  meta?: ReactNode;
  /** 页首末端：这一页的主要操作或范围切换。 */
  end?: ReactNode;
  width: keyof typeof WIDTHS;
  children?: ReactNode;
};

/**
 * 后台每一页的框：页首（标题、一句说明，末端放这一页的主要操作）和一条限宽的内容列，靠左对齐侧栏。
 * 表格和图表多的页（看板、用户列表）用宽栏；表单和资料（配置、用户详情）用窄栏，行不至于拉得太长。
 * 页首下面的各节用 `SettingsSection`（标题 + 说明 + 内容 + 分隔线），三页写法一致。
 */
export function AdminPage({ title, intro, above, meta, end, width, children }: Props) {
  return (
    <VStack maxWidth={WIDTHS[width]}>
      <VStack as="header" gap={3} paddingBlockEnd={2}>
        {above}
        <HStack gap={4} vAlign="end" wrap="wrap">
          <StackItem size="fill">
            <VStack gap={2}>
              <Heading level={1}>{title}</Heading>
              {meta}
              {intro && (
                <Text as="p" color="secondary" style={{ maxWidth: PROSE_WIDTH }}>
                  {intro}
                </Text>
              )}
            </VStack>
          </StackItem>
          {end}
        </HStack>
      </VStack>
      {children}
    </VStack>
  );
}
