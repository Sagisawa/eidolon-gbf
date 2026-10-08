"use client";

import { Table, pixel, proportional, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";

import { Numeric, Pair, RowList, Section, StatTile, TileRow, useWide } from "@/components/admin/DashboardParts";
import { TrendChart } from "@/components/admin/TrendChart";
import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import {
  amountTicks,
  type Cost,
  costPriceDates,
  type CostRow,
  costStatus,
  formatMoney,
  formatMoneyTick,
  formatPrice,
  formatRowUsage,
  formatTotals,
  matchText,
  trendCurrencies,
} from "@/lib/adminPrices";
import { type Dashboard, formatCount, type ServiceName } from "@/lib/dashboard";

const t = copy.admin.dashboard.cost;
const services = copy.admin.dashboard.health.services;

function serviceName(service: ServiceName): string {
  return services[service] ?? service;
}

/**
 * 看板的花费一组：每种币种的合计（估算，不扣免费额度，不换算汇率）、每种币种一张趋势图（和按服务的明细
 * 两两并排）、按模型的明细（没有单价的模型显示用量和「未设单价」），以及自带密钥的用量（只有数量，不算钱）。
 * 金额全由后端按单价算好。
 */
export function CostSection({ board }: { board: Dashboard }) {
  const { cost } = board;
  const dates = costPriceDates(cost);
  const unknown = cost.usage_unknown > 0 ? t.totalNote(formatCount(cost.usage_unknown)) : undefined;
  return (
    <SettingsSection title={t.title} description={t.hint(dates.catalog, dates.preset)}>
      <VStack gap={8}>
        {cost.totals.length === 0 ? (
          <Text color="secondary">{t.empty}</Text>
        ) : (
          <TileRow>
            {cost.totals.map((total) => (
              <StatTile
                key={total.currency}
                label={`${t.total} · ${total.currency}`}
                value={formatMoney(total.amount, total.currency)}
                note={unknown}
              />
            ))}
          </TileRow>
        )}

        <Pair>
          {trendCurrencies(cost.trend).map((currency) => (
            <Section key={currency} title={t.trendTitle(currency)} hint={t.trendHint[board.bucket]}>
              <TrendChart
                points={cost.trend.map((p) => ({ start: p.start, value: p.amounts[currency] ?? 0 }))}
                bucket={board.bucket}
                title={t.trendTitle(currency)}
                total={t.trendTotal(
                  copy.admin.dashboard.ranges[board.range],
                  formatMoneyTick(cost.totals.find((c) => c.currency === currency)?.amount ?? 0, currency),
                )}
                describe={(span, i) => t.trendReadout(span, formatMoneyTick(cost.trend[i].amounts[currency] ?? 0, currency))}
                empty={t.trendEmpty}
                ticks={amountTicks}
                format={(value) => formatMoneyTick(value, currency)}
              />
            </Section>
          ))}
          {cost.services.length > 0 && (
            <Section title={t.byService}>
              <ServicesTable cost={cost} />
            </Section>
          )}
        </Pair>

        {cost.rows.length > 0 && (
          <Section title={t.byModel}>
            <ModelsTable rows={cost.rows} />
          </Section>
        )}

        {cost.own_keys.length > 0 && (
          <Section title={t.own.title} hint={t.own.hint}>
            <OwnKeysTable cost={cost} />
          </Section>
        )}
      </VStack>
    </SettingsSection>
  );
}

interface ServiceRow extends Record<string, unknown> {
  row: Cost["services"][number];
  id: string;
}

function serviceNotes(row: Cost["services"][number]): string {
  return [
    row.unpriced > 0 ? t.unpricedModels(formatCount(row.unpriced)) : null,
    row.usage_unknown > 0 ? t.unknownCalls(formatCount(row.usage_unknown)) : null,
  ]
    .filter(Boolean)
    .join("，");
}

function ServicesTable({ cost }: { cost: Cost }) {
  const wide = useWide();
  const rows: ServiceRow[] = cost.services.map((row) => ({ id: row.service, row }));
  if (!wide) {
    return (
      <RowList
        rows={rows.map(({ id, row }) => ({
          id,
          label: serviceName(row.service),
          description: serviceNotes(row) || undefined,
          end: formatTotals(row.totals),
        }))}
      />
    );
  }
  const columns: TableColumn<ServiceRow>[] = [
    { key: "service", header: t.service, width: proportional(1.5), renderCell: ({ row }) => serviceName(row.service) },
    { key: "amount", header: t.amount, width: proportional(1.5), align: "end", renderCell: ({ row }) => <Numeric>{formatTotals(row.totals)}</Numeric> },
    {
      key: "notes",
      header: t.notes,
      width: proportional(2),
      renderCell: ({ row }) => serviceNotes(row) || "—",
    },
  ];
  return <Table data={rows} columns={columns} idKey="id" density="compact" />;
}

interface ModelRow extends Record<string, unknown> {
  id: string;
  row: CostRow;
}

function ModelsTable({ rows }: { rows: CostRow[] }) {
  const data: ModelRow[] = rows.map((row) => ({
    id: `${row.service}|${row.provider}|${row.model}|${row.unit ?? ""}`,
    row,
  }));
  const wide = useWide("table-wide");
  if (!wide) {
    return (
      <RowList
        rows={data.map(({ id, row }) => ({
          id,
          label: row.model,
          description: (
            <VStack gap={0.5}>
              <Text type="supporting" wordBreak="break-word">{`${serviceName(row.service)} · ${row.provider}`}</Text>
              <Text type="supporting">{formatRowUsage(row)}</Text>
              <PriceText row={row} />
            </VStack>
          ),
          end: row.amount === null || row.currency === null ? "—" : formatMoney(row.amount, row.currency),
        }))}
      />
    );
  }
  const columns: TableColumn<ModelRow>[] = [
    { key: "service", header: t.service, width: proportional(1.2), renderCell: ({ row }) => serviceName(row.service) },
    {
      key: "model",
      header: t.model,
      width: proportional(2),
      renderCell: ({ row }) => (
        <VStack gap={0.5}>
          <Text wordBreak="break-word">{row.model}</Text>
          <Text type="supporting" wordBreak="break-word">
            {row.provider}
          </Text>
        </VStack>
      ),
    },
    {
      key: "usage",
      header: t.usage,
      width: proportional(2),
      renderCell: ({ row }) => (
        <VStack gap={0.5}>
          <Text>{formatRowUsage(row)}</Text>
          {row.usage_unknown > 0 && <Text type="supporting">{t.unknownCalls(formatCount(row.usage_unknown))}</Text>}
        </VStack>
      ),
    },
    {
      key: "price",
      header: t.price,
      width: proportional(2),
      renderCell: ({ row }) => {
        const status = costStatus(row);
        if (status === "unpriced") return <Token size="sm" color="orange" label={t.unpriced} />;
        if (status === "unknown" || row.price === null || row.unit === null) return <Text color="secondary">{t.usageUnknown}</Text>;
        return (
          <VStack gap={0.5}>
            <Text>{formatPrice(row.price, row.unit)}</Text>
            <Text type="supporting" wordBreak="break-word">
              {[t.sources[row.price.source], row.price.source === "catalog_upstream" ? matchText(row.price) : null]
                .filter(Boolean)
                .join(" · ")}
            </Text>
          </VStack>
        );
      },
    },
    {
      key: "amount",
      header: t.amount,
      width: pixel(112),
      align: "end",
      renderCell: ({ row }) =>
        row.amount === null || row.currency === null ? "—" : <Numeric>{formatMoney(row.amount, row.currency)}</Numeric>,
    },
  ];
  return <Table data={data} columns={columns} idKey="id" density="compact" />;
}

interface OwnRow extends Record<string, unknown> {
  id: string;
  row: Cost["own_keys"][number];
}

/** 窄屏上一个模型的单价一行字：没有单价时照说。 */
function PriceText({ row }: { row: CostRow }) {
  const status = costStatus(row);
  if (status === "unpriced") return <Text type="supporting">{t.unpriced}</Text>;
  if (status === "unknown" || row.price === null || row.unit === null) return <Text type="supporting">{t.usageUnknown}</Text>;
  return <Text type="supporting">{`${formatPrice(row.price, row.unit)} · ${t.sources[row.price.source]}`}</Text>;
}

function OwnKeysTable({ cost }: { cost: Cost }) {
  const wide = useWide();
  const data: OwnRow[] = cost.own_keys.map((row) => ({ id: `${row.service}|${row.unit ?? ""}`, row }));
  if (!wide) {
    return (
      <RowList
        rows={data.map(({ id, row }) => ({
          id,
          label: serviceName(row.service),
          description: formatRowUsage(row),
          end: formatCount(row.calls),
        }))}
      />
    );
  }
  const columns: TableColumn<OwnRow>[] = [
    { key: "service", header: t.service, width: proportional(1.5), renderCell: ({ row }) => serviceName(row.service) },
    { key: "calls", header: t.own.calls, width: pixel(88), align: "end", renderCell: ({ row }) => <Numeric>{formatCount(row.calls)}</Numeric> },
    { key: "usage", header: t.usage, width: proportional(2.5), renderCell: ({ row }) => formatRowUsage(row) },
  ];
  return <Table data={data} columns={columns} idKey="id" density="compact" />;
}
