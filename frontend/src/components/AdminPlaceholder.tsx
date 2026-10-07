import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

import { copy } from "@/i18n";

/** 后台里还没有内容的一页：只有标题和一句说明。 */
export function AdminPlaceholder({ title }: { title: string }) {
  return (
    <VStack gap={2}>
      <Heading level={1} style={{ fontSize: "var(--text-large-size)" }}>
        {title}
      </Heading>
      <Text as="p" color="secondary">
        {copy.admin.comingSoon}
      </Text>
    </VStack>
  );
}
