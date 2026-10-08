"use client";

import { Card } from "@astryxdesign/core/Card";
import { Grid } from "@astryxdesign/core/Grid";
import { Heading } from "@astryxdesign/core/Heading";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { ReactNode } from "react";

// 看板各节共用的几块：数字卡片和放卡片的一行、组里带标题和说明的一小节、两节并排、等宽数字。

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

/** 数字卡排成一行：宽屏上六张一行，窄下来按每张不窄于 140px 折行（手机上一行两张）；张数少时也按同样的格子排，和上面的一行对齐。 */
export function TileRow({ children }: { children: ReactNode }) {
  return (
    <Grid columns={{ minWidth: 140, max: 6 }} gap={3}>
      {children}
    </Grid>
  );
}

/** 组里的一小节（`SettingsSection` 是一组，这里是组里的一项）：h3 标题、说明和内容。 */
export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <VStack gap={3}>
      <VStack gap={1}>
        <Heading level={3} style={{ fontSize: "var(--text-body-size)" }}>
          {title}
        </Heading>
        {hint && <Text type="supporting">{hint}</Text>}
      </VStack>
      {children}
    </VStack>
  );
}

/** 两小节并排：宽栏里左右各一半，窄到放不下两张不窄于 360px 的表时上下排。 */
export function Pair({ children }: { children: ReactNode }) {
  return (
    <Grid columns={{ minWidth: 360, max: 2 }} columnGap={8} rowGap={8} align="start">
      {children}
    </Grid>
  );
}

export function Numeric({ children }: { children: string }) {
  return <Text hasTabularNumbers>{children}</Text>;
}
