"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { HStack } from "@astryxdesign/core/HStack";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Table, pixel, proportional, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useEffect, useState } from "react";

import { CostSection } from "@/components/admin/CostSection";
import { AdminPage } from "@/components/admin/AdminPage";
import { Numeric, Pair, RowList, Section, StatTile, TileRow, useWide } from "@/components/admin/DashboardParts";
import { TrendChart } from "@/components/admin/TrendChart";
import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import {
  CALL_END_REASONS,
  CALL_RESULTS,
  countTicks,
  DASHBOARD_RANGES,
  type Dashboard,
  type DashboardRange,
  durationRange,
  type ErrorKind,
  formatCount,
  formatDuration,
  formatMs,
  formatPercent,
  formatShare,
  formatUsage,
  getCallsInProgress,
  getDashboard,
  type HealthStatus,
  healthStatus,
  isDashboardRange,
  LIVE_CALLS_REFRESH_MS,
  TURN_RESULTS,
} from "@/lib/dashboard";

const t = copy.admin.dashboard;

const STATUS_DOT: Record<HealthStatus, "success" | "warning" | "error" | "neutral"> = {
  ok: "success",
  degraded: "warning",
  failing: "error",
  idle: "neutral",
};

/**
 * 看板（后台默认页）：时间范围切换；回合和通话的几个数字，进行中的通话数（每分钟刷新）；回合和
 * 通话的趋势；回合结果；通话结果、时长和结束原因；服务健康（每项服务一行，部署者和自带密钥分开）；
 * 按角色的回合数和通话数。数字全由后端汇总，这里只负责排版和格式化。
 */
export function AdminDashboard() {
  const [range, setRange] = useState<DashboardRange>("24h");
  const [board, setBoard] = useState<Dashboard | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [inProgress, setInProgress] = useState<number | null>(null);

  useEffect(() => {
    let current = true;
    const refresh = () =>
      getCallsInProgress().then(
        (n) => current && setInProgress(n),
        () => current && setInProgress(null),
      );
    void refresh();
    const timer = setInterval(refresh, LIVE_CALLS_REFRESH_MS);
    return () => {
      current = false;
      clearInterval(timer);
    };
  }, []);

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
    <AdminPage
      width="wide"
      title={copy.admin.pages.dashboard}
      intro={t.intro}
      end={
        <SegmentedControl
          label={t.rangeLabel}
          value={range}
          onChange={(value) => isDashboardRange(value) && setRange(value)}
        >
          {DASHBOARD_RANGES.map((r) => (
            <SegmentedControlItem key={r} value={r} label={t.ranges[r]} />
          ))}
        </SegmentedControl>
      }
    >
      <VStack gap={6} paddingBlockStart={4}>
        {error !== null && <Banner status="error" title={t.failed(error)} />}
        {board === null ? (
          error === null && <Skeleton height={320} />
        ) : (
          <DashboardBody board={board} inProgress={inProgress} />
        )}
      </VStack>
    </AdminPage>
  );
}

/**
 * 先回答「用了多少」：一行数字卡；紧接着是服务健康（出事时第一眼要看到）；然后是用量的明细，
 * 小表两两并排；最后是花费。每一组是一节（标题、说明、内容、分隔线），和配置页、用户详情一致。
 */
function DashboardBody({ board, inProgress }: { board: Dashboard; inProgress: number | null }) {
  const { turns, calls } = board;
  return (
    <VStack>
      <TileRow>
        <StatTile
          label={t.tiles.turns}
          value={formatCount(turns.total)}
          note={t.tiles.turnsInCalls(formatCount(turns.in_calls))}
        />
        <StatTile
          label={t.tiles.calls}
          value={formatCount(calls.total)}
          note={t.tiles.callsOnOwnKeys(formatCount(calls.own_keys))}
        />
        <StatTile
          label={t.tiles.callsInProgress}
          value={inProgress === null ? "—" : formatCount(inProgress)}
          note={t.tiles.callsInProgressNote}
        />
        <StatTile label={t.tiles.activeUsers} value={formatCount(board.active_users)} />
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
      </TileRow>

      <SettingsSection title={t.health.title} description={t.health.hint}>
        <HealthTable board={board} />
      </SettingsSection>

      <SettingsSection title={t.groups.usage.title} description={t.groups.usage.hint}>
        <VStack gap={8}>
          <Pair>
            <Section title={t.trend.turns.title} hint={t.trend.turns.hint[board.bucket]}>
              <CountTrend board={board} series="turns" />
            </Section>
            <Section title={t.trend.calls.title} hint={t.trend.calls.hint[board.bucket]}>
              <CountTrend board={board} series="calls" />
            </Section>
          </Pair>

          <Pair>
            <Section title={t.results.title} hint={t.results.hint}>
              <CountsTable
                rows={TURN_RESULTS.map((result) => ({ id: result, label: t.results.names[result], count: turns.by_result[result] }))}
                total={turns.total}
                labelHeader={t.results.result}
                countHeader={t.results.turns}
                shareHeader={t.results.share}
              />
            </Section>
            <Section title={t.callResults.title} hint={t.callResults.hint}>
              <CountsTable
                rows={CALL_RESULTS.map((result) => ({ id: result, label: t.callResults.names[result], count: calls.by_result[result] }))}
                total={calls.total}
                labelHeader={t.callResults.result}
                countHeader={t.callResults.calls}
                shareHeader={t.callResults.share}
              />
            </Section>
          </Pair>

          <Pair>
            <Section
              title={t.durations.title}
              hint={t.durations.hint(formatDuration(calls.duration_s.p50), formatDuration(calls.duration_s.p90))}
            >
              <DurationsTable board={board} />
            </Section>
            <Section title={t.endReasons.title} hint={t.endReasons.hint}>
              <CountsTable
                rows={CALL_END_REASONS.map((reason) => ({ id: reason, label: t.endReasons.names[reason], count: calls.end_reasons[reason] }))}
                total={CALL_END_REASONS.reduce((sum, reason) => sum + calls.end_reasons[reason], 0)}
                labelHeader={t.endReasons.reason}
                countHeader={t.endReasons.calls}
                shareHeader={t.endReasons.share}
              />
            </Section>
          </Pair>

          <Section title={t.characters.title}>
            <CharactersTable board={board} />
          </Section>
        </VStack>
      </SettingsSection>

      <CostSection board={board} />
    </VStack>
  );
}

/** The turns, or the calls, in each stretch, with the users active in it. */
function CountTrend({ board, series }: { board: Dashboard; series: "turns" | "calls" }) {
  const words = t.trend[series];
  return (
    <TrendChart
      points={board.trend.map((p) => ({ start: p.start, value: p[series] }))}
      bucket={board.bucket}
      title={words.title}
      describe={(span, i) =>
        words.tooltip(span, formatCount(board.trend[i][series]), formatCount(board.trend[i].active_users))
      }
      empty={words.empty}
      ticks={countTicks}
      format={formatCount}
    />
  );
}

interface CountRow extends Record<string, unknown> {
  id: string;
  label: string;
  count: number;
}

/** How many of `total` fell under each row's label, and what share of it. */
function CountsTable({
  rows,
  total,
  labelHeader,
  countHeader,
  shareHeader,
}: {
  rows: CountRow[];
  total: number;
  labelHeader: string;
  countHeader: string;
  shareHeader: string;
}) {
  const wide = useWide();
  if (!wide) {
    return (
      <RowList
        rows={rows.map((row) => ({ id: row.id, label: row.label, end: `${formatCount(row.count)} · ${formatShare(row.count, total)}` }))}
      />
    );
  }
  const columns: TableColumn<CountRow>[] = [
    { key: "label", header: labelHeader, width: proportional(2), renderCell: (row) => row.label },
    { key: "count", header: countHeader, width: proportional(1), align: "end", renderCell: (row) => <Numeric>{formatCount(row.count)}</Numeric> },
    { key: "share", header: shareHeader, width: proportional(1), align: "end", renderCell: (row) => <Numeric>{formatShare(row.count, total)}</Numeric> },
  ];
  return <Table data={rows} columns={columns} idKey="id" density="compact" />;
}

interface DurationRow extends Record<string, unknown> {
  id: string;
  label: string;
  calls: number;
}

/** How many connected calls lasted how long, a bar against the commonest stretch. */
function DurationsTable({ board }: { board: Dashboard }) {
  const rows: DurationRow[] = board.calls.durations.map((d) => ({
    id: String(d.from_s),
    label: durationRange(d.from_s, d.to_s),
    calls: d.calls,
  }));
  const most = Math.max(0, ...rows.map((row) => row.calls));
  const wide = useWide();
  if (!wide) return <RowList rows={rows.map((row) => ({ id: row.id, label: row.label, end: formatCount(row.calls) }))} />;
  const columns: TableColumn<DurationRow>[] = [
    { key: "label", header: t.durations.range, width: proportional(1), renderCell: (row) => row.label },
    { key: "bar", header: "", width: proportional(2), renderCell: (row) => <ShareBar part={row.calls} whole={most} /> },
    { key: "calls", header: t.durations.calls, width: pixel(96), align: "end", renderCell: (row) => <Numeric>{formatCount(row.calls)}</Numeric> },
  ];
  return <Table data={rows} columns={columns} idKey="id" density="compact" />;
}

interface HealthRow extends Record<string, unknown> {
  id: string;
  row: Dashboard["health"][number];
}

function HealthTable({ board }: { board: Dashboard }) {
  const wide = useWide("table-wide");
  if (board.health.length === 0) return <Text color="secondary">{t.health.empty}</Text>;
  const rows: HealthRow[] = board.health.map((row) => ({ id: `${row.service}:${row.own_key}`, row }));
  if (!wide) {
    return (
      <RowList
        rows={rows.map(({ id, row }) => {
          const status = healthStatus(row);
          return {
            id,
            label: `${t.health.services[row.service] ?? row.service}${row.own_key ? ` · ${t.health.own}` : ""}`,
            description: (
              <VStack gap={0.5}>
                <HStack gap={1.5} vAlign="center">
                  <StatusDot variant={STATUS_DOT[status]} label={t.health.statuses[status]} />
                  <Text type="supporting" color="primary" hasTabularNumbers>
                    {`${t.health.statuses[status]} · ${t.health.calls} ${formatCount(row.calls)} · ${t.health.errorRate} ${formatPercent(row.error_rate)}`}
                  </Text>
                </HStack>
                <Text type="supporting" hasTabularNumbers>
                  {`${t.health.latency} ${formatMs(row.latency_ms.p50)} / ${formatMs(row.latency_ms.p95)} · ${formatUsage(row.usage, row.usage_unknown)}`}
                </Text>
                {errorsText(row) !== "—" && <Text type="supporting">{`${t.health.errors} ${errorsText(row)}`}</Text>}
              </VStack>
            ),
          };
        })}
      />
    );
  }
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
      renderCell: ({ row }) => errorsText(row),
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
  calls: number;
}

/** 每类错误各几次，没有时是「—」。 */
function errorsText(row: Dashboard["health"][number]): string {
  return (
    Object.entries(row.errors_by_kind)
      .map(([kind, n]) => `${t.health.errorKinds[kind as ErrorKind] ?? kind} ${formatCount(n ?? 0)}`)
      .join("、") || "—"
  );
}

function CharactersTable({ board }: { board: Dashboard }) {
  const wide = useWide();
  if (board.characters.length === 0) return <Text color="secondary">{t.characters.empty}</Text>;
  if (!wide) {
    return (
      <RowList
        rows={board.characters.map((c) => ({
          id: c.character_id,
          label: c.name ?? t.characters.removed,
          end: `${t.characters.turns} ${formatCount(c.turns)} · ${t.characters.calls} ${formatCount(c.calls)}`,
        }))}
      />
    );
  }
  const most = Math.max(...board.characters.map((c) => c.turns));
  const columns: TableColumn<CharacterRow>[] = [
    { key: "name", header: t.characters.character, width: proportional(1), renderCell: (row) => row.name ?? t.characters.removed },
    { key: "bar", header: "", width: proportional(2), renderCell: (row) => <ShareBar part={row.turns} whole={most} /> },
    { key: "turns", header: t.characters.turns, width: pixel(96), align: "end", renderCell: (row) => <Numeric>{formatCount(row.turns)}</Numeric> },
    { key: "calls", header: t.characters.calls, width: pixel(96), align: "end", renderCell: (row) => <Numeric>{formatCount(row.calls)}</Numeric> },
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
