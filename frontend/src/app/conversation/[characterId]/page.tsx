"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useRef, useState } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import {
  createConversation,
  listCharacters,
  listConversations,
  listMessages,
  sendTurn,
  type CallEvent,
  type Message,
  type Segment,
  type TurnEvent,
} from "@/lib/api";
import { startCall, type Call } from "@/lib/call";
import { loadCallPreferences, saveCallPreferences } from "@/lib/callPreferences";
import { toFailure, type Failure } from "@/lib/failure";

type Entry =
  | { kind: "user"; key: string; text: string }
  | { kind: "character"; key: string; segments: Segment[]; pending: boolean };

type CallState = "idle" | "connecting" | "active";

/** One exchange shown in the log before it is recorded: the user's words and the reply. */
type PendingTurn = { userKey: string; replyKey: string };

function pendingTurn(text: string): { turn: PendingTurn; entries: Entry[] } {
  const replyKey = `pending-${Date.now()}-${Math.random()}`;
  const turn = { userKey: `${replyKey}-user`, replyKey };
  return {
    turn,
    entries: [
      { kind: "user", key: turn.userKey, text },
      { kind: "character", key: turn.replyKey, segments: [], pending: true },
    ],
  };
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
  const [name, setName] = useState("");
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [entries, setEntries] = useState<Entry[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<Failure | null>(null);
  const [callState, setCallState] = useState<CallState>("idle");
  const [muted, setMuted] = useState(false);
  const [hearing, setHearing] = useState("");
  const call = useRef<Call | null>(null);
  const callTurn = useRef<PendingTurn | null>(null);
  const voice = useRef<HTMLAudioElement>(null);
  const logEnd = useRef<HTMLDivElement>(null);

  useEffect(() => {
    setMuted(loadCallPreferences().muted);
    return () => {
      call.current?.hangUp().catch(() => {});
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const characters = await listCharacters();
        const character = characters.find((c) => c.id === characterId);
        if (!character) throw new Error("角色不存在");
        if (!cancelled) setName(character.name);
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
  }, [entries, hearing]);

  function updateEntry(key: string, update: (entry: Entry) => Entry) {
    setEntries((all) => all.map((entry) => (entry.key === key ? update(entry) : entry)));
  }

  function dropTurn(turn: PendingTurn) {
    setEntries((all) => all.filter((e) => e.key !== turn.userKey && e.key !== turn.replyKey));
  }

  function onCallEvent(event: CallEvent) {
    if (event.type === "user") {
      const { turn, entries: added } = pendingTurn(event.text);
      callTurn.current = turn;
      setHearing("");
      setEntries((all) => [...all, ...added]);
      return;
    }
    const turn = callTurn.current;
    if (!turn) return;
    if (event.type === "delta") {
      updateEntry(turn.replyKey, (entry) => withDelta(entry, event));
    } else if (event.type === "done") {
      updateEntry(turn.replyKey, (entry) => ({ ...entry, pending: false }));
      callTurn.current = null;
    } else {
      dropTurn(turn);
      callTurn.current = null;
      setError({ message: event.message, needsKey: false });
    }
  }

  async function toggleCall() {
    if (call.current) {
      const ending = call.current;
      call.current = null;
      setCallState("idle");
      setHearing("");
      await ending.hangUp().catch(() => {});
      return;
    }
    if (!conversationId) return;
    setError(null);
    setCallState("connecting");
    try {
      call.current = await startCall(conversationId, loadCallPreferences(), {
        onEvent: onCallEvent,
        onHearing: setHearing,
        onVoice: (track) => {
          if (voice.current) voice.current.srcObject = new MediaStream([track]);
        },
        onDropped: () => {
          call.current = null;
          setCallState("idle");
          setHearing("");
          setError({ message: "通话已断开", needsKey: false });
        },
      });
      setCallState("active");
    } catch (e) {
      setCallState("idle");
      setError(toFailure(e));
    }
  }

  function toggleMute() {
    const next = !muted;
    setMuted(next);
    saveCallPreferences({ muted: next });
    call.current?.setMuted(next);
  }

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
    setError(null);
    if (call.current) {
      // The call takes it up like speech; its reply arrives as call events.
      call.current.sendText(text);
      return;
    }
    setBusy(true);
    const { turn, entries: added } = pendingTurn(text);
    setEntries((all) => [...all, ...added]);

    let failure: Failure | null = null;
    try {
      for await (const event of sendTurn(conversationId, text)) {
        if (event.type === "delta") {
          updateEntry(turn.replyKey, (entry) => withDelta(entry, event));
        } else if (event.type === "error") {
          failure = { message: event.message, needsKey: false };
        }
      }
    } catch (e) {
      failure = toFailure(e);
    }
    if (failure) {
      // A failed turn is not recorded: take it back off the log and return the text to the input.
      dropTurn(turn);
      setInput(text);
      setError(failure);
    } else {
      updateEntry(turn.replyKey, (entry) => ({ ...entry, pending: false }));
    }
    setBusy(false);
  }

  return (
    <main className="conversation">
      <header className="page-header">
        <h1>{name}</h1>
        <div className="header-actions">
          <Link href="/" className="ghost-link">
            角色
          </Link>
          <button
            type="button"
            className="ghost"
            onClick={startNewConversation}
            disabled={busy || callState !== "idle" || error?.needsKey}
          >
            新对话
          </button>
          <Link href="/settings" className="ghost-link">
            设置
          </Link>
        </div>
      </header>

      <section className="log" aria-live="polite">
        {entries.length === 0 && name && <p className="empty">和{name}打个招呼吧。</p>}
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
        {hearing && (
          <p className="bubble user hearing" aria-label="正在听">
            {hearing}
          </p>
        )}
        <div ref={logEnd} />
      </section>

      {error && <FailureNotice failure={error} />}

      <div className="call-bar">
        <button
          type="button"
          className={callState === "idle" ? "" : "hang-up"}
          onClick={toggleCall}
          disabled={!conversationId || busy || callState === "connecting"}
        >
          {callState === "idle" ? "语音通话" : callState === "connecting" ? "接通中……" : "挂断"}
        </button>
        <label className="mute-switch">
          <input type="checkbox" checked={muted} onChange={toggleMute} />
          静音（只看文字）
        </label>
        {callState === "active" && <span className="call-status">通话中，直接说话即可</span>}
      </div>
      <audio ref={voice} autoPlay muted={muted} />

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
