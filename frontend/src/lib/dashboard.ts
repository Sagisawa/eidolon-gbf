// The admin console's dashboard (GLOSSARY「看板」): what the backend sums up from the
// activity records, and how the page words and lays out its numbers. Nothing is summed up
// here; the backend does all of that.

import { apiHeaders, json } from "@/lib/api";

export const DASHBOARD_RANGES = ["24h", "7d", "30d", "90d"] as const;

export type DashboardRange = (typeof DASHBOARD_RANGES)[number];

export function isDashboardRange(value: string): value is DashboardRange {
  return (DASHBOARD_RANGES as readonly string[]).includes(value);
}

export type ServiceName =
  | "chat_llm"
  | "memory_llm"
  | "tts"
  | "stt"
  | "judge"
  | "embedding"
  | "rerank";

export type ErrorKind =
  | "timeout"
  | "connection"
  | "rate_limited"
  | "unauthorized"
  | "refused"
  | "server_error"
  | "unreadable"
  | "other";

/** What a service's calls were billed for in one unit; null where no call said. */
export type Usage = { unit: string; input: number | null; output: number | null };

/** One service's calls, on the deployer's keys or on users' own (`own_key`). */
export type ServiceHealth = {
  service: ServiceName;
  own_key: boolean;
  calls: number;
  errors: number;
  error_rate: number;
  errors_by_kind: Partial<Record<ErrorKind, number>>;
  latency_ms: { p50: number | null; p95: number | null };
  usage: Usage[];
  /** Calls the service did not say what it billed for. */
  usage_unknown: number;
};

export type TurnResult = "success" | "failed" | "rejected" | "left";

export const TURN_RESULTS: TurnResult[] = ["success", "failed", "rejected", "left"];

export type TrendPoint = { start: string; turns: number; active_users: number };

export type Bucket = "hour" | "6h" | "day";

export type Dashboard = {
  range: DashboardRange;
  from: string;
  to: string;
  /** How long each stretch of `trend` is. */
  bucket: Bucket;
  health: ServiceHealth[];
  turns: {
    total: number;
    by_result: Record<TurnResult, number>;
    own_keys: number;
    active_users: number;
    time_to_speak_ms: { count: number; p50: number | null; p90: number | null };
  };
  trend: TrendPoint[];
  /** `name` is null for a character since removed from the configuration. */
  characters: { character_id: string; name: string | null; turns: number }[];
};

export async function getDashboard(range: DashboardRange): Promise<Dashboard> {
  return json(await fetch(`/api/admin/dashboard?range=${range}`, { headers: apiHeaders() }));
}

const NONE = "—";

/** A count, comma'd; from ten thousand on, in 万 to one decimal. */
export function formatCount(n: number): string {
  if (Math.abs(n) >= 10_000) return `${trim(n / 10_000)}万`;
  return Math.round(n).toLocaleString("en-US");
}

/** `part` of `whole` as a percentage, to one decimal at most; a sliver is never shown as 0. */
export function formatShare(part: number, whole: number): string {
  if (whole <= 0) return NONE;
  return formatPercent(part / whole);
}

export function formatPercent(rate: number): string {
  if (rate <= 0) return "0%";
  if (rate < 0.001) return "<0.1%";
  return `${trim(rate * 100)}%`;
}

/** A duration in milliseconds: under a second in ms, else in seconds to one decimal. */
export function formatMs(ms: number | null): string {
  if (ms === null) return NONE;
  if (ms < 1000) return `${Math.round(ms)} ms`;
  return `${trim(ms / 1000)} s`;
}

function trim(value: number): string {
  return value.toFixed(1).replace(/\.0$/, "");
}

/** How a service is doing by its error rate; `idle` with no calls to tell by. */
export type HealthStatus = "ok" | "degraded" | "failing" | "idle";

export function healthStatus(row: Pick<ServiceHealth, "calls" | "error_rate">): HealthStatus {
  if (row.calls === 0) return "idle";
  if (row.error_rate < 0.02) return "ok";
  if (row.error_rate < 0.1) return "degraded";
  return "failing";
}

/** What a service's calls were billed for, e.g. "输入 1.2万 · 输出 3,400 tokens"; how
 * many calls did not say, if any. */
export function formatUsage(usage: Usage[], unknown: number): string {
  const parts = usage.map(({ unit, input, output }) => {
    if (output === null) return `${input === null ? NONE : formatCount(input)} ${unit}`;
    return `输入 ${input === null ? NONE : formatCount(input)} · 输出 ${formatCount(output)} ${unit}`;
  });
  if (unknown > 0) parts.push(`${formatCount(unknown)} 次未知`);
  return parts.join("；") || NONE;
}

/** Where a stretch of the trend begins, as its axis labels it, in the browser's time. */
export function stretchLabel(start: string, bucket: Bucket): string {
  const at = new Date(start);
  const hour = `${String(at.getHours()).padStart(2, "0")}:00`;
  const day = `${at.getMonth() + 1}月${at.getDate()}日`;
  if (bucket === "day") return day;
  if (bucket === "6h") return at.getHours() === 0 ? day : hour;
  return hour;
}

/** The whole stretch, for its tooltip: "10月7日 14:00–15:00", or the day. */
export function stretchSpan(start: string, bucket: Bucket): string {
  const at = new Date(start);
  const day = `${at.getMonth() + 1}月${at.getDate()}日`;
  if (bucket === "day") return day;
  const hours = bucket === "6h" ? 6 : 1;
  const end = (at.getHours() + hours) % 24;
  const pad = (h: number) => `${String(h).padStart(2, "0")}:00`;
  return `${day} ${pad(at.getHours())}–${pad(end)}`;
}

/** Clean ticks for a count axis from 0 to at least `max`: 1, 2 or 5 times a power of ten
 * apart, at most `count` steps. */
export function countTicks(max: number, count = 4): number[] {
  if (max <= 0) return [0, 1];
  const rough = max / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  const step = [1, 2, 5, 10].map((m) => m * power).find((s) => s >= rough) ?? 10 * power;
  const whole = Math.max(1, Math.round(step)); // counts tick on whole numbers
  const ticks = [];
  for (let tick = 0; tick < max + whole; tick += whole) ticks.push(tick);
  return ticks;
}

/** Which of `n` stretches the axis labels, so that at most `most` labels fit: every
 * stretch, or every second, third… counting back from the latest. */
export function labelledStretches(n: number, most: number): Set<number> {
  const every = Math.max(1, Math.ceil(n / most));
  const labelled = new Set<number>();
  for (let i = n - 1; i >= 0; i -= every) labelled.add(i);
  return labelled;
}
