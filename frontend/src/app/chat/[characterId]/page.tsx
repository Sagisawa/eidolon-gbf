"use client";

import { useParams } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import {
  createConversation,
  listConversations,
  listMessages,
  sendTurn,
  type Message,
  type Segment,
} from "@/lib/api";

const CHARACTER_NAMES: Record<string, string> = { mano: "櫻木真乃" };

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

export default function ChatPage() {
  const { characterId } = useParams<{ characterId: string }>();
  const name = CHARACTER_NAMES[characterId] ?? characterId;
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
        if (!cancelled) setError((e as Error).message);
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
      setError((e as Error).message);
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
    setEntries((all) => [
      ...all,
      { kind: "user", key: `${replyKey}-user`, text },
      { kind: "character", key: replyKey, segments: [], pending: true },
    ]);
    const updateReply = (update: (entry: Entry & { kind: "character" }) => Entry) =>
      setEntries((all) =>
        all.map((entry) =>
          entry.key === replyKey && entry.kind === "character" ? update(entry) : entry,
        ),
      );

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
          setError(event.message);
        }
      }
    } catch (e) {
      setError((e as Error).message);
    } finally {
      // Settle the reply; drop it if nothing arrived before an error.
      setEntries((all) =>
        all.flatMap((entry) =>
          entry.key !== replyKey || entry.kind !== "character"
            ? [entry]
            : entry.segments.length === 0
              ? []
              : [{ ...entry, pending: false }],
        ),
      );
      setBusy(false);
    }
  }

  return (
    <main className="chat">
      <header className="chat-header">
        <h1>{name}</h1>
        <button type="button" className="ghost" onClick={startNewConversation} disabled={busy}>
          新对话
        </button>
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

      {error && <p className="error" role="alert">{error}</p>}

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
