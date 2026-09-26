import { describe, expect, it } from "vitest";
import type { Message, TurnEvent } from "@/lib/api";
import {
  conversationLog,
  emptyLog,
  type ConversationLog,
  type LogAction,
} from "@/lib/conversationLog";

function message(id: number, role: Message["role"], text: string): Message {
  return role === "user"
    ? { id, role, text, ja: null, zh: null, segments: [], created_at: "2026-09-26T00:00:00Z" }
    : {
        id,
        role,
        text: null,
        ja: text,
        zh: `（${text}）`,
        segments: [{ ja: text, zh: `（${text}）` }],
        created_at: "2026-09-26T00:00:00Z",
      };
}

function delta(segment: number, lang: "ja" | "zh", text: string): TurnEvent {
  return { type: "delta", segment, lang, text };
}

function play(actions: LogAction[], from: ConversationLog = emptyLog): ConversationLog {
  return actions.reduce(conversationLog, from);
}

const history = play([
  { type: "loaded", messages: [message(1, "user", "早上好"), message(2, "character", "おはよう")] },
]);

describe("conversationLog", () => {
  it("shows the recorded messages it is loaded with, one entry each", () => {
    expect(history.turn).toBeNull();
    expect(history.entries).toEqual([
      { kind: "user", key: "m1", text: "早上好" },
      {
        kind: "character",
        key: "m2",
        segments: [{ ja: "おはよう", zh: "（おはよう）" }],
        pending: false,
      },
    ]);
  });

  it("replaces everything, including a turn in progress, when loaded again", () => {
    const log = play(
      [
        { type: "submitted", text: "你好" },
        { type: "loaded", messages: [] },
      ],
      history,
    );
    expect(log).toEqual(emptyLog);
  });

  it("shows a typed turn at once and confirms it on `user` without a second copy", () => {
    const submitted = play([{ type: "submitted", text: "你好" }], history);
    expect(submitted.turn?.confirmed).toBe(false);

    const log = conversationLog(submitted, { type: "user", text: "你好" });
    expect(log.turn?.confirmed).toBe(true);
    expect(log.entries.slice(2)).toEqual([
      { kind: "user", key: log.turn?.userKey, text: "你好" },
      { kind: "character", key: log.turn?.replyKey, segments: [], pending: true },
    ]);
  });

  it("opens a turn on `user` when nothing was typed, as in a call", () => {
    const log = play([{ type: "user", text: "在吗" }], history);
    expect(log.turn?.confirmed).toBe(true);
    expect(log.entries).toHaveLength(4);
    expect(log.entries[2]).toMatchObject({ kind: "user", text: "在吗" });
    expect(log.entries[3]).toMatchObject({ kind: "character", segments: [], pending: true });
  });

  it("merges deltas by segment and language, each language adding up on its own", () => {
    const log = play(
      [
        { type: "user", text: "在吗" },
        delta(0, "ja", "いる"),
        delta(0, "zh", "在"),
        delta(0, "ja", "よ"),
        delta(1, "ja", "どうした"),
        delta(0, "zh", "哦"),
        delta(1, "zh", "怎么了"),
      ],
      history,
    );
    expect(log.entries[3]).toMatchObject({
      segments: [
        { ja: "いるよ", zh: "在哦" },
        { ja: "どうした", zh: "怎么了" },
      ],
      pending: true,
    });
  });

  it("swaps the reply for the recorded one on `done` and ends the turn", () => {
    const recorded = message(4, "character", "いるよ");
    const log = play(
      [
        { type: "submitted", text: "在吗" },
        { type: "user", text: "在吗" },
        delta(0, "ja", "いる"),
        { type: "done", message: recorded },
      ],
      history,
    );
    expect(log.turn).toBeNull();
    expect(log.entries).toHaveLength(4);
    expect(log.entries[2]).toMatchObject({ kind: "user", text: "在吗" });
    expect(log.entries[3]).toEqual({
      kind: "character",
      key: "m4",
      segments: recorded.segments,
      pending: false,
    });
  });

  it.each<LogAction>([
    { type: "error", message: "角色暂时无法回复，请稍后再试。" },
    { type: "interrupted" },
  ])("takes the turn in progress back off the log on `$type`", (end) => {
    for (const opening of [
      [{ type: "submitted", text: "你好" }],
      [{ type: "submitted", text: "你好" }, { type: "user", text: "你好" }, delta(0, "ja", "こん")],
      [{ type: "user", text: "你好" }, delta(0, "ja", "こん")],
    ] as LogAction[][]) {
      expect(play([...opening, end], history)).toEqual(history);
    }
  });

  it.each<LogAction>([
    delta(0, "ja", "いる"),
    { type: "done", message: message(9, "character", "いるよ") },
    { type: "error", message: "角色暂时无法回复，请稍后再试。" },
    { type: "interrupted" },
  ])("leaves the log alone on `$type` with no turn in progress", (action) => {
    expect(conversationLog(history, action)).toBe(history);
  });

  it("keeps two turns in a row apart", () => {
    const log = play(
      [
        { type: "user", text: "一" },
        delta(0, "ja", "いち"),
        { type: "done", message: message(4, "character", "いち") },
        { type: "user", text: "二" },
        delta(0, "ja", "に"),
        { type: "done", message: message(6, "character", "に") },
      ],
      history,
    );
    expect(log.turn).toBeNull();
    expect(log.entries.map((e) => (e.kind === "user" ? e.text : e.segments[0].ja))).toEqual([
      "早上好",
      "おはよう",
      "一",
      "いち",
      "二",
      "に",
    ]);
    expect(new Set(log.entries.map((e) => e.key)).size).toBe(6);
  });

  it("drops a reply cut off halfway when the call is hung up or drops", () => {
    const log = play(
      [
        { type: "user", text: "一" },
        { type: "done", message: message(4, "character", "いち") },
        { type: "user", text: "二" },
        delta(0, "ja", "に"),
        { type: "interrupted" },
      ],
      history,
    );
    expect(log.turn).toBeNull();
    expect(log.entries).toHaveLength(4);
    expect(log.entries.every((e) => e.kind === "user" || !e.pending)).toBe(true);
  });

  it("gives a new turn keys no entry shown with it has, after an earlier turn was dropped", () => {
    const log = play(
      [
        { type: "user", text: "一" },
        { type: "done", message: message(4, "character", "いち") },
        { type: "user", text: "二" },
        { type: "interrupted" },
        { type: "user", text: "三" },
      ],
      history,
    );
    expect(new Set(log.entries.map((e) => e.key)).size).toBe(log.entries.length);
  });

  it("drops an unfinished turn when a new utterance is taken up", () => {
    const log = play(
      [{ type: "user", text: "一" }, delta(0, "ja", "い"), { type: "user", text: "二" }],
      history,
    );
    expect(log.entries).toHaveLength(4);
    expect(log.entries[2]).toMatchObject({ kind: "user", text: "二" });
    expect(log.entries[3]).toMatchObject({ segments: [], pending: true });
  });
});
