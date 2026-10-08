"use client";

import { Card } from "@astryxdesign/core/Card";
import { Grid } from "@astryxdesign/core/Grid";
import { Heading } from "@astryxdesign/core/Heading";
import { useMediaQuery } from "@astryxdesign/core/hooks";
import { List, ListItem } from "@astryxdesign/core/List";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { ReactNode } from "react";

import { PROSE_WIDTH } from "@/components/SettingsSection";

// 看板各节共用的几块：数字卡片和放卡片的一行、组里带标题和说明的一小节、两节并排、等宽数字，
// 以及窄屏上代替表格的列表行。

export function StatTile({ label, value, note }: { label: string; value: string; note?: string }) {
  return (
    <Card>
      <VStack gap={1}>
        <Text type="supporting">{label}</Text>
        <Text type="display-3" size="xl" weight="semibold" hasTabularNumbers>
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
        {hint && (
          <Text type="supporting" style={{ maxWidth: PROSE_WIDTH }}>
            {hint}
          </Text>
        )}
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

/**
 * 后台内容区放得下表格吗；放不下时表格换成 `RowList`，不横向滚动。侧栏在 768px 以上常驻、占去约 260px：
 * 视口到 1024px，内容区有七百多像素，放得下三四列的小表；七列的服务健康、按模型的花费和用户表要九百多
 * 像素，视口到 1280px 才放得下，所以这几张传 `"table-wide"`。
 */
export function useWide(table: "table" | "table-wide" = "table"): boolean {
  return useMediaQuery(table === "table" ? "(min-width: 1024px)" : "(min-width: 1280px)", true);
}

export interface Row {
  id: string;
  label: string;
  /** 名字下面的副行：窄屏上放不进行尾的其余各列。 */
  description?: ReactNode;
  /** 行尾：这一行最要紧的数字。 */
  end?: string;
}

/** 窄屏上代替表格的列表：一行一项，名字在左、数字在行尾，其余各列缩进副行。 */
export function RowList({ rows }: { rows: Row[] }) {
  return (
    <List hasDividers density="compact">
      {rows.map((row) => (
        <ListItem
          key={row.id}
          label={row.label}
          description={row.description}
          endContent={row.end === undefined ? undefined : <Numeric>{row.end}</Numeric>}
        />
      ))}
    </List>
  );
}
