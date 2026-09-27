"use client";

import { Heading } from "@astryxdesign/core/Heading";
import { VStack } from "@astryxdesign/core/VStack";

import { copy } from "@/i18n";

/** 首页。宽屏时右栏还没选角色，居中一句提示；窄屏时外壳只显示列表，这一页不出现。 */
export default function ConversationsHome() {
  return (
    <VStack height="100%" hAlign="center" vAlign="center" padding={6}>
      <Heading level={2} color="secondary">
        {copy.conversationList.noneSelected}
      </Heading>
    </VStack>
  );
}
