"use client";

import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { StackItem } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { ReactNode } from "react";

const WIDTHS = { wide: 1200, narrow: 960 } as const;

/** 说明文字的行长上限：一行四十来个汉字。 */
export const PROSE_WIDTH = "42em";

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
              <Heading level={1} style={{ fontSize: "var(--text-large-size)" }}>
                {title}
              </Heading>
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
