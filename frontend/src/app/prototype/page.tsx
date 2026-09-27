"use client";

import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { BottomSheet } from "@astryxdesign/core/BottomSheet";
import { Heading } from "@astryxdesign/core/Heading";
import { useMediaQuery } from "@astryxdesign/core/hooks";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { StackItem } from "@astryxdesign/core/Stack";
import { VStack } from "@astryxdesign/core/VStack";
import { useEffect, useRef, useState } from "react";


import { CALL_LIMIT_SECONDS, type CallPhase, type EndReason } from "./call";
import { CallLayer } from "./CallLayer";
import { Conversation } from "./Conversation";
import { ConversationList, selectedRow } from "./ConversationList";
import {
  cannedReplies,
  characters,
  conversations as seed,
  hearingSample,
  liveLines,
  type Message,
  microphones,
} from "./data";
import { PrototypeConsole, type Scenario } from "./PrototypeConsole";

type Leave = { to: string } | null;

export default function PrototypePage() {
  const narrow = useMediaQuery("(max-width: 767px)");
  const reducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)");

  const [selectedId, setSelectedId] = useState<string | null>("mano");
  const [messages, setMessages] = useState<Record<string, Message[]>>(seed);
  const [empty, setEmpty] = useState(false);

  const [callId, setCallId] = useState<string | null>(null);
  const [phase, setPhase] = useState<CallPhase>({ kind: "idle" });
  const [collapsed, setCollapsed] = useState(false);
  const [micMuted, setMicMuted] = useState(false);
  const [textOnly, setTextOnly] = useState(false);
  const [micId, setMicId] = useState(microphones[0].id);
  const [micPickerOpen, setMicPickerOpen] = useState(false);
  const [hearing, setHearing] = useState(false);
  const [nearLimit, setNearLimit] = useState(false);
  const [lineShown, setLineShown] = useState(false);
  const [reason, setReason] = useState<EndReason>("not-connected");
  const [leave, setLeave] = useState<Leave>(null);
  const [now, setNow] = useState(() => Date.now());
  const replyIndex = useRef(0);

  // 通话中每秒走一次表。
  useEffect(() => {
    if (phase.kind !== "connected") return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [phase.kind]);

  // 拨打约 2 秒后接通；接通 1.5 秒后她开口。
  useEffect(() => {
    if (phase.kind === "dialing") {
      const t = setTimeout(() => connect(), 2200);
      return () => clearTimeout(t);
    }
    if (phase.kind === "connected" && !lineShown) {
      const t = setTimeout(() => setLineShown(true), 1500);
      return () => clearTimeout(t);
    }
  }, [phase, lineShown]); // eslint-disable-line react-hooks/exhaustive-deps

  const elapsed = phase.kind === "connected" ? (now - phase.since) / 1000 : 0;
  const inCall = phase.kind === "dialing" || phase.kind === "connected";

  function connect() {
    const offset = nearLimit ? (CALL_LIMIT_SECONDS - 48) * 1000 : 0;
    setNow(Date.now());
    setPhase({ kind: "connected", since: Date.now() - offset });
  }

  function startCall(id: string) {
    setCallId(id);
    setCollapsed(false);
    setLineShown(false);
    setMicMuted(false);
    setPhase({ kind: "dialing" });
  }

  function hangUp() {
    setPhase({ kind: "idle" });
    setCallId(null);
    setCollapsed(false);
  }

  function send(id: string, text: string) {
    const time = new Date().toTimeString().slice(0, 5);
    setEmpty(false);
    setMessages((all) => ({ ...all, [id]: [...(all[id] ?? []), { id: crypto.randomUUID(), from: "producer", text, time }] }));
    const replies = cannedReplies[id];
    const reply = replies[replyIndex.current++ % replies.length];
    setTimeout(() => {
      setMessages((all) => ({ ...all, [id]: [...(all[id] ?? []), { id: crypto.randomUUID(), from: "her", ...reply, time }] }));
    }, 1200);
  }

  /** 离开当前对话：通话中先确认（CONTEXT.md「通话」：离开对话页就挂断）。 */
  function navigate(to: string) {
    if (inCall && to !== callId) setLeave({ to });
    else go(to);
  }

  function go(to: string) {
    if (to === "settings" || to === "memories") return; // 原型里不做这两页。
    setSelectedId(to === "list" ? null : to);
  }

  function applyScenario(s: Scenario) {
    const id = selectedId ?? "mano";
    if (s === "idle") return hangUp();
    setCallId(id);
    setCollapsed(false);
    if (s === "dialing") setPhase({ kind: "dialing" });
    if (s === "connected") {
      setLineShown(true);
      connect();
    }
    if (s === "ended") setPhase({ kind: "ended", reason });
  }

  const scenario: Scenario = phase.kind === "idle" ? "idle" : phase.kind;
  const selected = characters.find((c) => c.id === selectedId) ?? null;
  const caller = characters.find((c) => c.id === callId) ?? null;
  const showList = !narrow || selected === null;
  const showConversation = selected !== null;

  const layer =
    caller && phase.kind !== "idle" ? (
      <CallLayer
        character={caller}
        phase={phase}
        elapsed={elapsed}
        collapsed={collapsed && phase.kind !== "ended"}
        micMuted={micMuted}
        textOnly={textOnly}
        line={lineShown ? liveLines[caller.id] : null}
        hearing={hearing ? hearingSample : ""}
        fullScreen={narrow}
        reducedMotion={reducedMotion}
        onCollapse={() => setCollapsed(true)}
        onHangUp={hangUp}
        onToggleMute={() => setMicMuted((m) => !m)}
        onOpenMicPicker={() => setMicPickerOpen(true)}
        onToggleTextOnly={setTextOnly}
        onRedial={() => startCall(caller.id)}
        onDismiss={hangUp}
      />
    ) : null;

  return (
    <HStack height="100dvh" style={{ overflow: "hidden" }}>
      {showList && (
        <VStack
          width={narrow ? "100%" : 320}
          height="100%"
          style={{ flexShrink: 0, borderInlineEnd: narrow ? undefined : "var(--border-width) solid var(--color-border-blue)" }}
        >
          <ConversationList
            characters={characters}
            conversations={empty ? {} : messages}
            selectedId={narrow ? null : selectedId}
            call={callId && inCall ? { characterId: callId, elapsed, connected: phase.kind === "connected" } : null}
            onSelect={navigate}
            onNavigate={navigate}
          />
        </VStack>
      )}
      {showConversation && !(narrow && showList) && selected && (
        <StackItem size="fill" style={{ minWidth: 0, height: "100%" }}>
          <Conversation
            key={selected.id}
            character={selected}
            messages={empty ? [] : (messages[selected.id] ?? [])}
            call={callId === selected.id ? { phase, elapsed, collapsed } : null}
            onBack={narrow ? () => navigate("list") : undefined}
            onCall={() => startCall(selected.id)}
            onExpandCall={() => setCollapsed(false)}
            onSend={(text) => send(selected.id, text)}
            onNewConversation={() => setMessages((all) => ({ ...all, [selected.id]: [] }))}
          >
            {callId === selected.id && layer}
          </Conversation>
        </StackItem>
      )}
      {!narrow && !selected && (
        <StackItem size="fill">
          <VStack height="100%" hAlign="center" vAlign="center">
            <Heading level={2} color="secondary">
              选一位偶像开始对话
            </Heading>
          </VStack>
        </StackItem>
      )}

      <BottomSheet isOpen={micPickerOpen} onOpenChange={setMicPickerOpen} label="切换麦克风" height="hug">
        <VStack gap={3} padding={5}>
          <Heading level={2}>切换麦克风</Heading>
          <List>
            {microphones.map((m) => (
              <ListItem
                key={m.id}
                label={m.label}
                description={m.id === micId ? "正在使用，也是以后通话的默认麦克风" : undefined}
                isSelected={m.id === micId}
                style={m.id === micId && caller ? selectedRow(caller.color) : undefined}
                onClick={() => {
                  setMicId(m.id);
                  setMicPickerOpen(false);
                }}
              />
            ))}
          </List>
        </VStack>
      </BottomSheet>

      <AlertDialog
        isOpen={leave !== null}
        onOpenChange={(open) => !open && setLeave(null)}
        title={`会挂断和${caller?.name ?? "她"}的通话`}
        description="离开这段对话，通话就会结束。这次通话照常计入限额。"
        actionLabel="挂断并离开"
        cancelLabel="留在通话里"
        onAction={() => {
          const to = leave?.to;
          hangUp();
          setLeave(null);
          if (to) go(to);
        }}
      />

      <PrototypeConsole
        scenario={scenario}
        reason={reason}
        collapsed={collapsed}
        hearing={hearing}
        nearLimit={nearLimit}
        empty={empty}
        onScenario={applyScenario}
        onReason={(r) => {
          setReason(r);
          if (phase.kind === "ended") setPhase({ kind: "ended", reason: r });
        }}
        onCollapsed={setCollapsed}
        onHearing={setHearing}
        onNearLimit={setNearLimit}
        onEmpty={setEmpty}
      />
    </HStack>
  );
}
