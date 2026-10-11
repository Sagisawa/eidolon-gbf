"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, useSyncExternalStore, type ReactElement, type ReactNode, type RefObject } from "react";

import { FailureNotice, SignInButton } from "@/components/app/FailureNotice";
import { MarkedAvatar } from "@/components/app/MarkedAvatar";
import { Bubble, BubbleContent } from "@/components/ui/bubble";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Empty, EmptyContent, EmptyDescription, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Message, MessageContent, MessageHeader } from "@/components/ui/message";
import {
  MessageScroller,
  MessageScrollerContent,
  MessageScrollerItem,
  MessageScrollerProvider,
  MessageScrollerViewport,
} from "@/components/ui/message-scroller";
import { Spinner } from "@/components/ui/spinner";
import { Textarea } from "@/components/ui/textarea";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { copy } from "@/i18n";
import { createConversation, listConversations, listMessages, sendTurn, type Character } from "@/lib/api";
import { startCall } from "@/lib/call";
import { loadCallPreferences, saveCallPreferences } from "@/lib/callPreferences";
import { CharacterVoice } from "@/lib/characterVoice";
import { dayOf } from "@/lib/conversationList";
import type { Entry } from "@/lib/conversationLog";
import type { Failure } from "@/lib/failure";
import { isLive, LiveConversation, NOT_OPEN } from "@/lib/liveConversation";
import { settingsHref } from "@/lib/settingsTab";
import { cn } from "@/lib/utils";
import { herVars } from "@/theme/herVars";
import { BackIcon, MoreIcon, PhoneIcon, SendIcon } from "@/theme/icons";
import { Ja } from "@/theme/Ja";

import { CallBar } from "./CallBar";
import { CallLayer } from "./CallLayer";
import { MicSheet } from "./MicSheet";
import { OutfitPicker } from "./OutfitPicker";
import { useDirectory, useWide } from "./ConversationDirectory";
import { useCallTones } from "./useCallTones";
import { useFocusBack } from "./useFocusBack";
import { useStandOutfits } from "./useStandOutfits";

const t = copy.conversation;

const notOpen = () => NOT_OPEN;
const noSubscription = () => () => {};

/**
 * 和一位角色的 IM 对话页（DESIGN.md「Layout」「Chat bubbles」）：页首和消息区铺她的壁纸，
 * 成组的 22px 圆角气泡，实底的输入栏。对话的状态全在 LiveConversation 里，这里只画它的快照、把操作交给它。
 * 整个子树注入她的颜色（herVars），浮层（更多菜单）的 container 指回这棵子树。
 *
 * 页首的电话键打开通话层并开始呼叫（spec「通话层」）；通话层可以收起回到这里，页首下面出现通话条，
 * 电话键变成实心的「回到通话」。离开这一页（换角色、进设置或记忆、回列表）先经列表外壳确认，然后挂断。
 * 她有立绘时，更多菜单里有「换衣装」（spec「衣装与换衣装」）。
 */
export function ConversationView({
  userId,
  character,
  onBack,
}: {
  /** 登录的用户：发回合时带上浏览器里存的、这位用户的自带 LLM。 */
  userId: string;
  character: Character;
  onBack?: () => void;
}) {
  const router = useRouter();
  const { refresh, handOver, leave } = useDirectory();
  const isFullScreen = !useWide();
  const isReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)", false);
  const [live, setLive] = useState<LiveConversation | null>(null);
  const snapshot = useSyncExternalStore(live?.subscribe ?? noSubscription, live?.snapshot ?? notOpen, notOpen);
  const { conversation, entries, call, layer, hearing, draft, textOnly, failure } = snapshot;
  // 她的声音：<audio> 交给它，什么时候拨号、播放、静音由 LiveConversation 告诉它。
  const [voice] = useState(() => new CharacterVoice());
  const outfits = useStandOutfits(character);
  const [pickingOutfit, setPickingOutfit] = useState(false);
  const subtree = useRef<HTMLDivElement>(null);
  // 电话本身的声音（铃声、接通音、挂断音）：像她的声音一样交给 LiveConversation。
  const tones = useCallTones();

  // 打开她的对话（最新的一个，从没聊过就开一个新的）；离开这一页就和它告别（挂断通话，停下她的声音）。
  useEffect(() => {
    const conversation = new LiveConversation(character.id, {
      listConversations,
      createConversation,
      listMessages,
      onListChanged: refresh,
      startCall: (conversationId, preferences, handlers) => startCall(conversationId, preferences, handlers, userId),
      sendTurn: (conversationId, text) => sendTurn(conversationId, text, userId),
      preferences: { load: loadCallPreferences, save: saveCallPreferences },
      voice,
      tones,
    });
    // 交给列表一次：它自己订阅这份快照，那一行跟着通话走；离开这一页时收回。
    setLive(conversation);
    handOver(conversation);
    return () => {
      conversation.dispose();
      handOver(null);
    };
  }, [character.id, userId, refresh, voice, tones, handOver]);

  const isOpen = conversation.status === "open";
  const inCall = isLive(call);
  const back = onBack && (() => leave(onBack));
  // 要在这次点击里同步调用：她的声音趁这一下唤醒 AudioContext。
  const dial = () => void live?.startCall();

  // 通话层展开时盖住整栏：底下的页首和对话不能再被 Tab 或屏幕阅读器摸到。快照里的 layer
  // 已经管着「画哪一通、收没收起」；通话条只在通话中、通话层收着时出现。
  const isCovered = layer !== null && !layer.collapsed;
  const barShown = isLive(call) && layer?.collapsed === true;
  const focus = useFocusBack({ layerOpen: isCovered, noteShown: barShown });

  // 页首的图标键：手机上触控目标不小于 44px（DESIGN.md「Layout」）。
  const headerKey = "max-md:size-11";
  const phoneKey = inCall ? (
    <HeaderTip label={copy.call.expand}>
      <Button
        ref={focus.phoneKey}
        variant="ghost"
        size="icon-lg"
        className={headerKey}
        aria-label={copy.call.expand}
        onClick={() => live?.expand()}
      >
        {/* 通话中换成实心图标 */}
        <PhoneIcon className="size-5 fill-current text-her-mark" />
      </Button>
    </HeaderTip>
  ) : (
    <HeaderTip label={t.callTooltip}>
      <Button
        ref={focus.phoneKey}
        variant="ghost"
        size="icon-lg"
        className={headerKey}
        aria-label={t.call(character.name)}
        disabled={!snapshot.canDial}
        focusableWhenDisabled
        onClick={dial}
      >
        <PhoneIcon className="size-5 text-her-mark" />
      </Button>
    </HeaderTip>
  );

  const header = (
    <header inert={isCovered} className="flex h-14 shrink-0 items-center gap-1 px-2">
      {back && (
        <Button variant="ghost" size="icon-lg" className={headerKey} aria-label={t.back} onClick={back}>
          <BackIcon className="size-6" />
        </Button>
      )}
      <h1 className="min-w-0 flex-1 truncate px-2 text-header">{character.name}</h1>
      {phoneKey}
      <DropdownMenu>
        <DropdownMenuTrigger
          render={<Button variant="ghost" size="icon-lg" className={headerKey} aria-label={t.menu} />}
        >
          <MoreIcon className="size-5" />
        </DropdownMenuTrigger>
        <DropdownMenuContent container={subtree} align="end">
          <DropdownMenuItem disabled={!snapshot.canStartNew} onClick={() => void live?.startNewConversation()}>
            {t.newConversation}
          </DropdownMenuItem>
          {outfits && <DropdownMenuItem onClick={() => setPickingOutfit(true)}>{t.outfits.open}</DropdownMenuItem>}
        </DropdownMenuContent>
      </DropdownMenu>
    </header>
  );

  if (conversation.status === "failed") {
    return (
      <Frame character={character} subtree={subtree} header={header}>
        <Empty>
          <EmptyHeader>
            <EmptyTitle>{t.loadFailed}</EmptyTitle>
            <EmptyDescription>{conversation.failure.message}</EmptyDescription>
          </EmptyHeader>
          <EmptyContent>
            {conversation.failure.signedOut ? (
              <SignInButton />
            ) : (
              back && (
                <Button variant="outline" onClick={back}>
                  {t.backToList}
                </Button>
              )
            )}
          </EmptyContent>
        </Empty>
      </Frame>
    );
  }

  const canSend = isOpen && draft.trim() !== "";
  const composer = (
    <form
      inert={isCovered}
      className="flex shrink-0 flex-col gap-2 border-t bg-background px-3 py-2"
      onSubmit={(e) => {
        e.preventDefault();
        void live?.submit();
      }}
    >
      {/* 失败的原因（没登录时带去登录的入口）；通话层盖着时整栏 inert，Tab 摸不到 */}
      {failure && <FailureNotice failure={{ ...failure, message: failureText(failure) }} />}
      <div className="flex items-end gap-2">
        <Textarea
          variant="composer"
          rows={1}
          value={draft}
          onChange={(e) => live?.setDraft(e.target.value)}
          onKeyDown={(e) => {
            // 回车发送，Shift+回车换行；输入法选字时的回车不算。
            if (e.key === "Enter" && !e.shiftKey && !e.nativeEvent.isComposing) {
              e.preventDefault();
              void live?.submit();
            }
          }}
          placeholder={t.placeholder}
          aria-label={t.placeholder}
          disabled={!isOpen}
          className="flex-1"
        />
        <Button type="submit" variant="her" size="icon-lg" aria-label={t.send} disabled={!canSend}>
          <SendIcon className="size-5" />
        </Button>
      </div>
    </form>
  );

  return (
    <Frame character={character} subtree={subtree} header={header}>
      {barShown && <CallBar ref={focus.note} call={call} onExpand={() => live?.expand()} />}
      <div inert={isCovered} className="min-h-0 flex-1">
        {/* 开新对话的过程中也是 opening：旧对话留在原处，只是发送键和电话键禁用 */}
        {!isOpen && entries.length === 0 ? (
          <div className="flex h-full items-center justify-center">
            <Spinner className="size-6 text-muted-foreground" aria-label={t.loading} />
          </div>
        ) : entries.length === 0 && !hearing ? (
          <Empty className="h-full">
            <EmptyHeader>
              <EmptyTitle>{t.emptyTitle(character.name)}</EmptyTitle>
              <EmptyDescription>{t.emptyDescription}</EmptyDescription>
            </EmptyHeader>
          </Empty>
        ) : (
          <Messages entries={entries} hearing={hearing} character={character} />
        )}
      </div>
      {composer}
      {/* 静音由 voice 管：只看文字，或者她的声音改走电话质感时，这里只是持有音轨 */}
      <audio ref={voice.attach} autoPlay />
      {layer && (
        <CallLayer
          character={character}
          call={layer.call}
          isCollapsed={layer.collapsed}
          layerRef={focus.layer}
          isFullScreen={isFullScreen}
          isReducedMotion={isReducedMotion}
          micMuted={snapshot.micMuted}
          micNotice={snapshot.micNotice}
          textOnly={textOnly}
          line={snapshot.line}
          previousLine={snapshot.previousLine}
          hearing={hearing}
          standDirection={snapshot.stand}
          standOutfits={outfits?.toTry ?? []}
          onCollapse={() => live?.collapse()}
          onHangUp={() => void live?.hangUp()}
          onToggleMic={() => live?.toggleMic()}
          onSwitchMic={() => live?.openMicPicker()}
          onToggleTextOnly={() => live?.toggleTextOnly()}
          onRedial={dial}
          onDismiss={() => live?.dismissEnd()}
          onOwnKeys={() => leave(() => router.push(settingsHref("own-keys")))}
        />
      )}
      <MicSheet
        isOpen={snapshot.pickingMic}
        onOpenChange={(open) => (open ? live?.openMicPicker() : live?.closeMicPicker())}
        micId={snapshot.micId}
        onSelect={(micId) => void live?.switchMic(micId)}
      />
      {outfits && (
        <OutfitPicker
          isOpen={pickingOutfit}
          onOpenChange={setPickingOutfit}
          isWide={!isFullScreen}
          isReducedMotion={isReducedMotion}
          color={character.color}
          outfits={outfits}
        />
      )}
    </Frame>
  );
}

/**
 * 对话这一栏：注入她的颜色，铺她的壁纸（页首和消息区同一张，DESIGN.md「The Wallpaper Rule」），
 * 页首在上，其余填满。通话层绝对定位盖在上面。
 */
function Frame({
  character,
  subtree,
  header,
  children,
}: {
  character: Character;
  subtree: RefObject<HTMLDivElement | null>;
  header: ReactNode;
  children: ReactNode;
}) {
  return (
    <div
      ref={subtree}
      style={herVars(character.color)}
      className="relative flex h-full flex-col overflow-hidden bg-her-wall text-foreground"
    >
      {header}
      {children}
    </div>
  );
}

/** 页首图标键的提示。 */
function HeaderTip({ label, children }: { label: string; children: ReactElement }) {
  return (
    <Tooltip>
      <TooltipTrigger render={children} />
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}

/** 消息区的一行：跨天处的日期条，或者一条消息和它在组里的位置（The Bubble Group Rule）。 */
type Line =
  | { kind: "day"; key: string; label: string }
  | { kind: "entry"; entry: Entry; first: boolean; last: boolean };

/** 按日期和说话的人把消息排成行：换了一天先放日期条；同一个人连着发、中间没有日期条的算一组。 */
function linesOf(entries: Entry[], now: Date): Line[] {
  const days = entries.map((e) => new Date(e.at).toDateString());
  const lines: Line[] = [];
  entries.forEach((entry, i) => {
    const newDay = i === 0 || days[i] !== days[i - 1];
    if (newDay) lines.push({ kind: "day", key: `day-${days[i]}`, label: dayLabel(new Date(entry.at), now) });
    const next = entries[i + 1];
    lines.push({
      kind: "entry",
      entry,
      first: newDay || entries[i - 1].kind !== entry.kind,
      last: !next || days[i + 1] !== days[i] || next.kind !== entry.kind,
    });
  });
  return lines;
}

/** 日期条上的字：今天、昨天，今年写月日，更早写年月日（和列表的写法一样）。 */
function dayLabel(at: Date, now: Date): string {
  const list = copy.conversationList;
  switch (dayOf(at, now)) {
    case "today":
      return t.today;
    case "yesterday":
      return list.yesterday;
    case "thisYear":
      return list.monthDay(String(at.getMonth() + 1), String(at.getDate()));
    case "earlier":
      return list.fullDate(String(at.getFullYear()), String(at.getMonth() + 1), String(at.getDate()));
  }
}

/**
 * 消息区：官方 Message Scroller，打开时停在最底，新消息和她正在说的话跟着往下滚（制作人往上翻时不抢）。
 * 消息从顶部开始排；气泡之间 4px，换人时多 8px。
 */
function Messages({ entries, hearing, character }: { entries: Entry[]; hearing: string; character: Character }) {
  const lines = linesOf(entries, new Date());
  return (
    <MessageScrollerProvider autoScroll defaultScrollPosition="end">
      <MessageScroller>
        <MessageScrollerViewport>
          <MessageScrollerContent className="gap-1 px-3 pt-2 pb-4">
            {lines.map((line) =>
              line.kind === "day" ? (
                <MessageScrollerItem key={line.key} className="my-3 flex justify-center">
                  <span className="rounded-full bg-foreground/10 px-3 py-1 text-meta text-muted-foreground">
                    {line.label}
                  </span>
                </MessageScrollerItem>
              ) : (
                <MessageScrollerItem key={line.entry.key} messageId={line.entry.key} className={cn(line.first && "mt-2")}>
                  <Bubbled line={line} character={character} />
                </MessageScrollerItem>
              ),
            )}
            {hearing && (
              <MessageScrollerItem key="hearing" className="mt-2">
                {/* 用户正在说、还没定稿的话：制作人那一侧，不成气泡 */}
                <Message align="end">
                  <Bubble variant="ghost" align="end">
                    <BubbleContent aria-label={t.hearing}>
                      <p className="text-body text-muted-foreground">{hearing}</p>
                    </BubbleContent>
                  </Bubble>
                </Message>
              </MessageScrollerItem>
            )}
          </MessageScrollerContent>
        </MessageScrollerViewport>
      </MessageScroller>
    </MessageScrollerProvider>
  );
}

/**
 * 一条消息。制作人的在右，深蓝墨水；她的在左，日语原文在上、中文字幕在下（The Original-Then-Subtitle Rule）。
 * 头像和名字只在一组的第一条，时间只在最后一条的外侧底部。
 */
function Bubbled({
  line: { entry, first, last },
  character,
}: {
  line: Extract<Line, { kind: "entry" }>;
  character: Character;
}) {
  const time = <time className="shrink-0 pb-0.5 text-meta text-muted-foreground tabular-nums">{clock(entry.at)}</time>;
  if (entry.kind === "user") {
    return (
      <Message align="end">
        <div className="flex min-w-0 flex-1 items-end justify-end gap-1.5">
          {last && time}
          <Bubble variant="producer" align="end" joinsPrevious={!first} joinsNext={!last}>
            <BubbleContent>
              <p className="text-body whitespace-pre-wrap">{entry.text}</p>
            </BubbleContent>
          </Bubble>
        </div>
      </Message>
    );
  }
  return (
    <Message align="start">
      {first ? (
        <MarkedAvatar name={character.name} src={character.avatar_url} size="bubble" />
      ) : (
        <span aria-hidden className="w-bubble-avatar shrink-0" />
      )}
      <MessageContent className="gap-1">
        {first && <MessageHeader className="px-1">{character.name}</MessageHeader>}
        <div className="flex min-w-0 items-end gap-1.5">
          <Bubble variant="her" joinsPrevious={!first} joinsNext={!last}>
            <BubbleContent>
              {entry.segments.length === 0 ? (
                <Spinner className="my-1 text-muted-foreground" aria-label={t.replying(character.name)} />
              ) : (
                <div className="flex flex-col gap-2">
                  {entry.segments.map((segment, i) => (
                    <div key={i} className="flex flex-col gap-0.5">
                      <p className="text-japanese-line">
                        <Ja>{segment.ja}</Ja>
                      </p>
                      {segment.zh && <p className="text-subtitle text-muted-foreground">{segment.zh}</p>}
                    </div>
                  ))}
                </div>
              )}
            </BubbleContent>
          </Bubble>
          {last && !entry.pending && time}
        </div>
      </MessageContent>
    </Message>
  );
}

/** 气泡旁的时刻，写成 8:49（和列表里今天的时间一样）。 */
function clock(at: string): string {
  const d = new Date(at);
  return `${d.getHours()}:${String(d.getMinutes()).padStart(2, "0")}`;
}

/** 失败提示：后端给的原因，知道算不算限额时加一句（GLOSSARY.md「限额」）。 */
function failureText(failure: Failure): string {
  return failure.countsTowardLimit === false ? `${failure.message} ${t.notCounted}` : failure.message;
}
