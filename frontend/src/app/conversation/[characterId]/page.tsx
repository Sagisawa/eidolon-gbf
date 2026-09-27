"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { FormEvent, useEffect, useRef, useState, useSyncExternalStore } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import {
  createConversation,
  listCharacters,
  listConversations,
  listMessages,
  sendTurn,
  type Message,
} from "@/lib/api";
import { startCall } from "@/lib/call";
import { loadCallPreferences, saveCallPreferences } from "@/lib/callPreferences";
import { toFailure, type Failure } from "@/lib/failure";
import { LiveConversation, NOT_OPEN } from "@/lib/liveConversation";

/** The conversation to open, with its recorded messages. */
type Opened = { id: string; messages: Message[] };

const notOpen = () => NOT_OPEN;
const noSubscription = () => () => {};

export default function ConversationPage() {
  const { characterId } = useParams<{ characterId: string }>();
  const [name, setName] = useState("");
  const [opened, setOpened] = useState<Opened | null>(null);
  const [live, setLive] = useState<LiveConversation | null>(null);
  const [pageError, setPageError] = useState<Failure | null>(null);
  const { entries, phase, hearing, busy, draft, muted, failure } = useSyncExternalStore(
    live?.subscribe ?? noSubscription,
    live?.snapshot ?? notOpen,
    notOpen,
  );
  const error = pageError ?? failure;
  const characterAudio = useRef<HTMLAudioElement>(null);
  const logEnd = useRef<HTMLDivElement>(null);

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
        setOpened({ id: conversation.id, messages });
      } catch (e) {
        if (!cancelled) setPageError(toFailure(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [characterId]);

  // Leaving the page, or starting a new conversation, is done with the one open.
  useEffect(() => {
    if (!opened) return;
    const conversation = new LiveConversation(opened.id, opened.messages, {
      startCall,
      sendTurn,
      preferences: { load: loadCallPreferences, save: saveCallPreferences },
      onCharacterAudio: (track) => {
        if (characterAudio.current) characterAudio.current.srcObject = new MediaStream([track]);
      },
    });
    setLive(conversation);
    return () => conversation.dispose();
  }, [opened]);

  useEffect(() => {
    logEnd.current?.scrollIntoView({ block: "end" });
  }, [entries, hearing]);

  async function startNewConversation() {
    setPageError(null);
    try {
      const conversation = await createConversation(characterId);
      setOpened({ id: conversation.id, messages: [] });
    } catch (e) {
      setPageError(toFailure(e));
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    setPageError(null);
    void live?.submit();
  }

  function toggleCall() {
    setPageError(null);
    void live?.toggleCall();
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
            disabled={busy || phase !== "idle" || error?.signedOut}
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
          className={phase === "idle" ? "" : "hang-up"}
          onClick={toggleCall}
          disabled={!live || busy || phase === "connecting"}
        >
          {phase === "idle" ? "语音通话" : phase === "connecting" ? "接通中……" : "挂断"}
        </button>
        <label className="mute-switch">
          <input
            type="checkbox"
            checked={muted}
            onChange={() => live?.toggleMute()}
            disabled={!live}
          />
          静音（只看文字）
        </label>
        {phase === "active" && <span className="call-status">通话中，直接说话即可</span>}
      </div>
      <audio ref={characterAudio} autoPlay muted={muted} />

      <form className="composer" onSubmit={submit}>
        <input
          value={draft}
          onChange={(e) => live?.setDraft(e.target.value)}
          placeholder="用中文或日语说点什么"
          maxLength={2000}
          disabled={!live}
          aria-label="输入消息"
        />
        <button type="submit" disabled={!live || busy || phase === "connecting" || !draft.trim()}>
          发送
        </button>
      </form>
    </main>
  );
}
