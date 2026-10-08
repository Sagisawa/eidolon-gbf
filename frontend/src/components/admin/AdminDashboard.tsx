"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { HStack } from "@astryxdesign/core/HStack";
import { useMediaQuery } from "@astryxdesign/core/hooks";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { Table, pixel, proportional, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useCallback, useEffect, useRef, useState } from "react";

import { AppLink } from "@/components/AppLink";
import { CostSection } from "@/components/admin/CostSection";
import { AdminPage } from "@/components/admin/AdminPage";
import {
  Numeric,
  Pair,
  RowList,
  Section,
  StatTile,
  TileRow,
  TOUCH_LINK,
  TouchButton,
  useTouch,
  useWide,
} from "@/components/admin/DashboardParts";
import { CHART_INK, TrendChart } from "@/components/admin/TrendChart";
import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import {
  CALL_END_REASONS,
  CALL_RESULTS,
  countTicks,
  DASHBOARD_RANGES,
  DASHBOARD_REFRESH_MS,
  type Dashboard,
  type DashboardRange,
  durationRange,
  type ErrorKind,
  formatCount,
  formatDuration,
  formatFetchedAt,
  formatMs,
  formatPercent,
  formatShare,
  formatUsage,
  getCallsInProgress,
  getDashboard,
  type HealthStatus,
  healthStatus,
  healthSummary,
  isDashboardRange,
  rangeHref,
  splitZeroRows,
  TURN_RESULTS,
} from "@/lib/dashboard";

const t = copy.admin.dashboard;

/** 页首健康摘要的锚点：链到「服务健康」一节。 */
const HEALTH_ANCHOR = "health";
/** 摘要里最多点名几项有问题的服务，再多写「等 N 项」。 */
const SUMMARY_NAMES = 3;

const STATUS_DOT: Record<HealthStatus, "success" | "warning" | "error" | "neutral"> = {
  ok: "success",
  degraded: "warning",
  failing: "error",
  idle: "neutral",
};

/**
 * 看板（后台默认页）：时间范围切换；回合和通话的几个数字，进行中的通话数；回合和通话的趋势；回合结果；
 * 通话结果、时长和结束原因；服务健康（每项服务一行，部署者和自带密钥分开）；按角色的回合数和通话数。
 * 数字全由后端汇总，这里只负责排版和格式化。
 *
 * 数字要看得出新旧：页首写「数据截至 16:25」，旁边可以手动刷新；页面看得见时每分钟自动重新取一次
 * （切到别的标签页就停，切回来时过了一分钟就马上取），自动刷新不闪、不变淡。切换时间范围或手动刷新时，
 * 新数字到之前旧的整体变淡并标 aria-busy，不让人把上一个范围的数字当成这个范围的。取不到时旧数字留着，
 * 横幅写明下面是几点的数据。时间范围记在地址里（`?range=7d`），可以收藏、刷新不丢。
 */
export function AdminDashboard({ initialRange }: { initialRange: DashboardRange }) {
  const [range, setRange] = useState<DashboardRange>(initialRange);
  const [board, setBoard] = useState<Dashboard | null>(null);
  const [fetchedAt, setFetchedAt] = useState<Date | null>(null);
  /** 切换范围或手动刷新、新数字还没到：旧的变淡。自动刷新不算。 */
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inProgress, setInProgress] = useState<number | null>(null);
  const touch = useTouch();
  const rangeRef = useRef(range);
  /** 只认最后发出的那次请求：先发的自动刷新晚到，不能盖掉刚切换的范围。 */
  const latest = useRef(0);

  const load = useCallback((which: DashboardRange, quietly: boolean) => {
    const request = ++latest.current;
    if (!quietly) setLoading(true);
    getDashboard(which).then(
      (loaded) => {
        if (request !== latest.current) return;
        setBoard(loaded);
        setFetchedAt(new Date());
        setError(null);
        setLoading(false);
      },
      (e: Error) => {
        if (request !== latest.current) return;
        setError(e.message);
        setLoading(false);
      },
    );
  }, []);

  const refreshCalls = useCallback(() => {
    getCallsInProgress().then(setInProgress, () => setInProgress(null));
  }, []);

  useEffect(() => {
    rangeRef.current = range;
    load(range, false);
  }, [range, load]);

  useEffect(refreshCalls, [refreshCalls]);

  useWhileVisible(() => {
    load(rangeRef.current, true);
    refreshCalls();
  }, DASHBOARD_REFRESH_MS);

  function chooseRange(value: string) {
    if (!isDashboardRange(value)) return;
    setRange(value);
    window.history.replaceState(null, "", rangeHref(window.location.pathname, value));
  }

  function refresh() {
    load(range, false);
    refreshCalls();
  }

  const stamp = fetchedAt && formatFetchedAt(fetchedAt);
  /** 眼前的数字是上一个范围的：切换后还没到，或者切换那次没取到。 */
  const otherRange = board !== null && board.range !== range;
  const faded = loading || otherRange;
  return (
    <AdminPage
      width="wide"
      title={copy.admin.pages.dashboard}
      meta={
        // 手机上折成两行时不另加行距：两行各有 44px 的触控区，已经隔得开。
        <HStack gap={4} vAlign="center" wrap="wrap" style={{ rowGap: 0 }}>
          {/* 健康结论也是上一个范围的，和下面的数字一起变淡。 */}
          {board && (
            <HStack style={faded ? STALE : FRESH}>
              <HealthSummary board={board} />
            </HStack>
          )}
          <Freshness stamp={stamp} loading={loading} onRefresh={refresh} />
        </HStack>
      }
      intro={t.intro}
      end={
        <SegmentedControl label={t.rangeLabel} size={touch ? "lg" : "md"} value={range} onChange={chooseRange}>
          {DASHBOARD_RANGES.map((r) => (
            <SegmentedControlItem key={r} value={r} label={t.ranges[r]} />
          ))}
        </SegmentedControl>
      }
    >
      <VStack gap={6} paddingBlockStart={4}>
        {error !== null && (
          <Banner status="error" title={t.failed(error)} description={
              board && stamp
                ? otherRange
                  ? t.freshness.shownFromRange(stamp, t.ranges[board.range])
                  : t.freshness.shownFrom(stamp)
                : undefined
            } />
        )}
        {board === null ? (
          error === null && <Skeleton height={320} />
        ) : (
          <VStack aria-busy={loading} style={faded ? STALE : FRESH}>
            <DashboardBody board={board} inProgress={inProgress} />
          </VStack>
        )}
      </VStack>
    </AdminPage>
  );
}

/** 新数字到之前，旧的变淡：一眼看得出眼前的数字不属于刚选的范围。 */
const FRESH = { opacity: 1, transition: "opacity var(--duration-medium-min) var(--ease-standard)" };
const STALE = { ...FRESH, opacity: 0.45 };

/**
 * 页面看得见时每隔 `ms` 调一次 `tick`；藏起来（切到别的标签页、锁屏）就不调，再露出来时离上次已过
 * `ms` 就马上补一次。不在看的看板不必每分钟去问后端。
 */
function useWhileVisible(tick: () => void, ms: number) {
  const tickRef = useRef(tick);
  useEffect(() => {
    tickRef.current = tick;
  });
  useEffect(() => {
    let last = Date.now();
    const run = () => {
      last = Date.now();
      tickRef.current();
    };
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") run();
    }, ms);
    const onVisible = () => {
      if (document.visibilityState === "visible" && Date.now() - last >= ms) run();
    };
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      clearInterval(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [ms]);
}

/** 「数据截至 16:25」和刷新键。第一次读取时写「正在读取…」，占住这一行，数字到了页首不跳。 */
function Freshness({ stamp, loading, onRefresh }: { stamp: string | null; loading: boolean; onRefresh: () => void }) {
  return (
    <HStack gap={1} vAlign="center">
      <Text type="supporting" hasTabularNumbers>
        {stamp ? t.freshness.at(stamp) : t.freshness.loading}
      </Text>
      {stamp && (
        <TouchButton variant="ghost" size="sm" label={t.freshness.refreshLabel} isLoading={loading} onClick={onRefresh}>
          {t.freshness.refresh}
        </TouchButton>
      )}
    </HStack>
  );
}

/**
 * 页首的一行健康结论：都正常、没有调用，或者点名出问题的服务（最糟的在前），链到「服务健康」一节。
 * 只占一行，首屏的主体仍是下面回答「用了多少」的数字卡。
 */
function HealthSummary({ board }: { board: Dashboard }) {
  const touch = useTouch();
  const summary = healthSummary(board.health);
  const words = t.health.summary;
  let variant: "success" | "warning" | "error" | "neutral";
  let text: string;
  if (summary.kind === "problems") {
    variant = STATUS_DOT[summary.worst];
    const named = summary.rows.slice(0, SUMMARY_NAMES).map((row) =>
      words.problem(
        `${t.health.services[row.service] ?? row.service}${row.own_key ? `（${t.health.own}）` : ""}`,
        t.health.statuses[healthStatus(row)],
        formatPercent(row.error_rate),
      ),
    );
    const more = summary.rows.length > SUMMARY_NAMES ? words.more(formatCount(summary.rows.length)) : "";
    text = named.join("、") + more;
  } else {
    variant = summary.kind === "ok" ? "success" : "neutral";
    text = words[summary.kind];
  }
  return (
    <HStack gap={3} vAlign="center" wrap="wrap">
      <HStack gap={1.5} vAlign="center">
        <StatusDot variant={variant} label={text} />
        <Text weight="medium">{text}</Text>
      </HStack>
      <AppLink href={`#${HEALTH_ANCHOR}`} style={touch ? TOUCH_LINK : undefined}>
        {words.link}
      </AppLink>
    </HStack>
  );
}

/**
 * 先回答「用了多少」：一行数字卡（手机上只留回合、通话、进行中、活跃用户四张）；紧接着是服务健康
 * （出事时第一眼要看到，页首已有一句结论）；然后是用量的明细，小表两两并排；最后是花费。每一组是
 * 一节（标题、说明、内容、分隔线），和配置页、用户详情一致。
 */
function DashboardBody({ board, inProgress }: { board: Dashboard; inProgress: number | null }) {
  const { turns, calls } = board;
  const phone = !useMediaQuery("(min-width: 768px)", true);
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
        <StatTile label={t.tiles.activeUsers} value={formatCount(board.active_users)} note={t.tiles.activeUsersNote} />
        {!phone && (
          <StatTile
            label={t.tiles.ownKeys}
            value={formatCount(turns.own_keys)}
            note={t.tiles.ownKeysShare(formatShare(turns.own_keys, turns.total))}
          />
        )}
        {!phone && (
          <StatTile
            label={t.tiles.timeToSpeak}
            value={formatMs(turns.time_to_speak_ms.p50)}
            note={turns.time_to_speak_ms.p90 === null ? undefined : t.tiles.timeToSpeakP90(formatMs(turns.time_to_speak_ms.p90))}
          />
        )}
      </TileRow>

      <SettingsSection id={HEALTH_ANCHOR} title={t.health.title} description={t.health.hint}>
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
      total={words.total(
        t.ranges[board.range],
        formatCount(series === "turns" ? board.turns.total : board.calls.total),
        formatCount(board.active_users),
      )}
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
  /** 合并起来的零值行：为 0 的各项名字。 */
  zeroLabels?: string;
}

/** How many of `total` fell under each row's label, and what share of it. The rows at 0
 * fold into one last line, 「其余 N 项为 0」, naming them beneath. */
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
  const { counted, zero } = splitZeroRows(rows);
  const shown: CountRow[] =
    zero.length === 0
      ? counted
      : [
          ...counted,
          {
            id: "zero",
            label: (counted.length === 0 ? t.zeroRows.all : t.zeroRows.rest)(formatCount(zero.length)),
            count: 0,
            zeroLabels: zero.map((row) => row.label).join("、"),
          },
        ];
  if (!wide) {
    return (
      <RowList
        rows={shown.map((row) =>
          row.zeroLabels === undefined
            ? { id: row.id, label: row.label, end: `${formatCount(row.count)} · ${formatShare(row.count, total)}` }
            : // 包成节点：纯字符串的副行会被截成一行，名字要全列出来。
              { id: row.id, label: row.label, description: <Text type="supporting">{row.zeroLabels}</Text> },
        )}
      />
    );
  }
  const counts = (render: (row: CountRow) => string) => (row: CountRow) =>
    row.zeroLabels === undefined ? <Numeric>{render(row)}</Numeric> : null;
  const columns: TableColumn<CountRow>[] = [
    {
      key: "label",
      header: labelHeader,
      width: proportional(2),
      renderCell: (row) =>
        row.zeroLabels === undefined ? (
          row.label
        ) : (
          <VStack gap={0.5}>
            <Text color="secondary">{row.label}</Text>
            <Text type="supporting">{row.zeroLabels}</Text>
          </VStack>
        ),
    },
    { key: "count", header: countHeader, width: proportional(1), align: "end", renderCell: counts((row) => formatCount(row.count)) },
    { key: "share", header: shareHeader, width: proportional(1), align: "end", renderCell: counts((row) => formatShare(row.count, total)) },
  ];
  return <Table data={shown} columns={columns} idKey="id" density="compact" />;
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
                <HStack gap={1.5} vAlign="center" wrap="wrap">
                  {isTrouble(status) && <HealthStatusText status={status} size="supporting" />}
                  <Text type="supporting" color="primary" hasTabularNumbers>
                    {`${t.health.calls} ${formatCount(row.calls)} · ${t.health.errorRate} ${formatPercent(row.error_rate)}`}
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
      renderCell: ({ row }) => <HealthStatusText status={healthStatus(row)} />,
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

function isTrouble(status: HealthStatus): boolean {
  return status === "degraded" || status === "failing";
}

/**
 * 一行服务的状态。正常和没有调用是常态，只写次要色的字、不带点：七行都是绿点只是噪音，页首已经说了
 * 「各项服务正常」；出错偏多、大量出错才带点、加粗，一眼找得到。
 */
function HealthStatusText({ status, size = "body" }: { status: HealthStatus; size?: "body" | "supporting" }) {
  const label = t.health.statuses[status];
  const type = size === "supporting" ? "supporting" : undefined;
  if (!isTrouble(status)) {
    return (
      <Text type={type} color="secondary">
        {label}
      </Text>
    );
  }
  return (
    <HStack gap={1.5} vAlign="center">
      <StatusDot variant={STATUS_DOT[status]} label={label} />
      <Text type={type} color="primary" weight="semibold">
        {label}
      </Text>
    </HStack>
  );
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
      <rect x={0} y={2} width={`${width}%`} height={8} rx={4} fill={CHART_INK} />
    </svg>
  );
}
