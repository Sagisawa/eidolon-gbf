"use client";

import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { Grid } from "@astryxdesign/core/Grid";
import { Heading } from "@astryxdesign/core/Heading";
import { useMediaQuery } from "@astryxdesign/core/hooks";
import { List, ListItem } from "@astryxdesign/core/List";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import type { ComponentProps, CSSProperties, ReactNode } from "react";

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

/** 数字卡排成一行：最多 `max` 张一行，窄下来按每张不窄于 140px 折行（手机上一行两张）。 */
export function TileRow({ max = 6, children }: { max?: number; children: ReactNode }) {
  return (
    <Grid columns={{ minWidth: 140, max }} gap={3}>
      {children}
    </Grid>
  );
}

/** 一组数字卡，上面一行小字说明这组数字是什么时候的（「此刻」「30 天内」）。 */
export function TileGroup({ caption, style, children }: { caption: string; style?: CSSProperties; children: ReactNode }) {
  return (
    <VStack gap={2} style={style}>
      <Text type="supporting">{caption}</Text>
      {children}
    </VStack>
  );
}

/**
 * 组里的一小节（`SettingsSection` 是一组，这里是组里的一项）：h3 标题、说明和内容。
 * 表格是小节的最后一项时，Astryx 会按 `--container-padding-block-end`（24px）让它向下出血，压进下面一节的
 * 间距里（下一行的小节标题只隔十几像素）；小节里不要上下出血。
 */
export function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <VStack gap={3} style={NO_BLOCK_BLEED}>
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

/**
 * 两小节并排：宽栏里左右各一半，窄到放不下两张不窄于 360px 的表时上下排。
 * Astryx 的表格在内容区里按 `--container-padding-inline-*`（24px）向两侧出血，并排时两张表各伸进列距
 * 24px，32px 的列距被吃成重叠，横线连成一张表。这里把出血收到 8px：表格的首末列内边距也随之是 8px，
 * 字仍和小节标题对齐，两张表的横线之间留出 16px。
 */
export function Pair({ children }: { children: ReactNode }) {
  return (
    <Grid columns={{ minWidth: 360, max: 2 }} columnGap={8} rowGap={8} align="start" style={PAIR_BLEED}>
      {children}
    </Grid>
  );
}

const NO_BLOCK_BLEED = {
  "--container-padding-block-start": "0px",
  "--container-padding-block-end": "0px",
} as CSSProperties;

const PAIR_BLEED = {
  "--container-padding-inline-start": "var(--spacing-2)",
  "--container-padding-inline-end": "var(--spacing-2)",
} as CSSProperties;

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

/**
 * 手机宽度或触屏：行内的小按钮（ghost sm，28px 高）和页内链接要撑到 44px 的触控区（`TOUCH_TARGET`）。
 * 桌面上用鼠标时保持原来的紧凑。
 */
export function useTouch(): boolean {
  const coarse = useMediaQuery("(pointer: coarse)", false);
  const phone = !useMediaQuery("(min-width: 768px)", true);
  return coarse || phone;
}

/** 触控区下限 44px（`--spacing-11`），宽高都不小于它。 */
export const TOUCH_TARGET: CSSProperties = { minHeight: "var(--spacing-11)", minWidth: "var(--spacing-11)" };

/** 单独成行的文字链接（页内链接、返回链接）的触控区：撑到 44px 高，字仍在这一行里居中。 */
export const TOUCH_LINK: CSSProperties = { ...TOUCH_TARGET, display: "inline-flex", alignItems: "center" };

/** 后台的按钮：Astryx `Button`，手机或触屏上撑到 44px（md 默认 32px、sm 28px）。 */
export function TouchButton({ style, ...props }: ComponentProps<typeof Button>) {
  const touch = useTouch();
  return <Button {...props} style={touch ? { ...TOUCH_TARGET, ...style } : style} />;
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
