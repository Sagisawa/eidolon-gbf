"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  ApiError,
  createConversation,
  listConversations,
  listMessages,
  sendTurn,
  type Message,
  type Segment,
} from "@/lib/api";

const CHARACTER_NAMES: Record<string, string> = { mano: "櫻木真乃" };

type Failure = { message: string; needsKey: boolean };

function toFailure(e: unknown): Failure {
  return {
    message: (e as Error).message,
    needsKey: e instanceof ApiError && e.unauthorized,
  };
}

type Entry =
  | { kind: "user"; key: string; text: string }
  | { kind: "character"; key: string; segments: Segment[]; pending: boolean };

function toEntry(message: Message): Entry {
  return message.role === "user"
    ? { kind: "user", key: `m${message.id}`, text: message.text ?? "" }
    : {
        kind: "character",
        key: `m${message.id}`,
        segments: message.segments,
        pending: false,
      };
}

export default function ConversationPage() {
  const { characterId } = useParams<{ characterId: string }>();
  const name = CHARACTER_NAMES[characterId] ?? characterId;
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Failure | null>(null);
  const logEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [latest] = await listConversations(characterId);
        const conversation = latest ?? (await createConversation(characterId));
        const messages = await listMessages(conversation.id);
        if (cancelled) return;
        setConversationId(conversation.id);
        setEntries(messages.map(toEntry));
      } catch (e) {
        if (!cancelled) setError(toFailure(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [characterId]);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ block: "end" });
  }, [entries]);

  async function startNewConversation() {
    setError(null);
    try {
      const conversation = await createConversation(characterId);
      setConversationId(conversation.id);
      setEntries([]);
    } catch (e) {
      setError(toFailure(e));
    }
  }

  async function submit(event: FormEvent) {
    event.preventDefault();
    const text = input.trim();
    if (!text || !conversationId || busy) return;
    setInput("");
    setBusy(true);
    setError(null);
    const replyKey = `pending-${Date.now()}`;
    const userKey = `${replyKey}-user`;
    setEntries((all) => [
      ...all,
      { kind: "user", key: userKey, text },
      { kind: "character", key: replyKey, segments: [], pending: true },
    ]);
    const updateReply = (update: (entry: Entry & { kind: "character" }) => Entry) =>
      setEntries((all) =>
        all.map((entry) =>
          entry.key === replyKey && entry.kind === "character" ? update(entry) : entry,
        ),
      );

    let failure: Failure | null = null;
    try {
      for await (const event of sendTurn(conversationId, text)) {
        if (event.type === "delta") {
          updateReply((entry) => {
            const segments = [...entry.segments];
            const current = segments[event.segment] ?? { ja: "", zh: "" };
            segments[event.segment] = { ...current, [event.lang]: current[event.lang] + event.text };
            return { ...entry, segments };
          });
        } else if (event.type === "error") {
          failure = { message: event.message, needsKey: false };
        }
      }
    } catch (e) {
      failure = toFailure(e);
    }
    if (failure) {
      // A failed turn is not recorded: take it back off the log and return the text to the input.
      setEntries((all) => all.filter((entry) => entry.key !== replyKey && entry.key !== userKey));
      setInput(text);
      setError(failure);
    } else {
      updateReply((entry) => ({ ...entry, pending: false }));
    }
    setBusy(false);
  }

  return (
    <main className="conversation">
      <header className="conversation-header">
        <h1>{name}</h1>
        <div className="header-actions">
          <button
            type="button"
            className="ghost"
            onClick={startNewConversation}
            disabled={busy || error?.needsKey}
          >
            新对话
          </button>
          <Link href="/settings" className="ghost-link">
            设置
          </Link>
        </div>
      </header>

      <section className="log" aria-live="polite">
        {entries.length === 0 && <p className="empty">和{name}打个招呼吧。</p>}
        {entries.map((entry) =>
          entry.kind === "user" ? (
            <p key={entry.key} className="bubble user">
              {entry.text}
            </p>
          ) : (
            <div key={entry.key} className={`bubble character${entry.pending ? " pending" : ""}`}>
              {entry.segments.map((segment, i) => (
                <div key={i} className="segment">
                  <p className="ja" lang="ja">
                    {segment.ja}
                  </p>
                  {segment.zh && <p className="zh">{segment.zh}</p>}
                </div>
              ))}
              {entry.pending && entry.segments.length === 0 && <p className="typing">……</p>}
            </div>
          ),
        )}
        <div ref={logEnd} />
      </section>

      {error && (
        <p className="error" role="alert">
          {error.message}
          {error.needsKey && (
            <>
              {" "}
              <Link href="/settings">前往设置</Link>
            </>
          )}
        </p>
      )}

      <form className="composer" onSubmit={submit}>
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="用中文或日语说点什么"
          maxLength={2000}
          disabled={!conversationId}
          aria-label="输入消息"
        />
        <button type="submit" disabled={!conversationId || busy || !input.trim()}>
          发送
        </button>
      </form>
    </main>
  );
}
