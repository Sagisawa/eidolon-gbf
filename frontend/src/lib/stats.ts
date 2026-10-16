// Stats (GLOSSARY.md「统计」): the user's own dealings with the characters, as `/api/stats`
// sums them up, and what the page makes of them: the heatmap's weeks and shades, the part
// of the day the portrait speaks of, and which blocks are shown. The backend gives only
// numbers; how many of what are shown, and how, is decided here.

import { copy } from "@/i18n";

/** What `/api/stats` answers. Dates are the producer's (`YYYY-MM-DD`, their profile's time zone).
 * `days_known`: the days since the user signed up, that day the first.
 * `visits`: the days in a row they came (took a turn or gave a gift), now and at the longest.
 * `all_hours`: how many turns and gifts at each hour of the day, 0–23, all told.
 * `heatmap`: how many on each day from `from`, a Monday 52 weeks before this week's, to today. */
export type Stats = {
  days_known: number;
  visits: { current: number; longest: number };
  all_hours: number[];
  heatmap: { from: string; counts: number[] };
};

/** The four parts of the day the portrait speaks of, each six hours from midnight. */
export const DAY_PARTS = ["night", "morning", "afternoon", "evening"] as const;

export type DayPart = (typeof DAY_PARTS)[number];

/** The parts of the day the user came at most, in the order of the day (more than one when
 * tied); none if they never came. */
export function busiestParts(hours: number[]): DayPart[] {
  const counts = DAY_PARTS.map((_, i) => hours.slice(i * 6, i * 6 + 6).reduce((sum, n) => sum + n, 0));
  const most = Math.max(...counts);
  return most === 0 ? [] : DAY_PARTS.filter((_, i) => counts[i] === most);
}

/** One line on when the user comes, by the part of the day they came at most: both of two
 * tied, and that they come at any time when three or four are; null if they never came. */
export function portrait(hours: number[]): string | null {
  const t = copy.settings.stats.portrait;
  const parts = busiestParts(hours).map((part) => t.parts[part]);
  if (parts.length === 0) return null;
  if (parts.length > 2) return t.anyTime;
  return t.comesAt(parts.join(t.and));
}

export type HeatLevel = 0 | 1 | 2 | 3 | 4;

/** How dark a day's square is: 0 when they did not come, else 1–4 by its share of the
 * busiest day's count. */
export function heatLevel(count: number, most: number): HeatLevel {
  if (count <= 0 || most <= 0) return 0;
  return Math.min(4, Math.max(1, Math.ceil((count / most) * 4))) as HeatLevel;
}

/** A day of the heatmap: its date (`YYYY-MM-DD`), its month and day of the month, how many
 * turns and gifts, and its shade. */
export type HeatCell = { date: string; month: number; day: number; count: number; level: HeatLevel };

/** The heatmap's columns, a week each from Monday at the top; the last only up to today. */
export function heatmapWeeks(heatmap: Stats["heatmap"]): HeatCell[][] {
  const most = Math.max(0, ...heatmap.counts);
  const start = Date.parse(`${heatmap.from}T00:00:00Z`);
  const weeks: HeatCell[][] = [];
  heatmap.counts.forEach((count, i) => {
    if (i % 7 === 0) weeks.push([]);
    const date = new Date(start + i * 86_400_000).toISOString().slice(0, 10);
    const [month, day] = [Number(date.slice(5, 7)), Number(date.slice(8, 10))];
    weeks[weeks.length - 1].push({ date, month, day, count, level: heatLevel(count, most) });
  });
  return weeks;
}

/** The months to label above the heatmap, by the column the first of each falls in; one
 * closer than `apart` columns to the label before it is left out. */
export function heatmapMonths(weeks: HeatCell[][], apart: number): Map<number, string> {
  const months = new Map<number, string>();
  let last = -Infinity;
  weeks.forEach((week, column) => {
    const first = week.find((cell) => cell.day === 1);
    if (!first || column - last < apart) return;
    months.set(column, copy.settings.stats.month(first.month));
    last = column;
  });
  return months;
}

/** Which blocks of the page are shown: none, but a line and a way to the conversations, when
 * the user never took a turn or gave a gift (`isEmpty`); otherwise each that has something. */
export function statsSections(stats: Stats): { isEmpty: boolean; visits: boolean; portrait: boolean; heatmap: boolean } {
  const hasCome = stats.all_hours.some((n) => n > 0);
  return {
    isEmpty: !hasCome,
    visits: hasCome && stats.visits.longest > 0,
    portrait: hasCome,
    heatmap: stats.heatmap.counts.some((n) => n > 0),
  };
}
