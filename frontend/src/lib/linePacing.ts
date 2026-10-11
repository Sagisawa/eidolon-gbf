// Which of her lines the call layer's line card shows in a call, and when it moves on
// (spec「通话层的台词卡按她说话的节奏换段」). The card shows one segment at a time and only
// moves forward.
//
// - A reply voiced as it started (not text only) is followed by her voice to the end: the card
//   moves on to the segment her voice starts playing, skipping any it never plays. Until her
//   voice starts on it, the card stays on the line it showed last.
// - Should her voice stop short of the end of a recorded reply, or not start on it at all within
//   `VOICE_WAIT_MS`, the card plays out the rest at her pace (`lineTime`), unless the user
//   interrupted her: then it stays where it is until her next reply is said.
// - A reply started in text only shows each segment as its text arrives.
// - A reply dropped for a follow-on leaves no trace on the card.

import type { Segment } from "@/lib/api";

/** How fast she speaks, in characters of Japanese a second, punctuation included: about what
 * the characters' recorded greetings on the landing page come to. */
const CHARACTERS_PER_SECOND = 5;

/** The least time a line stays on the card when the card keeps her pace, in milliseconds. */
const SHORTEST_LINE_MS = 1500;

/** How long the card waits for her voice to start on a recorded reply before playing it out at
 * her pace, in milliseconds: her text runs ahead of her voice, so a reply is often recorded
 * before she starts saying it. */
const VOICE_WAIT_MS = 3000;

/** A segment the card has shown: which reply of the call and which segment of it, since when. */
type Shown = { reply: number; segment: number; line: Segment; at: number };

/** Her latest reply in the call. */
type Reply = {
  number: number;
  /** Voiced as it started (not text only), and so followed by her voice to the end. */
  voiced: boolean;
  /** Its segments so far; all of them once it is recorded. */
  segments: Segment[];
  /** When it was recorded; null until it is. */
  recordedAt: number | null;
  /** The user spoke or typed over it (GLOSSARY.md「打断」): the card is not to play it out. */
  interrupted: boolean;
};

export type Lines = {
  /** The segments the card has shown in this call, in order; the last is the one it shows. */
  shown: Shown[];
  reply: Reply | null;
  /** Her voice is playing. */
  voicing: boolean;
};

export type LinesEvent =
  /** A reply starts (the turn's `user` event), voiced unless text only. */
  | { type: "reply"; number: number; voiced: boolean }
  /** The latest reply's text arrived: its segments so far. */
  | { type: "text"; segments: Segment[] }
  /** The latest reply is recorded, with these segments. */
  | { type: "recorded"; segments: Segment[] }
  /** Her voice started playing this segment. */
  | { type: "segment-playing"; reply: number; segment: number }
  /** Her voice started or stopped playing. */
  | { type: "voice"; playing: boolean }
  /** The user started speaking, or sent what they typed: her latest reply is interrupted, or
   * dropped for a follow-on, which comes to the same here. Her `done` may come before the
   * user's words are taken up, so it is told apart by this, not by the next reply. */
  | { type: "interrupted" }
  /** The call is over: the card keeps its last moment, and moves on no more. */
  | { type: "call-over" };

/** As a call starts: nothing shown. */
export const NO_LINES: Lines = { shown: [], reply: null, voicing: false };

/** The card moved on by this event, at `now`. */
export function movedLines(lines: Lines, event: LinesEvent, now: number): Lines {
  switch (event.type) {
    case "reply": {
      // A reply not recorded by the time the next one starts was dropped for a follow-on,
      // which leaves no trace (GLOSSARY.md「补充」).
      const dropped = lines.reply && lines.reply.recordedAt === null ? lines.reply.number : null;
      return {
        ...lines,
        shown: lines.shown.filter((s) => s.reply !== dropped),
        reply: { number: event.number, voiced: event.voiced, segments: [], recordedAt: null, interrupted: false },
      };
    }
    case "text":
    case "recorded": {
      const reply = lines.reply;
      if (!reply) return lines;
      const recordedAt = event.type === "recorded" ? now : null;
      const next = { ...reply, segments: event.segments, recordedAt };
      return withText({ ...lines, reply: next }, now);
    }
    case "segment-playing":
      if (event.reply !== lines.reply?.number) return lines;
      return shownUpTo(lines, event.segment, now);
    case "voice":
      return { ...lines, voicing: event.playing };
    case "interrupted":
      return lines.reply ? { ...lines, reply: { ...lines.reply, interrupted: true } } : lines;
    case "call-over":
      return { ...lines, reply: null, voicing: false };
  }
}

/** The card moved on at her pace, if it keeps her pace now and it is time. */
export function pacedLines(lines: Lines, now: number): Lines {
  const next = nextPaced(lines);
  if (next === null || next.at > now) return lines;
  return shownUpTo(lines, next.segment, now);
}

/** When the card is next to move on at her pace; null if it does not keep her pace now. */
export function nextPacedAt(lines: Lines): number | null {
  return nextPaced(lines)?.at ?? null;
}

/** The segment of her latest reply the card is next to move on to at her pace, and when; null
 * if it does not keep her pace now. It does once her voice is not playing a voiced reply that
 * is recorded and not interrupted: from the segment her voice stopped on, once that has had its
 * time, or from the first segment if her voice has not started on the reply a while after it
 * was recorded. */
function nextPaced(lines: Lines): { segment: number; at: number } | null {
  const { reply, voicing } = lines;
  if (!reply?.voiced || reply.recordedAt === null || reply.interrupted || voicing) return null;
  const current = lines.shown.at(-1);
  const next =
    current?.reply === reply.number
      ? { segment: current.segment + 1, at: current.at + lineTime(current.line) }
      : { segment: 0, at: reply.recordedAt + VOICE_WAIT_MS };
  return next.segment < reply.segments.length ? next : null;
}

/** The line the card shows; null until it has shown one. */
export function lineOf(lines: Lines): Segment | null {
  return lines.shown.at(-1)?.line ?? null;
}

/** The line the card showed before that; null until it has shown two. */
export function previousLineOf(lines: Lines): Segment | null {
  return lines.shown.at(-2)?.line ?? null;
}

/** The segment the card shows, of which reply; null until it has shown one. */
export function shownSegmentOf(lines: Lines): { reply: number; segment: number } | null {
  const current = lines.shown.at(-1);
  return current ? { reply: current.reply, segment: current.segment } : null;
}

/** How long she takes to say this line, at her pace, in milliseconds: every character of its
 * Japanese but spaces counts, punctuation too. */
function lineTime(line: Segment): number {
  const characters = [...line.ja.replace(/\s/g, "")].length;
  return Math.max(SHORTEST_LINE_MS, (characters / CHARACTERS_PER_SECOND) * 1000);
}

/** The latest reply's text arrived: what the card shows of it fills in, and a reply without
 * her voice shows its newest segment at once. */
function withText(lines: Lines, now: number): Lines {
  const reply = lines.reply!;
  const shown = lines.shown.map((s) =>
    s.reply === reply.number && reply.segments[s.segment] ? { ...s, line: reply.segments[s.segment] } : s,
  );
  const filled = { ...lines, shown };
  if (reply.voiced) return filled;
  const newest = reply.segments.findLastIndex((segment) => segment.ja);
  return newest < 0 ? filled : shownUpTo(filled, newest, now);
}

/** The card moves on to this segment of the latest reply at `now`, unless it is there or past
 * it already. */
function shownUpTo(lines: Lines, segment: number, now: number): Lines {
  const reply = lines.reply!;
  const current = lines.shown.at(-1);
  if (current?.reply === reply.number && current.segment >= segment) return lines;
  const line = reply.segments[segment] ?? { ja: "", zh: "" };
  return { ...lines, shown: [...lines.shown, { reply: reply.number, segment, line, at: now }] };
}
