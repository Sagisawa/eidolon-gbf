"use client";

import { Avatar } from "@astryxdesign/core/Avatar";
import { Button } from "@astryxdesign/core/Button";
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
import { Spinner } from "@astryxdesign/core/Spinner";
import { StackItem } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { Timestamp } from "@astryxdesign/core/Timestamp";
import { VStack } from "@astryxdesign/core/VStack";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore, type CSSProperties, type ReactNode } from "react";

import { copy } from "@/i18n";
import {
  createConversation,
  listConversations,
  listMessages,
  sendTurn,
  type Character,
  type Message,
} from "@/lib/api";
import { startCall } from "@/lib/call";
import { loadCallPreferences, saveCallPreferences } from "@/lib/callPreferences";
import type { Entry } from "@/lib/conversationLog";
import { toFailure, type Failure } from "@/lib/failure";
import { LiveConversation, NOT_OPEN } from "@/lib/liveConversation";
import { herVars } from "@/theme/herVars";
import { BackIcon, CheckIcon, HangUpIcon, PhoneIcon } from "@/theme/icons";
import { Ja } from "@/theme/Ja";

import { useDirectory } from "./ConversationDirectory";

const t = copy.conversation;

/** 要打开的对话和它已经记下的消息。 */
type Opened = { id: string; messages: Message[] };

const notOpen = () => NOT_OPEN;
const noSubscription = () => () => {};

/**
 * 和一位角色的 IM 对话页（DESIGN.md「Layout」「Chat bubbles」）：实底页首、只在消息区铺横线纸、
 * Astryx 的气泡和输入栏。对话的状态全在 LiveConversation 里，这里只画它的快照、把操作交给它。
 * 整个子树注入她的颜色（herVars）；离开这一页（换角色、回列表）就挂断通话，和原来一样。
 *
 * 通话层是 ticket 04 的事：这里先保留原来的通话功能——页首的电话键开始 / 挂断，通话中在页首下方
 * 显示状态，「只看文字」在 ⋯ 菜单里。
 */
export function ConversationView({ character, onBack }: { character: Character; onBack?: () => void }) {
  const { refresh, setCall } = useDirectory();
  const [opened, setOpened] = useState<Opened | null>(null);
  const [live, setLive] = useState<LiveConversation | null>(null);
  const [pageError, setPageError] = useState<Failure | null>(null);
  const { entries, phase, hearing, busy, draft, muted, failure } = useSyncExternalStore(
    live?.subscribe ?? noSubscription,
    live?.snapshot ?? notOpen,
    notOpen,
  );
  const characterAudio = useRef<HTMLAudioElement>(null);
  const times = useEntryTimes(entries, opened?.messages);

  // 打开她最新的一次对话；从没聊过就开一个新的。
  useEffect(() => {
    let cancelled = false;
    (async () => {
      try {
        const [latest] = await listConversations(character.id);
        const conversation = latest ?? (await createConversation(character.id));
        if (!latest) refresh(); // 列表里她那一行从「还没有对话」变成新对话
        const messages = await listMessages(conversation.id);
        if (!cancelled) setOpened({ id: conversation.id, messages });
      } catch (e) {
        if (!cancelled) setPageError(toFailure(e));
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [character.id, refresh]);

  // 离开这一页、或者开了新对话，就和打开着的这一个告别（挂断通话）。
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

  // 通话的进展告诉列表那一行。
  useEffect(() => {
    setCall(phase === "idle" ? null : { characterId: character.id, phase });
  }, [phase, character.id, setCall]);
  useEffect(() => () => setCall(null), [setCall]);

  // 一个回合记下之后，列表里的最后一句跟着更新。
  const settled = entries.filter((e) => !(e.kind === "character" && e.pending)).length;
  const seen = useRef<number | null>(null);
  useEffect(() => {
    if (!live) return;
    if (seen.current !== null && seen.current !== settled) refresh();
    seen.current = settled;
  }, [live, settled, refresh]);

  async function startNewConversation() {
    setPageError(null);
    try {
      const conversation = await createConversation(character.id);
      seen.current = null;
      setOpened({ id: conversation.id, messages: [] });
      refresh();
    } catch (e) {
      setPageError(toFailure(e));
    }
  }

  const error = pageError ?? failure;
  const inCall = phase !== "idle";

  // 列表只在拿到空数组时显示空状态，所以把消息和「正在听」放进同一个数组。
  const rows = entries.map((entry) => (
    <Bubble key={entry.key} entry={entry} character={character} at={times.get(entry.key)} />
  ));
  if (hearing) {
    rows.push(
      <ChatMessage key="hearing" sender="user">
        <ChatMessageBubble variant="ghost">
          <Text color="secondary" aria-label={t.hearing}>
            {hearing}
          </Text>
        </ChatMessageBubble>
      </ChatMessage>,
    );
  }

  const header = (
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
      {onBack && <IconButton label={t.back} icon={<Icon icon={BackIcon} />} variant="ghost" onClick={onBack} />}
      <Avatar
        src={character.avatar_url ?? undefined}
        name={character.name}
        size="lg"
        tooltip={false}
        style={{ boxShadow: "0 0 0 var(--spacing-0-5) var(--her-mark)" }}
      />
      <StackItem size="fill" style={{ minWidth: 0 }}>
        <Heading level={1} maxLines={1} style={{ fontSize: "var(--text-large-size)" }}>
          {character.name}
        </Heading>
      </StackItem>
      {phase === "active" ? (
        <IconButton
          label={t.hangUp}
          tooltip={t.hangUp}
          icon={<Icon icon={HangUpIcon} />}
          variant="destructive"
          onClick={() => void live?.toggleCall()}
          style={{ borderRadius: "var(--radius-full)" }}
        />
      ) : (
        <IconButton
          label={t.call(character.name)}
          tooltip={t.callTooltip}
          icon={<Icon icon={PhoneIcon} />}
          isLoading={phase === "connecting"}
          isDisabled={!live || busy}
          onClick={() => {
            setPageError(null);
            void live?.toggleCall();
          }}
          style={herButton}
        />
      )}
      <MoreMenu
        label={t.menu}
        alignment="end"
        items={[
          {
            label: t.newConversation,
            onClick: () => void startNewConversation(),
            isDisabled: !live || busy || inCall,
          },
          {
            label: t.textOnly,
            endContent: muted ? <Icon icon={CheckIcon} /> : undefined,
            onClick: () => live?.toggleMute(),
            isDisabled: !live,
          },
        ]}
      />
    </HStack>
  );

  if (pageError && !opened) {
    return (
      <Frame character={character} header={header}>
        <VStack height="100%" hAlign="center" vAlign="center" padding={6}>
          <EmptyState
            title={t.loadFailed}
            description={pageError.message}
            actions={onBack && <Button label={t.backToList} variant="secondary" onClick={onBack} />}
          />
        </VStack>
      </Frame>
    );
  }

  return (
    <Frame character={character} header={header}>
      {inCall && <CallStrip phase={phase} />}
      <StackItem size="fill" style={{ ...ruledPaper, minHeight: 0 }}>
        {!opened ? (
          <VStack height="100%" hAlign="center" vAlign="center">
            <Spinner size="lg" aria-label={t.loading} />
          </VStack>
        ) : (
          <ChatLayout
            style={{ height: "100%" }}
            composer={
              <ChatComposer
                value={draft}
                onChange={(value) => live?.setDraft(value)}
                onSubmit={() => {
                  setPageError(null);
                  void live?.submit();
                }}
                placeholder={t.placeholder}
                isDisabled={!live}
                status={error ? { type: "error", message: failureText(error) } : undefined}
                statusPosition="top"
              />
            }
          >
            <ChatMessageList
              align="top"
              gap={4}
              isStreaming={entries.some((e) => e.kind === "character" && e.pending)}
              emptyState={
                <EmptyState title={t.emptyTitle(character.name)} description={t.emptyDescription} />
              }
            >
              {rows}
            </ChatMessageList>
          </ChatLayout>
        )}
      </StackItem>
      <audio ref={characterAudio} autoPlay muted={muted} />
    </Frame>
  );
}

/** 对话这一栏：注入她的颜色，页首在上，其余填满。 */
function Frame({ character, header, children }: { character: Character; header: ReactNode; children: ReactNode }) {
  return (
    <VStack height="100%" style={{ ...herVars(character.color), position: "relative", overflow: "hidden" }}>
      {header}
      {children}
    </VStack>
  );
}

function Bubble({ entry, character, at }: { entry: Entry; character: Character; at: string | undefined }) {
  const metadata = at ? <ChatMessageMetadata timestamp={<Timestamp value={at} format="time" hasTooltip={false} />} /> : undefined;
  if (entry.kind === "user") {
    return (
      <ChatMessage sender="user">
        <ChatMessageBubble metadata={metadata} style={producerBubble}>
          {entry.text}
        </ChatMessageBubble>
      </ChatMessage>
    );
  }
  return (
    <ChatMessage
      sender="assistant"
      avatar={<Avatar src={character.avatar_url ?? undefined} name={character.name} size="md" tooltip={false} />}
    >
      <ChatMessageBubble metadata={entry.pending ? undefined : metadata} style={herBubble}>
        {entry.segments.length === 0 ? (
          <Spinner size="sm" aria-label={t.replying(character.name)} />
        ) : (
          <VStack gap={2}>
            {entry.segments.map((segment, i) => (
              <VStack key={i} gap={0.5}>
                <Ja>
                  <Text type="large" weight="normal">
                    {segment.ja}
                  </Text>
                </Ja>
                {segment.zh && (
                  <Text type="supporting" style={{ color: "var(--her-paper-muted)" }}>
                    {segment.zh}
                  </Text>
                )}
              </VStack>
            ))}
          </VStack>
        )}
      </ChatMessageBubble>
    </ChatMessage>
  );
}

/** 通话中的状态条（ticket 04 的通话层做好前的过渡）。线形表示状态：虚线=正在呼叫，实线=通话中。 */
function CallStrip({ phase }: { phase: "connecting" | "active" }) {
  return (
    <HStack
      hAlign="center"
      paddingBlock={2}
      paddingInline={4}
      role="status"
      style={{
        background: "var(--color-background-body)",
        borderBottom: "var(--border-width) solid var(--color-border)",
      }}
    >
      <Text
        weight="medium"
        style={{
          textDecorationLine: "underline",
          textDecorationStyle: phase === "active" ? "solid" : "dashed",
          textDecorationColor: "var(--her-note-rule)",
          textDecorationThickness: "var(--spacing-0-5)",
          textUnderlineOffset: "var(--spacing-1-5)",
        }}
      >
        {phase === "active" ? t.inCall : t.calling}
      </Text>
    </HStack>
  );
}

/** 失败提示：后端给的原因，知道算不算限额时加一句（CONTEXT.md「限额」）。 */
function failureText(failure: Failure): string {
  return failure.countsTowardLimit === false ? `${failure.message} ${t.notCounted}` : failure.message;
}

/**
 * 每条消息的时间：记下的消息用它记下的时间；这次新出现的（刚发出的、刚收到的）用它出现的时间。
 * conversationLog 的条目不带时间，所以在这里对着 key 记一份。
 */
function useEntryTimes(entries: Entry[], messages: Message[] | undefined): Map<string, string> {
  const times = useRef(new Map<string, string>());
  const loaded = useRef<Message[] | undefined>(undefined);
  if (messages !== loaded.current) {
    loaded.current = messages;
    times.current = new Map((messages ?? []).map((m) => [`m${m.id}`, m.created_at]));
  }
  const now = new Date().toISOString();
  for (const entry of entries) {
    const pending = entry.kind === "character" && entry.pending;
    if (!pending && !times.current.has(entry.key)) times.current.set(entry.key, now);
  }
  return times.current;
}

/** 她颜色的圆形电话键（DESIGN.md「Her call button」）。 */
const herButton: CSSProperties = {
  borderRadius: "var(--radius-full)",
  background: "var(--her-button)",
  color: "var(--her-button-fg)",
  border: 0,
};

/** 制作人的气泡：事务所深蓝墨水底、纸色字（深色模式下自动换成夜间墨水和夜间纸色）。 */
const producerBubble: CSSProperties = {
  background: "var(--office-ink)",
  color: "var(--color-background-body)",
};

/** 她的气泡：她的 paper 底、墨水色正文。 */
const herBubble: CSSProperties = {
  background: "var(--her-paper)",
  color: "var(--color-text-primary)",
};

/** 横线手帐纸：天蓝横线加一条装订边距线，只铺在消息区（DESIGN.md「The Paper-Only-Where-She-Writes Rule」）。 */
const ruledPaper: CSSProperties = {
  backgroundColor: "var(--color-background-body)",
  backgroundImage: [
    "linear-gradient(to right, transparent var(--spacing-4), var(--color-border-emphasized) var(--spacing-4), var(--color-border-emphasized) calc(var(--spacing-4) + var(--border-width)), transparent calc(var(--spacing-4) + var(--border-width)))",
    "linear-gradient(to bottom, transparent calc(var(--spacing-8) - var(--border-width)), var(--color-border-blue) calc(var(--spacing-8) - var(--border-width)))",
  ].join(", "),
  backgroundSize: "100% 100%, 100% var(--spacing-8)",
};
