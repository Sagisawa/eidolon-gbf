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
import { useMediaQuery } from "@astryxdesign/core/hooks";
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

import { FailureNotice, SignInButton } from "@/components/FailureNotice";
import { copy } from "@/i18n";
import { createConversation, listConversations, listMessages, sendTurn, type Character } from "@/lib/api";
import { startCall } from "@/lib/call";
import { loadCallPreferences, saveCallPreferences } from "@/lib/callPreferences";
import type { Entry } from "@/lib/conversationLog";
import type { Failure } from "@/lib/failure";
import { isLive, LiveConversation, NOT_OPEN, type CallState } from "@/lib/liveConversation";
import { herVars } from "@/theme/herVars";
import { BackIcon, PhoneIcon } from "@/theme/icons";
import { Ja } from "@/theme/Ja";

import { CallLayer, type ShownCall } from "./CallLayer";
import { CallNote } from "./CallNote";
import { MicSheet } from "./MicSheet";
import { useDirectory, useWide } from "./ConversationDirectory";

const t = copy.conversation;

const notOpen = () => NOT_OPEN;
const noSubscription = () => () => {};

/**
 * 和一位角色的 IM 对话页（DESIGN.md「Layout」「Chat bubbles」）：实底页首、只在消息区铺横线纸、
 * Astryx 的气泡和输入栏。对话的状态全在 LiveConversation 里，这里只画它的快照、把操作交给它。
 * 整个子树注入她的颜色（herVars）。
 *
 * 页首的电话键打开通话层并开始呼叫（spec「通话层」）；通话层可以收起回到这里，页首下方留一张便利贴，
 * 电话键变成「回到通话」。离开这一页（换角色、进设置或记忆、回列表）先经列表外壳确认，然后挂断。
 */
export function ConversationView({ character, onBack }: { character: Character; onBack?: () => void }) {
  const router = useRouter();
  const { refresh, setCall, leave } = useDirectory();
  const isFullScreen = !useWide();
  const isReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)", false);
  const [live, setLive] = useState<LiveConversation | null>(null);
  const snapshot = useSyncExternalStore(live?.subscribe ?? noSubscription, live?.snapshot ?? notOpen, notOpen);
  const { status, entries, call, hearing, busy, draft, textOnly, failure, collapsed } = snapshot;
  const characterAudio = useRef<HTMLAudioElement>(null);
  const shownCall = useShownCall(call);

  // 打开她的对话（最新的一个，从没聊过就开一个新的）；离开这一页就和它告别（挂断通话）。
  useEffect(() => {
    const conversation = new LiveConversation(character.id, {
      listConversations,
      createConversation,
      listMessages,
      onListChanged: refresh,
      startCall,
      sendTurn,
      preferences: { load: loadCallPreferences, save: saveCallPreferences },
      onCharacterAudio: (track) => {
        if (characterAudio.current) characterAudio.current.srcObject = new MediaStream([track]);
      },
    });
    setLive(conversation);
    return () => conversation.dispose();
  }, [character.id, refresh]);

  // 通话的进展告诉列表那一行。
  useEffect(() => {
    setCall(isLive(call) ? { characterId: character.id, state: call } : null);
  }, [call, character.id, setCall]);
  useEffect(() => () => setCall(null), [setCall]);

  const isOpen = status === "open";
  const inCall = isLive(call);
  const back = onBack && (() => leave(onBack));
  const dial = () => void live?.startCall();

  // 列表只在拿到空数组时显示空状态，所以把消息和「正在听」放进同一个数组。
  const rows = entries.map((entry) => <Bubble key={entry.key} entry={entry} character={character} />);
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

  // 通话层展开时盖住整栏：底下的页首和对话不能再被 Tab 或屏幕阅读器摸到。
  const isLayerCollapsed = collapsed || call.phase === "idle";
  const isCovered = shownCall !== null && !isLayerCollapsed;
  const phoneKey = isFullScreen ? { ...herButton, ...touchTarget } : herButton;

  const header = (
    <HStack
      as="header"
      inert={isCovered}
      gap={3}
      vAlign="center"
      paddingInline={4}
      paddingBlock={3}
      style={{
        background: "var(--color-background-body)",
        borderBottom: "var(--border-width) solid var(--color-border)",
      }}
    >
      {back && (
        <IconButton
          label={t.back}
          icon={<Icon icon={BackIcon} />}
          variant="ghost"
          onClick={back}
          style={isFullScreen ? touchTarget : undefined}
        />
      )}
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
      {inCall ? (
        <IconButton
          label={copy.call.expand}
          tooltip={copy.call.expand}
          icon={<Icon icon={PhoneIcon} />}
          onClick={() => live?.expand()}
          style={phoneKey}
        />
      ) : (
        <IconButton
          label={t.call(character.name)}
          tooltip={t.callTooltip}
          icon={<Icon icon={PhoneIcon} />}
          isDisabled={!isOpen || busy}
          onClick={dial}
          style={phoneKey}
        />
      )}
      <MoreMenu
        label={t.menu}
        alignment="end"
        items={[
          {
            label: t.newConversation,
            onClick: () => void live?.startNewConversation(),
            isDisabled: !isOpen || busy || inCall || failure?.signedOut,
          },
        ]}
      />
    </HStack>
  );

  if (status === "failed" && failure) {
    return (
      <Frame character={character} header={header}>
        <VStack height="100%" hAlign="center" vAlign="center" padding={6}>
          <EmptyState
            title={t.loadFailed}
            description={failure.message}
            actions={
              failure.signedOut ? (
                <SignInButton />
              ) : (
                back && <Button label={t.backToList} variant="secondary" onClick={back} />
              )
            }
          />
        </VStack>
      </Frame>
    );
  }

  return (
    <Frame character={character} header={header}>
      {isLive(call) && collapsed && <CallNote call={call} onExpand={() => live?.expand()} />}
      {/* 没登录时要给出去登录的入口，输入框的状态行放不下按钮；通话层盖着时不放，免得 Tab 摸到底下 */}
      {failure?.signedOut && !isCovered && <FailureNotice failure={failure} />}
      <StackItem size="fill" inert={isCovered} style={{ ...ruledPaper, minHeight: 0 }}>
        {/* 开新对话的过程中也是 opening：旧对话留在原处，只是发送键和电话键禁用 */}
        {!isOpen && entries.length === 0 ? (
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
                onSubmit={() => void live?.submit()}
                placeholder={t.placeholder}
                isDisabled={!isOpen}
                status={failure && !failure.signedOut ? { type: "error", message: failureText(failure) } : undefined}
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
      <audio ref={characterAudio} autoPlay muted={textOnly} />
      {shownCall && (
        <CallLayer
          character={character}
          call={shownCall}
          isCollapsed={isLayerCollapsed}
          isFullScreen={isFullScreen}
          isReducedMotion={isReducedMotion}
          micMuted={snapshot.micMuted}
          micNotice={snapshot.micNotice}
          textOnly={textOnly}
          line={snapshot.line}
          hearing={hearing}
          onCollapse={() => live?.collapse()}
          onHangUp={() => void live?.hangUp()}
          onToggleMic={() => live?.toggleMic()}
          onSwitchMic={() => live?.openMicPicker()}
          onToggleTextOnly={() => live?.toggleTextOnly()}
          onRedial={dial}
          onDismiss={() => live?.dismissEnd()}
          onOwnKeys={() => leave(() => router.push("/settings"))}
        />
      )}
      <MicSheet
        isOpen={snapshot.pickingMic}
        onOpenChange={(isOpen) => (isOpen ? live?.openMicPicker() : live?.closeMicPicker())}
        color={character.color}
        micId={snapshot.micId}
        onSelect={(micId) => void live?.switchMic(micId)}
      />
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

function Bubble({ entry, character }: { entry: Entry; character: Character }) {
  const metadata = (
    <ChatMessageMetadata timestamp={<Timestamp value={entry.at} format="time" hasTooltip={false} />} />
  );
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

/** 失败提示：后端给的原因，知道算不算限额时加一句（CONTEXT.md「限额」）。 */
function failureText(failure: Failure): string {
  return failure.countsTowardLimit === false ? `${failure.message} ${t.notCounted}` : failure.message;
}

/**
 * 通话层上要画的通话：通话中和结束页照实画；挂断回到空闲后，留着最后一刻的样子，收起的动画才有东西可收。
 * 这一页还没打过电话时为 null，通话层不出现。
 */
function useShownCall(call: CallState): ShownCall | null {
  const [shown, setShown] = useState<ShownCall | null>(null);
  if (call.phase !== "idle" && call !== shown) setShown(call);
  return call.phase === "idle" ? shown : call;
}

/** 她颜色的圆形电话键（DESIGN.md「Her call button」）。 */
const herButton: CSSProperties = {
  borderRadius: "var(--radius-full)",
  background: "var(--her-button)",
  color: "var(--her-button-fg)",
  border: 0,
};

/** 手机上页首的按钮不小于 44px，和通话层一致；页首本来就有 48px 的头像，高度不变。 */
const touchTarget: CSSProperties = { minWidth: "var(--spacing-11)", minHeight: "var(--spacing-11)" };

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
