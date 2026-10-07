// 单价和花费（GLOSSARY「看板」）：后端按单价估算的部署者花费，以及「配置」页里的单价。
// 花费全由后端算好，这里只负责措辞、格式化和单价表单的换算与校验。

import { apiHeaders, json } from "@/lib/api";
import { formatCount, type ServiceName } from "@/lib/dashboard";

export type Unit = "tokens" | "bytes" | "seconds";
export const UNITS: Unit[] = ["tokens", "bytes", "seconds"];

export type Currency = "USD" | "CNY";
export const CURRENCIES: Currency[] = ["USD", "CNY"];

/** 每 `per` 个单位的输入、输出价；`output` 为 null 时输出按输入价算。 */
export type Price = {
  input: number;
  output: number | null;
  currency: string;
  per: number;
  /** 预设：整理价格的日期；后台设定：设定的日期。 */
  as_of: string;
  source: "preset" | "override";
};

export type Amount = { currency: string; amount: number };

/** 一个模型在这段时间里的部署者用量和花费。`unit` 为 null 表示这个模型的调用都没说用量。 */
export type CostRow = {
  service: ServiceName;
  provider: string;
  model: string;
  unit: string | null;
  calls: number;
  usage_unknown: number;
  input: number | null;
  output: number | null;
  price: Price | null;
  currency: string | null;
  amount: number | null;
};

export type Cost = {
  totals: Amount[];
  services: { service: ServiceName; totals: Amount[]; unpriced: number; usage_unknown: number }[];
  rows: CostRow[];
  usage_unknown: number;
  trend: { start: string; amounts: Record<string, number> }[];
  own_keys: { service: ServiceName; unit: string | null; calls: number; input: number | null; output: number | null }[];
  preset_as_of: string | null;
};

export type PriceEntry = {
  provider: string;
  model: string;
  unit: string;
  per: number;
  preset: Price | null;
  override: Price | null;
};

export type Prices = {
  preset_as_of: string | null;
  prices: PriceEntry[];
  /** 最近用过却没有单价的模型，名字和运行记录里的一致。 */
  unpriced: { service: ServiceName; provider: string; model: string; unit: string }[];
};

const NONE = "—";

const SYMBOLS: Record<string, string> = { USD: "$", CNY: "¥" };

/** 一笔钱："$0.012"、"¥1,234.57"；不到 0.0001 的写成 "<$0.0001"，免得估出来的小钱显示成 0。 */
export function formatMoney(amount: number, currency: string): string {
  const sign = SYMBOLS[currency];
  const money = (text: string) => (sign ? `${sign}${text}` : `${text} ${currency}`);
  if (amount <= 0) return money("0");
  if (amount < 0.0001) return `<${money("0.0001")}`;
  if (amount >= 1) {
    return money(amount.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 }));
  }
  return money(String(Number(amount.toPrecision(2))));
}

/** 几种币种的合计，各算各的、不换算："$1.20 + ¥3.40"；一笔都没有时是 "—"。 */
export function formatTotals(totals: Amount[]): string {
  return totals.map((t) => formatMoney(t.amount, t.currency)).join(" + ") || NONE;
}

const UNIT_WORDS: Record<string, string> = { tokens: "tokens", bytes: "字节", seconds: "秒" };
const PER_WORDS: Record<string, string> = { tokens: "每百万 tokens", bytes: "每百万字节", seconds: "每小时" };

export function unitWord(unit: string): string {
  return UNIT_WORDS[unit] ?? unit;
}

/** 单价的计价口径："每百万 tokens"、"每小时"。 */
export function perWord(unit: string, per: number): string {
  return PER_WORDS[unit] ?? `每 ${formatCount(per)} ${unitWord(unit)}`;
}

/** 一个单价："输入 $2 · 输出 $8 / 每百万 tokens"；输出不单独计价时只有一个数。 */
export function formatPrice(price: Price, unit: string): string {
  const input = formatUnitPrice(price.input, price.currency);
  const amounts =
    price.output === null ? input : `输入 ${input} · 输出 ${formatUnitPrice(price.output, price.currency)}`;
  return `${amounts} / ${perWord(unit, price.per)}`;
}

/** 单价本身照原样写，不像花费那样四舍五入到两位有效数字。 */
function formatUnitPrice(amount: number, currency: string): string {
  const sign = SYMBOLS[currency];
  return sign ? `${sign}${amount}` : `${amount} ${currency}`;
}

/** 一行的用量："输入 2,000 · 输出 1,000 tokens"、"3,600 秒"；全都没说用量时是 "—"。 */
export function formatRowUsage(row: Pick<CostRow, "unit" | "input" | "output">): string {
  if (row.unit === null) return NONE;
  const word = unitWord(row.unit);
  if (row.output === null) return `${row.input === null ? NONE : formatCount(row.input)} ${word}`;
  return `输入 ${row.input === null ? NONE : formatCount(row.input)} · 输出 ${formatCount(row.output)} ${word}`;
}

/** 一行花费怎么显示：算出了钱；有用量但没有单价（「未设单价」）；或者调用都没说用量。 */
export type CostStatus = "priced" | "unpriced" | "unknown";

export function costStatus(row: Pick<CostRow, "unit" | "price">): CostStatus {
  if (row.unit === null) return "unknown";
  return row.price === null ? "unpriced" : "priced";
}

/** 花费趋势里出现过的币种，每种画一张图（不同币种不能共用一根轴）。 */
export function trendCurrencies(trend: Cost["trend"]): string[] {
  return [...new Set(trend.flatMap((point) => Object.keys(point.amounts)))].sort();
}

/** 金额轴的刻度：从 0 起，间隔是 10 的幂的 1、2、5 倍，最多 4 段，可以是小数。 */
export function amountTicks(max: number): number[] {
  if (max <= 0) return [0, 1];
  const rough = max / 4;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough) ?? 10 * power;
  const ticks: number[] = [];
  for (let i = 0; ticks.length === 0 || ticks[ticks.length - 1] < max; i += 1) {
    ticks.push(Number((i * step).toPrecision(12)));
  }
  return ticks;
}

/** 单价表单：各项都是输入框里的原文。 */
export type PriceForm = {
  provider: string;
  model: string;
  unit: Unit;
  input: string;
  output: string;
  currency: Currency;
};

export type PriceChange = {
  provider: string;
  model: string;
  unit: Unit;
  input: number;
  output: number | null;
  currency: Currency;
};

export type PriceProblem = { field: "provider" | "model" | "input" | "output"; reason: "required" | "amount" };

export function emptyPriceForm(): PriceForm {
  return { provider: "", model: "", unit: "tokens", input: "", output: "", currency: "USD" };
}

/** 修改一项单价时表单的初值：后台设定的，没有就是预设的。 */
export function priceFormOf(entry: Pick<PriceEntry, "provider" | "model" | "unit" | "preset" | "override">): PriceForm {
  const price = entry.override ?? entry.preset;
  return {
    provider: entry.provider,
    model: entry.model,
    unit: isUnit(entry.unit) ? entry.unit : "tokens",
    input: price ? String(price.input) : "",
    output: price?.output == null ? "" : String(price.output),
    currency: price && isCurrency(price.currency) ? price.currency : "USD",
  };
}

/** 表单换成要保存的单价，或者第一个不对的地方。输出价留空表示按输入价算。 */
export function priceChangeOf(form: PriceForm): { change: PriceChange } | { problem: PriceProblem } {
  const provider = form.provider.trim();
  const model = form.model.trim();
  if (!provider) return { problem: { field: "provider", reason: "required" } };
  if (!model) return { problem: { field: "model", reason: "required" } };
  if (!form.input.trim()) return { problem: { field: "input", reason: "required" } };
  const input = amountOf(form.input);
  if (input === null) return { problem: { field: "input", reason: "amount" } };
  let output: number | null = null;
  if (form.output.trim()) {
    output = amountOf(form.output);
    if (output === null) return { problem: { field: "output", reason: "amount" } };
  }
  return { change: { provider, model, unit: form.unit, input, output, currency: form.currency } };
}

function amountOf(text: string): number | null {
  const trimmed = text.trim();
  if (!/^\d+(\.\d+)?$/.test(trimmed)) return null;
  const value = Number(trimmed);
  return Number.isFinite(value) ? value : null;
}

function isUnit(value: string): value is Unit {
  return (UNITS as string[]).includes(value);
}

function isCurrency(value: string): value is Currency {
  return (CURRENCIES as string[]).includes(value);
}

export async function getPrices(): Promise<Prices> {
  return json(await fetch("/api/admin/prices", { headers: apiHeaders() }));
}

/** 从现在起按这个单价估算，取代同一提供方、模型和单位的预设。 */
export async function savePrice(change: PriceChange): Promise<Prices> {
  return json(
    await fetch("/api/admin/prices", {
      method: "PUT",
      headers: apiHeaders({ "content-type": "application/json" }),
      body: JSON.stringify(change),
    }),
  );
}

/** 恢复成预设；没有预设的就不再有单价。 */
export async function restorePrice(entry: Pick<PriceEntry, "provider" | "model" | "unit">): Promise<Prices> {
  const query = new URLSearchParams({ provider: entry.provider, model: entry.model, unit: entry.unit });
  return json(await fetch(`/api/admin/prices?${query}`, { method: "DELETE", headers: apiHeaders() }));
}
