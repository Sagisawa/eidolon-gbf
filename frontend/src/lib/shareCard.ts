// The share card (GLOSSARY.md「分享图」): what goes on the picture the user downloads from
// their stats, for the range they chose. Its star is the one talked with most in the range;
// it carries the form of address they set (「制作人」 if none), the portrait, the totals, the
// three talked with most and the range, and never affinity or anything of how they sign in.

import { copy } from "@/i18n";
import { callTime, mostTalked, portrait, statsSections, type Ranked, type Stats } from "@/lib/stats";

/** How many of those talked with most the card lists. */
export const SHARE_TOP = 3;

/** A total as the card writes it: a label over a number, or two for the hours and minutes, each with its unit. */
export type ShareTotal = { label: string; parts: { value: number; unit?: string }[] };

export type ShareCard = {
  /** The star: the character talked with most in the range (the first in the idols' order of those tied). */
  hero: string;
  /** The form of address the user set, or 「制作人」. */
  address: string;
  /** The range's label: 「近 30 天」「近一年」「全部」. */
  span: string;
  portrait: string | null;
  /** Turns, calls, how long they lasted, and gifts given unless affinity and gifts are off; 0s written as 0. */
  totals: ShareTotal[];
  /** The three talked with most in the range, fewer if fewer took a turn. */
  top: Ranked[];
};

/** Whether there is a card to share: a turn at least in the range, so that it has a star. */
export function canShare(stats: Stats): boolean {
  return mostTalked(stats.range.characters).length > 0;
}

/** The card for the range the stats are over, with the user's form of address; null with no turn in the range. */
export function shareCard(stats: Stats, formOfAddress: string | null): ShareCard | null {
  const t = copy.settings.stats;
  const ranked = mostTalked(stats.range.characters);
  if (ranked.length === 0) return null;
  const { calls, gifts } = stats.range;
  const { hours, minutes } = callTime(calls.seconds);
  const totals: ShareTotal[] = [
    { label: t.turns, parts: [{ value: stats.range.turns }] },
    { label: t.calls, parts: [{ value: calls.count, unit: t.timesUnit }] },
    {
      label: t.callTime,
      parts: [...(hours > 0 ? [{ value: hours, unit: t.hoursUnit }] : []), { value: minutes, unit: t.minutesUnit }],
    },
  ];
  if (statsSections(stats).giftsGiven && gifts) totals.push({ label: t.giftsGiven, parts: [{ value: gifts.given }] });
  return {
    hero: ranked[0].character_id,
    address: formOfAddress?.trim() || t.share.producer,
    span: t.ranges[stats.range.span],
    portrait: portrait(stats.all_hours),
    totals,
    top: ranked.slice(0, SHARE_TOP),
  };
}

/** The downloaded file's name, with the day it was made on, here: `eidolon-stats-2026-10-16.png`. */
export function shareFileName(now: Date): string {
  const two = (n: number) => String(n).padStart(2, "0");
  return `eidolon-stats-${now.getFullYear()}-${two(now.getMonth() + 1)}-${two(now.getDate())}.png`;
}

/** The site as the card shows it, without the scheme, and the landing page the QR code points to; from the page's origin, so that no domain is written in. */
export function siteAddress(origin: string): { shown: string; landing: string } {
  return { shown: origin.replace(/^https?:\/\//, ""), landing: `${origin}/` };
}
