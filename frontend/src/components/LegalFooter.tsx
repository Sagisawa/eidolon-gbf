"use client";

import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";

import { AppLink } from "@/components/AppLink";
import { copy } from "@/i18n";

/** 页脚的声明：非官方粉丝作品、角色由 AI 扮演，以及隐私政策和使用条款（PRODUCT.md「Brand Commitments」）。 */
export function LegalFooter() {
  return (
    <HStack gap={3} wrap="wrap" vAlign="center">
      <Text type="supporting">{copy.legal.disclaimer}</Text>
      <HStack gap={3}>
        <AppLink href="/privacy" color="secondary" size="sm" hasUnderline={false}>
          {copy.legal.privacy}
        </AppLink>
        <AppLink href="/terms" color="secondary" size="sm" hasUnderline={false}>
          {copy.legal.terms}
        </AppLink>
      </HStack>
    </HStack>
  );
}
