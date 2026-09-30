"use client";

import { Avatar } from "@astryxdesign/core/Avatar";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { Icon } from "@astryxdesign/core/Icon";
import { IconButton } from "@astryxdesign/core/IconButton";
import { StackItem } from "@astryxdesign/core/Stack";
import { Switch } from "@astryxdesign/core/Switch";
import { Text } from "@astryxdesign/core/Text";
import { MediaTheme } from "@astryxdesign/core/theme";
import { VStack } from "@astryxdesign/core/VStack";
import { useEffect, useRef, useState, type ComponentType, type CSSProperties, type ReactNode, type SVGProps } from "react";

import { copy } from "@/i18n";
import type { Character, Outfit, Segment } from "@/lib/api";
import type { CallEnd } from "@/lib/callEnd";
import { showTime } from "@/lib/callTime";
import { CALL_MUTED } from "@/lib/imageColor";
import type { CallState, LiveCall, MicNotice } from "@/lib/liveConversation";
import type { StandDirection } from "@/lib/standAnimations";
import { CollapseIcon, HangUpIcon, MicIcon, MicOffIcon, MicSwitchIcon } from "@/theme/icons";
import { Ja } from "@/theme/Ja";
import { lineState } from "@/theme/lineState";

import { Stand } from "./stand/Stand";
import { useCallTime } from "./useCallTime";

const t = copy.call;

/** 通话层上显示的通话：拨打中、通话中，或者因故结束。 */
export type ShownCall = LiveCall | Extract<CallState, { phase: "ended" }>;

type Props = {
  character: Character;
  call: ShownCall;
  /** 收起：回到 IM，通话照常继续。收起时整层 inert。 */
  isCollapsed: boolean;
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
 * 通话层（DESIGN.md「Call layer」）：像一张折好的纸，从页首整张拉下来；收起是同一个动作反过来。
 * 强制深色；她的背景图全幅，上面叠她 call.top 到 call.deep 的渐变，没有背景图时只用渐变。
 * 她有立绘时（`character.stand`）用立绘版的布局：手机「大立绘」、电脑「半身 ADV」。
 */
export function CallLayer(props: Props) {
  const { character, call, isCollapsed, isFullScreen, isReducedMotion } = props;
  const layer = useRef<HTMLElement>(null);
  const ended = call.phase === "ended";

  // Esc 收起（结束页上是回到对话）；按键时取最新的回调。
  const onEscape = useRef(() => {});
  useEffect(() => {
    onEscape.current = ended ? props.onDismiss : props.onCollapse;
  });
  // 展开时把焦点移进来，屏幕阅读器从这里读起。
  useEffect(() => {
    if (isCollapsed) return;
    layer.current?.focus();
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !e.defaultPrevented) onEscape.current();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [isCollapsed]);

  return (
    <VStack
      as="section"
      ref={layer}
      tabIndex={-1}
      aria-label={t.layer(character.name)}
      aria-hidden={isCollapsed}
      inert={isCollapsed}
      style={{
        position: isFullScreen ? "fixed" : "absolute",
        inset: 0,
        zIndex: 1,
        outline: "none",
        colorScheme: "dark",
        color: "var(--color-text-primary)",
        backgroundColor: "var(--her-call-deep)",
        backgroundImage: backdrop(character.background_url),
        backgroundSize: "cover",
        backgroundPosition: "center",
        clipPath: isCollapsed ? "inset(0 0 100% 0)" : "inset(0 0 0 0)",
        visibility: isCollapsed ? "hidden" : "visible",
        transition: isReducedMotion
          ? "none"
          : `clip-path var(--duration-medium) var(--ease-standard), visibility 0s linear ${isCollapsed ? "var(--duration-medium)" : "0s"}`,
      }}
    >
      <MediaTheme mode="dark">
        <VStack height="100%" paddingInline={5} paddingBlock={4} style={onCall}>
          <HStack vAlign="center" gap={3}>
            <StackItem size="fill" style={{ minWidth: 0 }}>
              {!ended && (
                <IconButton
                  label={t.collapse}
                  tooltip={t.collapseTooltip}
                  icon={<Icon icon={CollapseIcon} />}
                  variant="ghost"
                  onClick={props.onCollapse}
                  style={isFullScreen ? { ...touchTarget, minWidth: "var(--spacing-11)" } : undefined}
                />
              )}
            </StackItem>
            <Text type="supporting" color="secondary">
              {t.heading}
            </Text>
            <StackItem size="fill" style={{ minWidth: 0 }}>
              {!ended && (
                <HStack hAlign="end">
                  <Switch
                    label={t.textOnly}
                    value={props.textOnly}
                    onChange={props.onToggleTextOnly}
                    size="sm"
                    style={isFullScreen ? { ...touchTarget, justifyContent: "center" } : undefined}
                  />
                </HStack>
              )}
            </StackItem>
          </HStack>

          {character.stand ? (
            <StandBody {...props} outfit={character.stand.default_outfit} />
          ) : (
            <StackItem size="fill" isScrollable>
              <VStack minHeight="100%" hAlign="center" vAlign="center" gap={4} paddingBlock={4}>
                <Avatar
                  src={character.avatar_url ?? undefined}
                  name={character.name}
                  size="xl"
                  tooltip={false}
                  style={portrait}
                />
                <Name character={character} />
                <Words {...props} />
              </VStack>
            </StackItem>
          )}

          {!ended && <Controls {...props} isConnected={call.phase === "connected"} />}
        </VStack>
      </MediaTheme>
    </VStack>
  );
}

/**
 * 立绘版的布局（spec「通话层」）。只要她有立绘，一打电话就用它，立绘晚到或者加载失败都不切回去，
 * 字幕的位置在通话中途不会跳。立绘叠在背景图和纱上面，在文字和按钮下面；底部压一层她颜色的深色渐变，
 * 按钮和对话框落在衣服上也看得清。
 * - 手机「大立绘」：立绘从底部升起，贴着头顶、到膝；名字、计时和字幕在上方。
 * - 电脑「半身 ADV」：立绘铺满整层，贴着头顶、到腰；名字、计时和字幕在底部半透明的对话框里。
 */
function StandBody(props: Props & { outfit: Outfit }) {
  const { character, call, isCollapsed, isFullScreen, isReducedMotion, outfit, standDirection } = props;
  const dial = useDialCount(call.phase);
  const stand = (
    <Stand
      // 每拨一次重新载入：上一通失败了，这一通再试一次。
      key={dial}
      outfit={outfit}
      framing={isFullScreen ? "knees" : "waist"}
      isPaused={isCollapsed}
      entrance={isFullScreen && !isReducedMotion ? "rise" : "fade"}
      direction={standDirection}
      isReducedMotion={isReducedMotion}
    />
  );

  if (isFullScreen) {
    return (
      <>
        <VStack style={{ ...behind, insetInline: 0, bottom: 0, height: "78%" }}>{stand}</VStack>
        <VStack style={bottomShade} />
        <StackItem size="fill" isScrollable>
          <VStack hAlign="center" gap={3} paddingBlock={2}>
            <Name character={character} />
            <Words {...props} />
          </VStack>
        </StackItem>
      </>
    );
  }
  return (
    <>
      <VStack style={{ ...behind, inset: 0 }}>{stand}</VStack>
      <VStack style={bottomShade} />
      <StackItem size="fill" />
      <VStack hAlign="center" gap={2} padding={4} style={dialogBox}>
        <HStack width="100%">
          <Text weight="medium" style={{ color: "var(--her-call-rule)" }}>
            {character.name}
          </Text>
        </HStack>
        <Words {...props} />
      </VStack>
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

function Name({ character }: { character: Character }) {
  return (
    <Heading level={2} style={{ fontSize: "var(--text-large-size)" }}>
      {character.name}
    </Heading>
  );
}

/** 名字下面的内容：通话中是状态和字幕，结束后是结束页。 */
function Words(props: Props) {
  const { call } = props;
  return call.phase === "ended" ? <Ended {...props} end={call.end} /> : <Live {...props} call={call} />;
}

/** 拨打中、通话中：状态和计时，她当前这句的日语和字幕，用户正在说的话。 */
function Live({ call, line, hearing, textOnly, micNotice }: Props & { call: LiveCall }) {
  const time = useCallTime(call);
  if (!time) return <Status line="dashed">{t.dialing}</Status>;
  return (
    <VStack hAlign="center" gap={6} width="100%" maxWidth="34em">
      <VStack hAlign="center" gap={2}>
        <Status line="solid">{showTime(time)}</Status>
        <Text type="supporting" color="secondary" justify="center" role="status">
          {micNotice && t.micNotices[micNotice]}
        </Text>
      </VStack>
      <VStack hAlign="center" gap={2} aria-live="polite" style={{ minHeight: "calc(var(--spacing-12) * 2.5)" }}>
        {line ? (
          <>
            <Ja>
              <Text type="large" weight="normal" justify="center" textWrap="balance">
                {line.ja}
              </Text>
            </Ja>
            {line.zh && (
              <Text color="secondary" justify="center" textWrap="balance">
                {line.zh}
              </Text>
            )}
          </>
        ) : (
          <Text color="secondary">{textOnly ? t.repliesInText : t.speakFreely}</Text>
        )}
      </VStack>
      {hearing && (
        <Text type="supporting" color="secondary" justify="center">
          {t.hearing(hearing)}
        </Text>
      )}
    </VStack>
  );
}

/** 结束页：原因、后端多说的话、是否计入限额，以及「回到对话」和主操作。 */
function Ended({ end, isFullScreen, onRedial, onDismiss, onOwnKeys }: Props & { end: CallEnd }) {
  const size = isFullScreen ? touchTarget : undefined;
  const ending = t.endings[end.reason];
  const toOwnKeys = end.reason === "over_limit" || end.reason === "own_key";
  return (
    <VStack hAlign="center" gap={4} maxWidth="26em" role="alert">
      <Status line="struck">{t.ended}</Status>
      <Heading level={3} style={{ textAlign: "center" }}>
        {ending.title}
      </Heading>
      {end.detail && <Text justify="center">{end.detail}</Text>}
      <Text color="secondary" justify="center">
        {ending.body}
      </Text>
      <Text type="supporting" color="secondary" justify="center">
        {end.counts ? t.counted : t.notCounted}
      </Text>
      <HStack gap={3} wrap="wrap" hAlign="center">
        <Button label={t.backToConversation} variant="secondary" onClick={onDismiss} style={size} />
        {toOwnKeys ? (
          <Button label={t.toOwnKeys} variant="primary" onClick={onOwnKeys} style={size} />
        ) : (
          <Button label={t.redial} variant="primary" onClick={onRedial} style={size} />
        )}
      </HStack>
    </VStack>
  );
}

/** 状态行。线形表示状态（DESIGN.md「The Line-State Rule」）：虚线=拨打中，实线=通话中，删除线=已结束。 */
function Status({ line, children }: { line: "dashed" | "solid" | "struck"; children: ReactNode }) {
  return (
    <Text
      hasTabularNumbers
      weight="medium"
      style={lineState(line, "var(--her-call-rule)")}
    >
      {children}
    </Text>
  );
}

/** 底部三枚圆形键：麦克风静音 · 挂断 · 切换麦克风。拨打中只能挂断。 */
function Controls({ isConnected, micMuted, onToggleMic, onHangUp, onSwitchMic }: Props & { isConnected: boolean }) {
  return (
    <HStack hAlign="center" gap={8} paddingBlock={6}>
      <RoundControl
        label={micMuted ? t.micUnmute : t.micMute}
        icon={micMuted ? MicOffIcon : MicIcon}
        isPressed={micMuted}
        isDisabled={!isConnected}
        onClick={onToggleMic}
      />
      <RoundControl label={t.hangUp} icon={HangUpIcon} tone="danger" onClick={onHangUp} />
      <RoundControl label={t.switchMic} icon={MicSwitchIcon} isDisabled={!isConnected} onClick={onSwitchMic} />
    </HStack>
  );
}

function RoundControl({
  label,
  icon,
  tone,
  isPressed,
  isDisabled,
  onClick,
}: {
  label: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  tone?: "danger";
  isPressed?: boolean;
  isDisabled?: boolean;
  onClick: () => void;
}) {
  return (
    <VStack hAlign="center" gap={2}>
      <IconButton
        label={label}
        icon={<Icon icon={icon} size="lg" />}
        variant={tone === "danger" ? "destructive" : "secondary"}
        isDisabled={isDisabled}
        aria-pressed={isPressed}
        onClick={onClick}
        style={{
          width: roundSize,
          height: roundSize,
          borderRadius: "var(--radius-full)",
          ...(tone !== "danger" && {
            background: isPressed
              ? "var(--color-text-primary)"
              : translucentWhite,
            color: isPressed ? "var(--her-call-deep)" : "var(--color-text-primary)",
            border: 0,
          }),
        }}
      />
      <Text type="supporting" color="secondary" aria-hidden>
        {label}
      </Text>
    </VStack>
  );
}

/** 通话层上圆形键和次要按钮的底：16% 的白（DESIGN.md「Round controls」）。 */
const translucentWhite = "color-mix(in srgb, var(--color-text-primary) 16%, transparent)";

/** 手机上每个能点的东西不小于 44px（spec「通话层」）。 */
const touchTarget: CSSProperties = { minHeight: "var(--spacing-11)" };

/** 圆形控制键 64px，手机上也远大于 44px 的触控下限。 */
const roundSize = "calc(var(--spacing-8) * 2)";

/**
 * 背景：她的背景图全幅，上面叠一层从 call.top 到 call.deep 的渐变，白字才读得清；没有背景图时渐变不透明，
 * 头像背后再透一点原色的光晕（DESIGN.md「Call layer」）。
 */
function backdrop(backgroundUrl: string | null): string {
  const glow =
    "radial-gradient(50% 32% at 50% 38%, color-mix(in oklab, var(--her-call-glow) 30%, transparent) 0%, transparent 100%)";
  if (!backgroundUrl) {
    return `${glow}, linear-gradient(180deg, var(--her-call-top) 0%, var(--her-call-deep) 62%)`;
  }
  const veil =
    "linear-gradient(180deg, color-mix(in oklab, var(--her-call-top) 82%, transparent) 0%, color-mix(in oklab, var(--her-call-deep) 94%, transparent) 62%, var(--her-call-deep) 100%)";
  return `${veil}, url(${JSON.stringify(backgroundUrl)})`;
}

/**
 * 通话层上的覆盖：次要字是 74% 的白，与 imageColor 校验用的 CALL_MUTED 一致；
 * 开关的圆钮取 surface 色，在她的颜色上换成白色才看得见（DESIGN.md「Switch」）；
 * 次要按钮的底（neutral）在系统浅色时会取到浅色模式的深墨水，这里和圆形键一样换成半透明的白。
 */
const onCall = {
  "--color-text-secondary": `color-mix(in srgb, var(--color-text-primary) ${CALL_MUTED * 100}%, transparent)`,
  "--color-background-surface": "var(--color-text-primary)",
  "--color-neutral": translucentWhite,
} as CSSProperties;

/**
 * 铺在通话层底下的立绘：在背景图和纱之上，在文字和按钮之下（整层 zIndex 1 自成层叠上下文），
 * 不接收点击。
 */
const behind: CSSProperties = { position: "absolute", zIndex: -1, pointerEvents: "none" };

/** 底部压的一层她颜色的深色渐变，挂断、静音这些按钮落在衣服上也看得清（DESIGN.md「Call layer」）。 */
const bottomShade: CSSProperties = {
  ...behind,
  insetInline: 0,
  bottom: 0,
  height: "45%",
  background:
    "linear-gradient(180deg, transparent 0%, color-mix(in oklab, var(--her-call-deep) 88%, transparent) 55%, var(--her-call-deep) 100%)",
};

/** 电脑「半身 ADV」的对话框：72% 的 call.deep，一圈 call.rule 细线（DESIGN.md「Call layer」）。 */
const dialogBox: CSSProperties = {
  borderRadius: "var(--radius-container)",
  background: "color-mix(in oklab, var(--her-call-deep) 72%, transparent)",
  boxShadow: "0 0 0 var(--border-width) var(--her-call-rule)",
};

/** 大头像：她的 call.rule 描边加柔和投影（DESIGN.md「Call portrait」）。 */
const portrait: CSSProperties = {
  boxShadow: "0 0 0 var(--spacing-1) var(--her-call-rule), 0 var(--spacing-3) var(--spacing-10) var(--color-shadow)",
};
