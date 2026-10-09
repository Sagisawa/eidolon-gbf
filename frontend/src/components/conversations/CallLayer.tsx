"use client";

import { useEffect, useRef, useState, type ComponentType, type ReactNode, type RefObject, type SVGProps } from "react";

import { MarkedAvatar } from "@/components/app/MarkedAvatar";
import { Button } from "@/components/ui/button";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { copy } from "@/i18n";
import type { Character, Outfit, Segment } from "@/lib/api";
import type { CallEnd } from "@/lib/callEnd";
import { clock, showTime } from "@/lib/callTime";
import type { CallState, LiveCall, MicNotice } from "@/lib/liveConversation";
import type { StandDirection } from "@/lib/standAnimations";
import { cn } from "@/lib/utils";
import {
  CollapseIcon,
  HangUpIcon,
  MicIcon,
  MicOffIcon,
  MicSwitchIcon,
  PhoneIcon,
  TextOnlyIcon,
} from "@/theme/icons";
import { Ja } from "@/theme/Ja";

import { Stand } from "./stand/Stand";
import { useCallTime } from "./useCallTime";

const t = copy.call;

/** 通话层上显示的通话：拨打中、通话中，或者因故结束。 */
export type ShownCall = LiveCall | Extract<CallState, { phase: "ended" }>;

type Props = {
  character: Character;
  call: ShownCall;
  /** 收起：回到 IM，通话照常继续。收起时整层 inert，焦点由对话页送回页上。 */
  isCollapsed: boolean;
  /** 通话层这一整层；对话页用它看焦点在不在层里。 */
  layerRef: RefObject<HTMLElement | null>;
  /** 手机上占满整屏；电脑上只盖右边的对话栏。 */
  isFullScreen: boolean;
  isReducedMotion: boolean;
  micMuted: boolean;
  /** 麦克风出了状况时要说的话。 */
  micNotice: MicNotice | null;
  textOnly: boolean;
  /** 她当前这句；还没开口时为 null。 */
  line: Segment | null;
  /** 用户正在说、还没定稿的话。 */
  hearing: string;
  /** 她的立绘该是什么样子；她没有立绘时用不上。 */
  standDirection: StandDirection;
  /** 立绘依次试的衣装：选中的那套，再是默认衣装；她没有立绘时用不上。 */
  standOutfits: readonly Outfit[];
  onCollapse: () => void;
  onHangUp: () => void;
  onToggleMic: () => void;
  /** 打开麦克风列表。 */
  onSwitchMic: () => void;
  onToggleTextOnly: () => void;
  onRedial: () => void;
  onDismiss: () => void;
  /** 结束页上「去设置自带密钥」。 */
  onOwnKeys: () => void;
};

/**
 * 通话层（DESIGN.md「Call layer」）：从对话栏底部整张滑上来，收起是同一个动作反过来（410ms、ease-call），
 * 减少动态效果时没有过渡。强制深色（`.dark`），文字白色、次要字 80% 白。
 *
 * 底是她的头像放大模糊（有背景图时换成清晰的背景图），上面压一层到 call.deep 的渐变。
 * 没有立绘时中部是 112px 头像、名字和状态行；她有立绘时（`character.stand`）立绘做底，名字和状态行缩进头部，
 * 底部压暗。台词放在底部的毛玻璃卡里，再下面是毛玻璃底栏；结束后台词卡换成同样毛玻璃的结束卡。
 */
export function CallLayer(props: Props) {
  const { character, call, isCollapsed, isFullScreen, isReducedMotion, layerRef } = props;
  const ended = call.phase === "ended";
  const hasStand = Boolean(character.stand);

  // Esc 收起（结束页上是回到对话）；按键时取最新的回调。
  const onEscape = useRef(() => {});
  useEffect(() => {
    onEscape.current = ended ? props.onDismiss : props.onCollapse;
  });
  // 展开时把焦点移进来，屏幕阅读器从这里读起。
  useEffect(() => {
    if (isCollapsed) return;
    layerRef.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) onEscape.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isCollapsed, layerRef]);

  return (
    <section
      ref={layerRef}
      tabIndex={-1}
      aria-label={t.layer(character.name)}
      aria-hidden={isCollapsed}
      inert={isCollapsed}
      className={cn(
        "dark inset-0 z-10 flex flex-col overflow-hidden bg-her-call-deep text-white outline-none",
        isFullScreen ? "fixed" : "absolute",
        // visibility 跟着一起过渡：收起时等滑完才藏起来，展开时立刻可见。第一次出现也从底部滑上来。
        isReducedMotion
          ? "transition-none"
          : "transition-[translate,visibility] duration-410 ease-call starting:translate-y-full",
        isCollapsed ? "invisible translate-y-full" : "translate-y-0",
      )}
    >
      <Backdrop character={character} />
      {hasStand && <StandStage {...props} />}

      <header className="relative grid grid-cols-[1fr_auto_1fr] items-center gap-2 px-4 pt-4">
        <div className="flex justify-start">
          {!ended && (
            <Tooltip>
              <TooltipTrigger
                render={
                  <Button
                    variant="ghost"
                    size="icon-lg"
                    className={cn(isFullScreen && "size-11")}
                    aria-label={t.collapse}
                    onClick={props.onCollapse}
                  />
                }
              >
                <CollapseIcon className="size-6" />
              </TooltipTrigger>
              <TooltipContent>{t.collapseTooltip}</TooltipContent>
            </Tooltip>
          )}
        </div>
        <div className="min-w-0 text-center">
          {hasStand && (
            <>
              <h2 className="truncate text-header font-bold">{character.name}</h2>
              <Status call={call} />
            </>
          )}
        </div>
        <div className="flex justify-end">
          {!ended && (
            <Button
              variant="call-glass"
              size={isFullScreen ? "call" : "call-sm"}
              aria-pressed={props.textOnly}
              onClick={props.onToggleTextOnly}
            >
              <TextOnlyIcon aria-hidden />
              {t.textOnly}
            </Button>
          )}
        </div>
      </header>

      {!hasStand && (
        <div className="relative flex flex-col items-center gap-3 pt-10 text-center">
          <Ripple isOn={call.phase === "dialing"}>
            <MarkedAvatar name={character.name} src={character.avatar_url} size="call" />
          </Ripple>
          <h2 className="mt-2 text-call-name">{character.name}</h2>
          <Status call={call} />
        </div>
      )}

      <div
        className={cn(
          "relative flex min-h-0 flex-1 flex-col items-center gap-3 overflow-y-auto px-5",
          ended ? "justify-center py-6" : "justify-end pb-5",
        )}
      >
        {call.phase === "ended" ? (
          <Ended {...props} end={call.end} />
        ) : (
          <>
            <p role="status" className="text-center text-sm text-white/80">
              {props.micNotice && t.micNotices[props.micNotice]}
            </p>
            {/* 台词卡在接通前不出现 */}
            {call.phase === "connected" && <LineCard {...props} />}
          </>
        )}
      </div>

      {!ended && <Dock {...props} isConnected={call.phase === "connected"} />}
    </section>
  );
}

/**
 * 底：没有背景图时她的头像放大、`blur-3xl`；有背景图时背景图清晰铺满。上面压一层从 25% 黑到
 * call.deep 混黑（`her-call-shade`）的渐变，白字的可读性全靠它（DESIGN.md「Call layer」）。
 */
function Backdrop({ character }: { character: Character }) {
  const src = character.background_url ?? character.avatar_url;
  return (
    <>
      {src && (
        // 纯装饰的底图，不经 next/image：头像要整张放大模糊，背景图按 cover 铺满。
        <img
          src={src}
          alt=""
          aria-hidden
          className={cn(
            "pointer-events-none absolute inset-0 size-full object-cover",
            !character.background_url && "scale-125 blur-3xl",
          )}
        />
      )}
      <div aria-hidden className="pointer-events-none absolute inset-0 bg-linear-to-b from-black/25 to-her-call-shade" />
    </>
  );
}

/**
 * 立绘（DESIGN.md「Call layer」的「立绘」）：叠在底图和渐变之上、文字和按钮之下，不接收点击。
 * 只要她有立绘，一打电话就用这套布局，立绘晚到或者加载失败都不切回头像版，台词的位置不跳。
 * - 手机：占下方 80% 的高度，取景到膝，到了从下方升起。
 * - 电脑：铺满头部以下的整层，取景到腰，原地淡入。
 * 底部 50% 压一层到 call.deep 的渐变，台词卡和底栏落在衣服上也看得清。结束后立绘降到 40%。
 */
function StandStage(props: Props) {
  const { call, isCollapsed, isFullScreen, isReducedMotion, standOutfits, standDirection } = props;
  const dial = useDialCount(call.phase);
  return (
    <>
      <div
        aria-hidden
        className={cn(
          "pointer-events-none absolute inset-x-0 bottom-0 transition-opacity duration-500",
          isFullScreen ? "h-[80%]" : "top-16",
          call.phase === "ended" && "opacity-40",
        )}
      >
        <Stand
          // 每拨一次重新载入：上一通失败了，这一通再试一次。
          key={dial}
          outfits={standOutfits}
          framing={isFullScreen ? "knees" : "waist"}
          isPaused={isCollapsed}
          entrance={isFullScreen && !isReducedMotion ? "rise" : "fade"}
          direction={standDirection}
          isReducedMotion={isReducedMotion}
        />
      </div>
      <div
        aria-hidden
        className="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-linear-to-b from-transparent via-her-call-deep/88 via-55% to-her-call-deep"
      />
    </>
  );
}

/** 第几通电话：拨号时加一。 */
function useDialCount(phase: ShownCall["phase"]): number {
  const [seen, setSeen] = useState({ phase, count: 0 });
  if (phase !== seen.phase) {
    const count = seen.count + (phase === "dialing" ? 1 : 0);
    setSeen({ phase, count });
    return count;
  }
  return seen.count;
}

/**
 * 状态行（名字下面）：呼叫中是「正在呼叫」加三个依次闪的小点，通话中是计时，结束后是挂断图标加
 * 「通话已结束 · mm:ss」（没接通过就不带时长）。只用文字和图标，不再用线形。
 */
function Status({ call }: { call: ShownCall }) {
  const time = useCallTime(call);
  const seconds = useEndedSeconds(call);
  return (
    <p className="flex items-center justify-center gap-1.5 text-sm text-white/80 tabular-nums">
      {call.phase === "dialing" && (
        <>
          {t.calling}
          <span aria-hidden className="inline-flex gap-0.5">
            {/* 延迟写在 style 里：animate-pulse 是 animation 简写，会盖掉类里的 animation-delay */}
            {[0, 200, 400].map((delay) => (
              <span
                key={delay}
                className="size-1 rounded-full bg-white/80 motion-safe:animate-pulse"
                style={{ animationDelay: `${delay}ms` }}
              />
            ))}
          </span>
        </>
      )}
      {call.phase === "connected" && time && showTime(time)}
      {call.phase === "ended" && (
        <>
          <HangUpIcon aria-hidden className="size-3.5" />
          {seconds === null ? t.ended : t.endedAfter(clock(seconds))}
        </>
      )}
    </p>
  );
}

/** 结束了的通话打了多久（秒）：记下接通的时刻，结束时算出来；没接通过为 null。 */
function useEndedSeconds(call: ShownCall): number | null {
  const [since, setSince] = useState<number | null>(null);
  const [seconds, setSeconds] = useState<number | null>(null);
  if (call.phase === "connected" && call.since !== since) {
    setSince(call.since);
    setSeconds(null);
  }
  if (call.phase === "dialing" && since !== null) setSince(null);
  const isEnded = call.phase === "ended";
  useEffect(() => {
    if (isEnded && since !== null) setSeconds(Math.max(0, Math.floor((Date.now() - since) / 1000)));
  }, [isEnded, since]);
  return isEnded ? seconds : null;
}

/** 呼叫中、没有立绘时头像外两圈 20% 白的波纹，2 秒一圈；减少动态效果时不放。 */
function Ripple({ isOn, children }: { isOn: boolean; children: ReactNode }) {
  return (
    <div className="relative grid place-items-center">
      {/* 时长和延迟写在 style 里：animate-ping 是 animation 简写，会盖掉类里的 animation-duration */}
      {isOn &&
        [0, 1].map((delay) => (
          <span
            key={delay}
            aria-hidden
            className="absolute inset-0 rounded-full bg-white/20 motion-safe:animate-ping motion-reduce:hidden"
            style={{ animationDuration: "2s", animationDelay: `${delay}s` }}
          />
        ))}
      {children}
    </div>
  );
}

/**
 * 台词卡：她当前这句的日语原文在上、字幕在下；「只看文字」开着时上一句以 45% 不透明度留在上面。
 * 她还没开口时是一句提示。用户正在说、还没定稿的话放在最下面。
 */
function LineCard({ line, hearing, textOnly, call }: Props) {
  const previous = usePreviousLine(line, call.phase);
  return (
    <div className="w-full max-w-[34em] rounded-3xl bg-white/12 px-5 py-4 text-center text-balance backdrop-blur-md">
      <div aria-live="polite">
        {line ? (
          <>
            {textOnly && previous && (
              <div className="mb-3 opacity-45">
                <p className="text-body">
                  <Ja>{previous.ja}</Ja>
                </p>
                {previous.zh && <p className="text-subtitle text-white/80">{previous.zh}</p>}
              </div>
            )}
            <p className="text-call-line leading-relaxed">
              <Ja>{line.ja}</Ja>
            </p>
            {line.zh && <p className="mt-1 text-sm text-white/80">{line.zh}</p>}
          </>
        ) : (
          <p className="text-sm text-white/80">{textOnly ? t.repliesInText : t.speakFreely}</p>
        )}
      </div>
      {hearing && <p className="mt-3 text-sm text-white/80">{t.hearing(hearing)}</p>}
    </div>
  );
}

/**
 * 这通电话里她的上一句。一句话的原文在说的过程中会变长，变长的还是同一句；换了一句，原来那句才成为上一句。
 * 重新拨号时清掉。
 */
function usePreviousLine(line: Segment | null, phase: ShownCall["phase"]): Segment | null {
  const [seen, setSeen] = useState<{ line: Segment | null; previous: Segment | null }>({ line, previous: null });
  let next = seen;
  if (phase === "dialing" && (seen.line || seen.previous)) next = { line: null, previous: null };
  else if (line !== seen.line) {
    const isSameLine = !line || !seen.line || line.ja.startsWith(seen.line.ja);
    next = { line, previous: isSameLine ? seen.previous : seen.line };
  }
  if (next !== seen) setSeen(next);
  return next.previous;
}

/** 结束卡：原因、后端多说的话、说明、是否计入限额，以及「回到对话」和主操作（重拨或「去设置自带密钥」）。 */
function Ended({ end, onRedial, onDismiss, onOwnKeys }: Props & { end: CallEnd }) {
  const ending = t.endings[end.reason];
  const toOwnKeys = end.reason === "over_limit" || end.reason === "own_key";
  return (
    <div
      role="alert"
      className="flex w-full max-w-[34em] flex-col items-center gap-2 rounded-3xl bg-white/12 px-5 py-6 text-center text-balance backdrop-blur-md"
    >
      <h3 className="text-lg font-semibold">{ending.title}</h3>
      {end.detail && <p className="text-sm">{end.detail}</p>}
      <p className="text-sm text-white/80">{ending.body}</p>
      <p className="text-meta text-white/60">{end.counts ? t.counted : t.notCounted}</p>
      <div className="mt-3 flex flex-wrap justify-center gap-2">
        <Button variant="call-glass" size="call" onClick={onDismiss}>
          {t.backToConversation}
        </Button>
        <Button variant="call-solid" size="call" onClick={toOwnKeys ? onOwnKeys : onRedial}>
          {!toOwnKeys && <PhoneIcon aria-hidden />}
          {toOwnKeys ? t.toOwnKeys : t.redial}
        </Button>
      </div>
    </div>
  );
}

/**
 * 底栏：一条毛玻璃胶囊。静音、切换麦克风是 56px 圆形图标键（静音按下时白底黑图标），
 * 挂断是带「挂断」二字的挂断红胶囊。呼叫中静音和切换麦克风置灰，只能挂断。
 */
function Dock({ isConnected, micMuted, onToggleMic, onHangUp, onSwitchMic }: Props & { isConnected: boolean }) {
  return (
    <footer className="relative flex justify-center px-4 pt-2 pb-8">
      <div className="flex items-center gap-2 rounded-full bg-white/12 p-2 backdrop-blur-md">
        <RoundKey
          label={micMuted ? t.micUnmute : t.micMute}
          icon={micMuted ? MicOffIcon : MicIcon}
          isPressed={micMuted}
          isDisabled={!isConnected}
          onClick={onToggleMic}
        />
        <RoundKey label={t.switchMic} icon={MicSwitchIcon} isDisabled={!isConnected} onClick={onSwitchMic} />
        <Button variant="hangup" size="call-dock" onClick={onHangUp} className="ml-2">
          <HangUpIcon aria-hidden />
          {t.hangUp}
        </Button>
      </div>
    </footer>
  );
}

function RoundKey({
  label,
  icon: Icon,
  isPressed,
  isDisabled,
  onClick,
}: {
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  isPressed?: boolean;
  isDisabled?: boolean;
  onClick: () => void;
}) {
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <Button
            variant="call-round"
            size="icon-call-dock"
            aria-label={label}
            aria-pressed={isPressed}
            disabled={isDisabled}
            onClick={onClick}
          />
        }
      >
        <Icon aria-hidden />
      </TooltipTrigger>
      <TooltipContent>{label}</TooltipContent>
    </Tooltip>
  );
}
