"use client";

import { Divider } from "@astryxdesign/core/Divider";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useId, type ReactNode } from "react";

import { SectionHeading } from "@/components/SubpageHeader";

/** 说明文字的行长上限：一行四十来个汉字。 */
export const PROSE_WIDTH = "42em";

type Props = {
  title: string;
  /** 页内链接跳到这一节用的锚点。 */
  id?: string;
  /** 标题下的一段说明。 */
  description?: ReactNode;
  children?: ReactNode;
};

/**
 * 设置页的一节：标题、说明、内容，下面一条分隔线。
 * 纸面上不再套卡片或底色，保持安静（PRODUCT.md「角色在前，系统在后」）。
 * 不用 Astryx Section：它会伸出页面内容的内边距，和页首的内容线对不齐。
 */
export function SettingsSection({ title, id, description, children }: Props) {
  const headingId = useId();
  return (
    <>
      <VStack as="section" id={id} aria-labelledby={headingId} gap={4} paddingBlock={6}>
        <VStack gap={1}>
          <SectionHeading id={headingId}>{title}</SectionHeading>
          {description && (
            <Text as="p" color="secondary" style={{ maxWidth: PROSE_WIDTH }}>
              {description}
            </Text>
          )}
        </VStack>
        {children}
      </VStack>
      <Divider />
    </>
  );
}
