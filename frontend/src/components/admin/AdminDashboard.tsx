"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { Card } from "@astryxdesign/core/Card";
import { Grid } from "@astryxdesign/core/Grid";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Table, pixel, proportional, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useEffect, useState, type ReactNode } from "react";

import { TurnTrendChart } from "@/components/admin/TurnTrendChart";
import { copy } from "@/i18n";
import {
  DASHBOARD_RANGES,
  type Dashboard,
  type DashboardRange,
  type ErrorKind,
  formatCount,
  formatMs,
  formatPercent,
  formatShare,
  formatUsage,
  getDashboard,
  type HealthStatus,
  healthStatus,
  isDashboardRange,
  TURN_RESULTS,
  type TurnResult,
} from "@/lib/dashboard";

const t = copy.admin.dashboard;

const STATUS_DOT: Record<HealthStatus, "success" | "warning" | "error" | "neutral"> = {
  ok: "success",
  degraded: "warning",
  failing: "error",
  idle: "neutral",
};

/**
 * 看板（后台默认页）：时间范围切换；回合的几个数字；回合趋势；回合结果；服务健康（每项服务一行，
 * 部署者和自带密钥分开）；按角色的回合数。数字全由后端汇总，这里只负责排版和格式化。
 */
export function AdminDashboard() {
  const [range, setRange] = useState<DashboardRange>("24h");
  const [board, setBoard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let current = true;
    setError(null);
    getDashboard(range).then(
      (loaded) => current && setBoard(loaded),
      (e: Error) => current && setError(e.message),
    );
    return () => {
      current = false;
    };
  }, [range]);

  return (
    <VStack gap={6}>
      <VStack gap={2}>
        <Heading level={1} style={{ fontSize: "var(--text-large-size)" }}>
          {copy.admin.pages.dashboard}
        </Heading>
        <Text as="p" color="secondary">
          {t.intro}
        </Text>
      </VStack>

      <SegmentedControl
        label={t.rangeLabel}
        value={range}
        onChange={(value) => isDashboardRange(value) && setRange(value)}
      >
        {DASHBOARD_RANGES.map((r) => (
          <SegmentedControlItem key={r} value={r} label={t.ranges[r]} />
        ))}
      </SegmentedControl>

      {error !== null && <Banner status="error" title={t.failed(error)} />}
      {board === null ? (
        error === null && <Skeleton height={320} />
      ) : (
        <DashboardBody board={board} />
      )}
    </VStack>
  );
}

function DashboardBody({ board }: { board: Dashboard }) {
  const turns = board.turns;
  return (
    <VStack gap={8}>
      <Grid columns={{ minWidth: 160, max: 4 }} gap={3}>
        <StatTile label={t.tiles.turns} value={formatCount(turns.total)} />
        <StatTile label={t.tiles.activeUsers} value={formatCount(turns.active_users)} />
        <StatTile
          label={t.tiles.ownKeys}
          value={formatCount(turns.own_keys)}
          note={t.tiles.ownKeysShare(formatShare(turns.own_keys, turns.total))}
        />
        <StatTile
          label={t.tiles.timeToSpeak}
          value={formatMs(turns.time_to_speak_ms.p50)}
          note={turns.time_to_speak_ms.p90 === null ? undefined : t.tiles.timeToSpeakP90(formatMs(turns.time_to_speak_ms.p90))}
        />
      </Grid>

      <Section title={t.trend.title} hint={t.trend.hint[board.bucket]}>
        <TurnTrendChart points={board.trend} bucket={board.bucket} />
      </Section>

      <Section title={t.results.title} hint={t.results.hint}>
        <ResultsTable board={board} />
      </Section>

      <Section title={t.health.title} hint={t.health.hint}>
        <HealthTable board={board} />
      </Section>

      <Section title={t.characters.title}>
        <CharactersTable board={board} />
      </Section>
    </VStack>
  );
}

function StatTile({ label, value, note }: { label: string; value: string; note?: string }) {
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

function Section({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
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

interface ResultRow extends Record<string, unknown> {
  result: TurnResult;
  turns: number;
}

function ResultsTable({ board }: { board: Dashboard }) {
  const total = board.turns.total;
  const rows: ResultRow[] = TURN_RESULTS.map((result) => ({ result, turns: board.turns.by_result[result] }));
  const columns: TableColumn<ResultRow>[] = [
    { key: "result", header: t.results.result, width: proportional(2), renderCell: (row) => t.results.names[row.result] },
    { key: "turns", header: t.results.turns, width: proportional(1), align: "end", renderCell: (row) => <Numeric>{formatCount(row.turns)}</Numeric> },
    { key: "share", header: t.results.share, width: proportional(1), align: "end", renderCell: (row) => <Numeric>{formatShare(row.turns, total)}</Numeric> },
  ];
  return <Table data={rows} columns={columns} idKey="result" density="compact" />;
}

interface HealthRow extends Record<string, unknown> {
  id: string;
  row: Dashboard["health"][number];
}

function HealthTable({ board }: { board: Dashboard }) {
  if (board.health.length === 0) return <Text color="secondary">{t.health.empty}</Text>;
  const rows: HealthRow[] = board.health.map((row) => ({ id: `${row.service}:${row.own_key}`, row }));
  const columns: TableColumn<HealthRow>[] = [
    {
      key: "service",
      header: t.health.service,
      width: proportional(2),
      renderCell: ({ row }) => (
        <VStack gap={0.5}>
          <Text>{t.health.services[row.service] ?? row.service}</Text>
          {row.own_key && <Text type="supporting">{t.health.own}</Text>}
        </VStack>
      ),
    },
    {
      key: "status",
      header: t.health.status,
      width: proportional(1.5),
      renderCell: ({ row }) => {
        const status = healthStatus(row);
        return (
          <HStack gap={1.5} vAlign="center">
            <StatusDot variant={STATUS_DOT[status]} label={t.health.statuses[status]} />
            <Text>{t.health.statuses[status]}</Text>
          </HStack>
        );
      },
    },
    { key: "calls", header: t.health.calls, width: pixel(88), align: "end", renderCell: ({ row }) => <Numeric>{formatCount(row.calls)}</Numeric> },
    { key: "errorRate", header: t.health.errorRate, width: pixel(88), align: "end", renderCell: ({ row }) => <Numeric>{formatPercent(row.error_rate)}</Numeric> },
    {
      key: "errors",
      header: t.health.errors,
      width: proportional(2),
      renderCell: ({ row }) =>
        Object.entries(row.errors_by_kind)
          .map(([kind, n]) => `${t.health.errorKinds[kind as ErrorKind] ?? kind} ${formatCount(n ?? 0)}`)
          .join("、") || "—",
    },
    {
      key: "latency",
      header: t.health.latency,
      width: proportional(1.5),
      align: "end",
      renderCell: ({ row }) => <Numeric>{`${formatMs(row.latency_ms.p50)} / ${formatMs(row.latency_ms.p95)}`}</Numeric>,
    },
    { key: "usage", header: t.health.usage, width: proportional(2.5), renderCell: ({ row }) => formatUsage(row.usage, row.usage_unknown) },
  ];
  return <Table data={rows} columns={columns} idKey="id" density="compact" />;
}

interface CharacterRow extends Record<string, unknown> {
  character_id: string;
  name: string | null;
  turns: number;
}

function CharactersTable({ board }: { board: Dashboard }) {
  if (board.characters.length === 0) return <Text color="secondary">{t.characters.empty}</Text>;
  const most = Math.max(...board.characters.map((c) => c.turns));
  const columns: TableColumn<CharacterRow>[] = [
    { key: "name", header: t.characters.character, width: proportional(1), renderCell: (row) => row.name ?? t.characters.removed },
    { key: "bar", header: "", width: proportional(2), renderCell: (row) => <ShareBar part={row.turns} whole={most} /> },
    { key: "turns", header: t.characters.turns, width: pixel(96), align: "end", renderCell: (row) => <Numeric>{formatCount(row.turns)}</Numeric> },
  ];
  return <Table data={board.characters} columns={columns} idKey="character_id" density="compact" />;
}

/** A thin bar, as long against the longest as `part` is against `whole`; the count beside
 * it in its own column carries the number. */
function ShareBar({ part, whole }: { part: number; whole: number }) {
  const width = whole > 0 ? (part / whole) * 100 : 0;
  return (
    <svg width="100%" height={12} aria-hidden="true" style={{ display: "block" }}>
      <rect x={0} y={2} width={`${width}%`} height={8} rx={4} fill="var(--color-data-categorical-blue)" />
    </svg>
  );
}

function Numeric({ children }: { children: string }) {
  return <Text hasTabularNumbers>{children}</Text>;
}
