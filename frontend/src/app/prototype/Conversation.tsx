import { Avatar } from "@astryxdesign/core/Avatar";
import {
  ChatComposer,
  ChatLayout,
  ChatMessage,
  ChatMessageBubble,
  ChatMessageList,
  ChatMessageMetadata,
} from "@astryxdesign/core/Chat";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { Icon } from "@astryxdesign/core/Icon";
import { IconButton } from "@astryxdesign/core/IconButton";
import { MoreMenu } from "@astryxdesign/core/MoreMenu";
import { StackItem } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useState } from "react";

import { type CallPhase, clock } from "./call";
import type { Character, Message } from "./data";
import { herVars } from "./herVars";
import { BackIcon, PhoneIcon } from "./icons";
import { Ja } from "./Ja";

type Props = {
  character: Character;
  messages: Message[];
  /** 这段对话里正在进行的通话；没有时为 null。 */
  call: { phase: CallPhase; elapsed: number; collapsed: boolean } | null;
  onBack?: () => void;
  onCall: () => void;
  onExpandCall: () => void;
  onSend: (text: string) => void;
  onNewConversation: () => void;
  /** 通话层，盖在这一栏上。 */
  children?: React.ReactNode;
};

export function Conversation({
  character,
  messages,
  call,
  onBack,
  onCall,
  onExpandCall,
  onSend,
  onNewConversation,
  children,
}: Props) {
  const [draft, setDraft] = useState("");
  const inCall = call !== null && (call.phase.kind === "dialing" || call.phase.kind === "connected");

  return (
    <VStack height="100%" style={{ ...herVars(character.color), position: "relative", overflow: "hidden" }}>
      <HStack
        as="header"
        gap={3}
        vAlign="center"
        paddingInline={4}
        paddingBlock={3}
        style={{
          background: "var(--color-background-body)",
          borderBottom: "var(--border-width) solid var(--color-border)",
        }}
      >
        {onBack && <IconButton label="返回对话列表" icon={<Icon icon={BackIcon} />} variant="ghost" onClick={onBack} />}
        <Avatar
          src={character.avatar}
          name={character.name}
          size="lg"
          tooltip={false}
          style={{ boxShadow: "0 0 0 var(--spacing-0-5) var(--her-mark)" }}
        />
        <StackItem size="fill">
          <Heading level={1} style={{ fontSize: "var(--text-large-size)" }}>
            {character.name}
          </Heading>
        </StackItem>
        <IconButton
          label={inCall ? "回到通话" : `和${character.name}通话`}
          tooltip={inCall ? "回到通话" : "语音通话"}
          icon={<Icon icon={PhoneIcon} />}
          variant="secondary"
          onClick={inCall ? onExpandCall : onCall}
          style={{
            borderRadius: "var(--radius-full)",
            background: "var(--her-button)",
            color: "var(--her-button-fg)",
            border: 0,
          }}
        />
        <MoreMenu alignment="end" variant="ghost" label="更多操作" items={[{ label: "新对话", onClick: onNewConversation }]} />
      </HStack>

      <StackItem size="fill" style={{ ...ruledPaper, minHeight: 0 }}>
        <VStack height="100%">
          {call && call.collapsed && inCall && (
            <CallNote phase={call.phase} elapsed={call.elapsed} onClick={onExpandCall} />
          )}
          <StackItem size="fill" style={{ minHeight: 0 }}>
            <ChatLayout
              style={{ height: "100%" }}
              composer={
                <ChatComposer
                  value={draft}
                  onChange={setDraft}
                  placeholder="说点什么…"
                  onSubmit={(value) => {
                    if (!value.trim()) return;
                    onSend(value.trim());
                    setDraft("");
                  }}
                />
              }
            >
              <ChatMessageList
                align="top"
                gap={4}
                emptyState={
                  <EmptyState
                    title={`和${character.name}说点什么吧`}
                    description="打字，或者点右上角的电话和她通话。"
                  />
                }
              >
                {messages.map((m) =>
                  m.from === "producer" ? (
                    <ChatMessage key={m.id} sender="user">
                      <ChatMessageBubble
                        metadata={<ChatMessageMetadata timestamp={m.time} />}
                        style={{ background: "var(--office-ink)", color: "var(--color-background-body)" }}
                      >
                        {m.text}
                      </ChatMessageBubble>
                    </ChatMessage>
                  ) : (
                    <ChatMessage
                      key={m.id}
                      sender="assistant"
                      avatar={<Avatar src={character.avatar} name={character.name} size="md" tooltip={false} />}
                    >
                      <ChatMessageBubble
                        metadata={<ChatMessageMetadata timestamp={m.time} />}
                        style={{ background: "var(--her-paper)", color: "var(--color-text-primary)" }}
                      >
                        <VStack gap={1}>
                          <Ja>
                            <Text type="large" weight="normal">
                              {m.ja}
                            </Text>
                          </Ja>
                          <Text type="supporting" style={{ color: "var(--her-paper-muted)" }}>
                            {m.zh}
                          </Text>
                        </VStack>
                      </ChatMessageBubble>
                    </ChatMessage>
                  ),
                )}
              </ChatMessageList>
            </ChatLayout>
          </StackItem>
        </VStack>
      </StackItem>

      {children}
    </VStack>
  );
}

/** 收起后留在页首的便利贴。线形表示状态：实线=通话中，虚线=拨打中。 */
function CallNote({ phase, elapsed, onClick }: { phase: CallPhase; elapsed: number; onClick: () => void }) {
  const connected = phase.kind === "connected";
  return (
    <HStack hAlign="center" paddingBlock={3}>
      <button
        type="button"
        onClick={onClick}
        style={{
          appearance: "none",
          border: 0,
          cursor: "pointer",
          font: "inherit",
          color: "var(--color-text-primary)",
          background: "var(--her-note)",
          padding: "var(--spacing-2) var(--spacing-5)",
          transform: "rotate(-1.2deg)",
          boxShadow: "0 var(--spacing-0-5) var(--spacing-2) var(--color-shadow)",
          position: "relative",
        }}
      >
        <VStack
          as="span"
          aria-hidden
          style={{
            position: "absolute",
            insetBlockStart: "calc(var(--spacing-2) * -1)",
            insetInlineStart: "50%",
            width: "var(--spacing-12)",
            height: "var(--spacing-4)",
            transform: "translateX(-50%) rotate(2deg)",
            background: "color-mix(in srgb, var(--color-background-body) 55%, transparent)",
            boxShadow: "0 0 0 var(--border-width) color-mix(in srgb, var(--color-border-blue) 60%, transparent)",
          }}
        />
        <Text
          weight="medium"
          hasTabularNumbers
          style={{
            textDecorationLine: "underline",
            textDecorationStyle: connected ? "solid" : "dashed",
            textDecorationColor: "var(--her-note-rule)",
            textDecorationThickness: "var(--spacing-0-5)",
            textUnderlineOffset: "var(--spacing-1-5)",
          }}
        >
          {connected ? `通话中 ${clock(elapsed)} · 点击返回` : "正在呼叫… · 点击返回"}
        </Text>
      </button>
    </HStack>
  );
}

/** 横线手帐纸：天蓝横线加一条页边距线，只铺在消息区。 */
const ruledPaper: React.CSSProperties = {
  backgroundColor: "var(--color-background-body)",
  backgroundImage: [
    "linear-gradient(to right, transparent var(--spacing-4), var(--color-border-emphasized) var(--spacing-4), var(--color-border-emphasized) calc(var(--spacing-4) + var(--border-width)), transparent calc(var(--spacing-4) + var(--border-width)))",
    "linear-gradient(to bottom, transparent calc(var(--spacing-8) - var(--border-width)), var(--color-border-blue) calc(var(--spacing-8) - var(--border-width)))",
  ].join(", "),
  backgroundSize: "100% 100%, 100% var(--spacing-8)",
};
