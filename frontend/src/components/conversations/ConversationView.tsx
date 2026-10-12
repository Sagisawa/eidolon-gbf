"use client";

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
import { cueText } from "@/lib/affinity";
import type { Account, Character } from "@/lib/api";
import type { Entry } from "@/lib/conversationLog";
import type { Failure } from "@/lib/failure";
import { isLive, NOT_OPEN, type LiveConversation } from "@/lib/liveConversation";
import { linesOf, type Line } from "@/lib/messageLines";
import { localOwnKeys, needsOwnLLM, subscribeOwnKeys } from "@/lib/localOwnKeys";
import { settingsHref } from "@/lib/settingsCategory";
import { detectTimezone } from "@/lib/timezone";
import { cn } from "@/lib/utils";
import { herVars } from "@/theme/herVars";
import { AffinityDownIcon, AffinityUpIcon, BackIcon, MoreIcon, PhoneIcon, SendIcon } from "@/theme/icons";
import { Ja } from "@/theme/Ja";

import { AffinityBadge } from "./AffinityBadge";
import { CallBar } from "./CallBar";
import { LiveCallLayer } from "./CallLayer";
import { OutfitPicker } from "./OutfitPicker";
import { useDirectory, useWide } from "./ConversationDirectory";
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
 * 电话键变成实心的「回到通话」。对话的实时状态（连同通话）由导航外壳持有（ADR-0018）：这一页打开时向外壳要她那一份，
 * 离开时交回；通话中离开这一页，通话留在外壳里，回来时一切照旧。她的声音、电话本身的声音和切换麦克风的面板也在外壳里。
 * 她有立绘时，更多菜单里有「换衣装」（spec「衣装与换衣装」）。
 * 好感度可用时，电话键和更多菜单之间是好感度标识（GLOSSARY.md「好感度」）；不可用时读到 null，不显示。
 */
export function ConversationView({
  account,
  character,
  onBack,
}: {
  /** 登录的用户：发回合时带上浏览器里存的、这位用户的自带 LLM；他必须自带 LLM 而这个浏览器里没存时提前拦下。 */
  account: Account;
  character: Character;
  onBack?: () => void;
}) {
  const userId = account.id;
  // 必须自带 LLM、这个浏览器里又没存：输入框和电话键换成提示和去设置的链接。存了（这个或别的标签页）当场恢复。
  const ownLLMMissing = useSyncExternalStore(
    subscribeOwnKeys,
    () => needsOwnLLM(account, localOwnKeys(userId)),
    () => false,
  );
  const { open, close, go } = useDirectory();
  const isFullScreen = !useWide();
  const isReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)", false);
  const [live, setLive] = useState<LiveConversation | null>(null);
  const snapshot = useSyncExternalStore(live?.subscribe ?? noSubscription, live?.snapshot ?? notOpen, notOpen);
  const { conversation, entries, call, layer, hearing, draft, failure } = snapshot;
  const outfits = useStandOutfits(character);
  const [pickingOutfit, setPickingOutfit] = useState(false);
  const subtree = useRef<HTMLDivElement>(null);
  // 她现在对制作人的好感度；读不到（好感度关着、没配判断模型或请求失败）就不显示标识，也不出变化胶囊。
  const { affinity, affinityCue } = snapshot;

  // 向外壳要她的对话（外壳里留着她的通话就用那一份，否则打开她最新的一个，从没聊过就开一个新的）；
  // 离开这一页时交回：通话还在进行就留在外壳里，否则就此告别。
  useEffect(() => {
    const conversation = open(character.id, userId);
    setLive(conversation);
    return () => close(conversation);
  }, [character.id, userId, open, close]);

  const isOpen = conversation.status === "open";
  const inCall = isLive(call);
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
  ) : ownLLMMissing ? null : (
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
      {onBack && (
        <Button variant="ghost" size="icon-lg" className={headerKey} aria-label={t.back} onClick={onBack}>
          <BackIcon className="size-6" />
        </Button>
      )}
      <h1 className="min-w-0 flex-1 truncate px-2 text-header">{character.name}</h1>
      {phoneKey}
      {affinity && (
        <AffinityBadge
          status={affinity}
          cue={affinityCue}
          name={character.name}
          timeZone={detectTimezone()}
          subtree={subtree}
        />
      )}
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
              onBack && (
                <Button variant="outline" onClick={onBack}>
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
  const composer = ownLLMMissing ? (
    // 输入框和电话键换成一句提示和去设置的链接；后端的 403 仍是兜底。
    <div inert={isCovered} className="shrink-0 border-t bg-background px-3 py-2">
      <FailureNotice failure={{ message: t.ownLLMRequired, signedOut: false, toOwnKeys: true }} />
    </div>
  ) : (
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
              {/* 被拦时输入框和电话键都不在，「打字，或者点电话」不对；下面的提示会说明 */}
              {!ownLLMMissing && <EmptyDescription>{t.emptyDescription}</EmptyDescription>}
            </EmptyHeader>
          </Empty>
        ) : (
          <Messages entries={entries} hearing={hearing} character={character} affinityOn={affinity !== null} />
        )}
      </div>
      {composer}
      {live && (
        <LiveCallLayer
          live={live}
          character={character}
          standOutfits={outfits?.toTry ?? []}
          layerRef={focus.layer}
          isFullScreen={isFullScreen}
          onOwnKeys={() => go(settingsHref("own-keys"))}
        />
      )}
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

/**
 * 消息区：官方 Message Scroller，打开时停在最底，新消息和她正在说的话跟着往下滚（制作人往上翻时不抢）。
 * 消息从顶部开始排；气泡之间 4px，换人时多 8px。好感度可用时，改变了好感度的回复后面是一行变化胶囊。
 */
function Messages({
  entries,
  hearing,
  character,
  affinityOn,
}: {
  entries: Entry[];
  hearing: string;
  character: Character;
  affinityOn: boolean;
}) {
  const lines = linesOf(entries, new Date(), affinityOn);
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
              ) : line.kind === "cue" ? (
                <MessageScrollerItem key={line.key} className="mt-2 flex justify-center">
                  {/* 好感度的变化胶囊：样子和日期条一样，一个升降小箭头加一句话，不用她的颜色 */}
                  <span className="flex items-center gap-1 rounded-full bg-foreground/10 px-3 py-1 text-meta text-muted-foreground">
                    {line.change.up ? (
                      <AffinityUpIcon aria-hidden className="size-3" />
                    ) : (
                      <AffinityDownIcon aria-hidden className="size-3" />
                    )}
                    {cueText(line.change, character.name)}
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
