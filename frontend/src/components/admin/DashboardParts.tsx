"use client";

import { Card } from "@astryxdesign/core/Card";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { ReactNode } from "react";

// 看板各节共用的几块：数字卡片、带标题和说明的一节、等宽数字。

export function StatTile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card>
      <VStack gap={1}>
        <Text type="supporting">{label}</Text>
        <Text type="display-3" weight="semibold">
          {value}
        </Text>
        {note && <Text type="supporting">{note}</Text>}
      </VStack>
    </Card>
  );
}

export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <VStack gap={3}>
      <VStack gap={1}>
        <Heading level={2} style={{ fontSize: "var(--text-body-size)" }}>
          {title}
        </Heading>
        {hint && <Text type="supporting">{hint}</Text>}
      </VStack>
      {children}
    </VStack>
  );
}

export function Numeric({ children }: { children: string }) {
  return <Text hasTabularNumbers>{children}</Text>;
}
