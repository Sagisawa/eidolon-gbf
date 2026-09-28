// The conversation page's log: what it shows of the conversation, kept up to date from
// the same turn events whether the turn is typed or spoken in a call.

import type { Message, Segment, TurnEvent } from "@/lib/api";

/** One message shown. `at` (ISO) is when it was recorded; for the turn under way, when the
 * user sent or said the words, which the reply shares until it is recorded. */
export type Entry =
  | { kind: "user"; key: string; text: string; at: string }
  | { kind: "character"; key: string; segments: Segment[]; pending: boolean; at: string };

/** The exchange under way: the user's words and the reply, both the last entries shown.
 * A turn the user typed is unconfirmed until the backend's `user` event takes it up. */
export type Turn = { confirmed: boolean; userKey: string; replyKey: string };

export type ConversationLog = { entries: Entry[]; turn: Turn | null };

export type LogAction =
  /** The conversation was opened or started: show its recorded messages. */
  | { type: "loaded"; messages: Message[] }
  /** The user typed something outside a call, at `at`; show it before the backend takes it up. */
  | { type: "submitted"; text: string; at: string }
  /** The backend took up the user's words, heard at `at`; words typed keep the time they were sent. */
  | (Extract<TurnEvent, { type: "user" }> & { at: string })
  | Exclude<TurnEvent, { type: "user" }>
  /** The turn ended without `done` or `error`: the user hung up, the call dropped, or
   * the text turn's event stream closed early. */
  | { type: "interrupted" };

export const emptyLog: ConversationLog = { entries: [], turn: null };

export function conversationLog(log: ConversationLog, action: LogAction): ConversationLog {
  switch (action.type) {
    case "loaded":
      return { entries: action.messages.map(toEntry), turn: null };
    case "submitted":
      return opened(withoutTurn(log), action.text, action.at, false);
    case "user":
      if (log.turn && !log.turn.confirmed) {
        return { ...log, turn: { ...log.turn, confirmed: true } };
      }
      return opened(withoutTurn(log), action.text, action.at, true);
    case "delta": {
      const turn = log.turn;
      if (!turn) return log;
      return { ...log, entries: replaced(log.entries, turn.replyKey, (e) => withDelta(e, action)) };
    }
    case "done": {
      const turn = log.turn;
      if (!turn) return log;
      const reply = toEntry(action.message);
      return { entries: replaced(log.entries, turn.replyKey, () => reply), turn: null };
    }
    case "error":
    case "interrupted":
      return withoutTurn(log);
  }
}

/** Opens a turn with the user's words and an empty reply to fill. The turn in progress is
 * always the last two entries, so an entry's position is never shared by two entries
 * shown together and serves as its key until the entry is replaced by the recorded one. */
function opened(log: ConversationLog, text: string, at: string, confirmed: boolean): ConversationLog {
  const position = log.entries.length;
  const turn = { confirmed, userKey: `new-${position}`, replyKey: `new-${position + 1}` };
  return {
    entries: [
      ...log.entries,
      { kind: "user", key: turn.userKey, text, at },
      { kind: "character", key: turn.replyKey, segments: [], pending: true, at },
    ],
    turn,
  };
}

/** A turn that ends without `done` left no record: take it back off the log. */
function withoutTurn(log: ConversationLog): ConversationLog {
  const turn = log.turn;
  if (!turn) return log;
  const entries = log.entries.filter((e) => e.key !== turn.userKey && e.key !== turn.replyKey);
  return { entries, turn: null };
}

function replaced(entries: Entry[], key: string, update: (entry: Entry) => Entry): Entry[] {
  return entries.map((entry) => (entry.key === key ? update(entry) : entry));
}

function withDelta(entry: Entry, event: TurnEvent & { type: "delta" }): Entry {
  if (entry.kind !== "character") return entry;
  const segments = [...entry.segments];
  const current = segments[event.segment] ?? { ja: "", zh: "" };
  segments[event.segment] = { ...current, [event.lang]: current[event.lang] + event.text };
  return { ...entry, segments };
}

function toEntry(message: Message): Entry {
  return message.role === "user"
    ? { kind: "user", key: `m${message.id}`, text: message.text ?? "", at: message.created_at }
    : {
        kind: "character",
        key: `m${message.id}`,
        segments: message.segments,
        pending: false,
        at: message.created_at,
      };
}
