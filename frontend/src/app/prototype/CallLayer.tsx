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

import { CALL_MUTED } from "@/lib/imageColor";

import { CALL_LIMIT_SECONDS, type CallPhase, clock, endings } from "./call";
import type { Character } from "./data";
import { Ja } from "./Ja";
import { CollapseIcon, HangUpIcon, MicIcon, MicOffIcon, MicSwitchIcon } from "./icons";

type Props = {
  character: Character;
  phase: CallPhase;
  elapsed: number;
  collapsed: boolean;
  micMuted: boolean;
  textOnly: boolean;
  /** 她当前这句；还没开口时为 null。 */
  line: { ja: string; zh: string } | null;
  /** 用户正在说、还没定稿的话。 */
  hearing: string;
  fullScreen: boolean;
  reducedMotion: boolean;
  onCollapse: () => void;
  onHangUp: () => void;
  onToggleMute: () => void;
  onOpenMicPicker: () => void;
  onToggleTextOnly: (next: boolean) => void;
  onRedial: () => void;
  onDismiss: () => void;
};

/** 通话层：像一张折好的纸，从页首整张拉下来；收起是同一个动作反过来。 */
export function CallLayer(props: Props) {
  const { character, phase, collapsed, fullScreen, reducedMotion } = props;

  return (
    <VStack
      as="section"
      aria-label={`和${character.name}的通话`}
      aria-hidden={collapsed}
      inert={collapsed}
      style={{
        position: fullScreen ? "fixed" : "absolute",
        inset: 0,
        zIndex: 20,
        colorScheme: "dark",
        color: "var(--color-text-primary)",
        // 背景图到位前的占位：她的印象色压到深色。
        // 背景图到位前的占位：上沿是能放白字的她的颜色，往下压到深色；头像背后透一点原色。
        backgroundColor: "var(--her-call-deep)",
        backgroundImage:
          "radial-gradient(50% 32% at 50% 38%, color-mix(in oklab, var(--her-call-glow) 30%, transparent) 0%, transparent 100%), linear-gradient(180deg, var(--her-call-top) 0%, var(--her-call-deep) 62%)",
        clipPath: collapsed ? "inset(0 0 100% 0)" : "inset(0 0 0 0)",
        visibility: collapsed ? "hidden" : "visible",
        transition: reducedMotion
          ? "none"
          : `clip-path var(--duration-medium) var(--ease-standard), visibility 0s linear ${collapsed ? "var(--duration-medium)" : "0s"}`,
      } as React.CSSProperties}
      onKeyDown={(e) => {
        if (e.key === "Escape" && phase.kind !== "ended") props.onCollapse();
      }}
    >
      <MediaTheme mode="dark">
        <VStack
          height="100%"
          paddingInline={5}
          paddingBlock={4}
          // 次要字：74% 的白，与 imageColor 里校验用的 CALL_MUTED 一致。
          style={
            {
              "--color-text-secondary": `color-mix(in srgb, var(--color-text-primary) ${CALL_MUTED * 100}%, transparent)`,
              // 开关的圆钮取 surface 色；在通话层上换成白色，才能和她的颜色拉开对比。
              "--color-background-surface": "var(--color-text-primary)",
            } as React.CSSProperties
          }
        >
          <HStack vAlign="center" gap={3}>
            {phase.kind !== "ended" && (
              <IconButton
                label="收起通话"
                tooltip="收起（Esc）"
                icon={<Icon icon={CollapseIcon} />}
                variant="ghost"
                onClick={props.onCollapse}
              />
            )}
            <StackItem size="fill" style={{ textAlign: "center" }}>
              <Text type="supporting" color="secondary">
                语音通话
              </Text>
            </StackItem>
            {phase.kind !== "ended" && (
              <Switch
                label="只看文字"
                value={props.textOnly}
                onChange={(next) => props.onToggleTextOnly(next)}
                size="sm"
              />
            )}
          </HStack>

          <StackItem size="fill">
            <VStack height="100%" hAlign="center" vAlign="center" gap={4}>
              <Avatar
                src={character.avatar}
                name={character.name}
                size="xl"
                tooltip={false}
                style={{ boxShadow: "0 0 0 var(--spacing-1) var(--her-call-rule), 0 var(--spacing-3) var(--spacing-10) var(--color-shadow)" }}
              />
              <Heading level={2} style={{ fontSize: "var(--text-heading-3-size)" }}>
                {character.name}
              </Heading>
              {phase.kind === "ended" ? (
                <Ended {...props} reason={phase.reason} />
              ) : (
                <Live {...props} />
              )}
            </VStack>
          </StackItem>

          {phase.kind !== "ended" && <Controls {...props} />}
        </VStack>
      </MediaTheme>
    </VStack>
  );
}

function Live({ phase, elapsed, line, hearing, textOnly }: Props) {
  if (phase.kind === "dialing") {
    return <Status dashed>正在呼叫…</Status>;
  }
  if (phase.kind !== "connected") return null;
  const remaining = CALL_LIMIT_SECONDS - elapsed;
  return (
    <VStack hAlign="center" gap={6} width="100%" maxWidth="34em">
      <Status>{remaining < 60 ? `还剩 ${clock(remaining)}` : clock(elapsed)}</Status>
      <VStack hAlign="center" gap={2} minHeight="calc(var(--spacing-12) * 2.5)" aria-live="polite">
        {line ? (
          <>
            <Ja>
              <Text type="large" weight="normal" justify="center" textWrap="balance">
                {line.ja}
              </Text>
            </Ja>
            <Text color="secondary" justify="center" textWrap="balance">
              {line.zh}
            </Text>
          </>
        ) : (
          <Text color="secondary">{textOnly ? "她会用文字回复" : "直接说话就好"}</Text>
        )}
      </VStack>
      {hearing && (
        <Text type="supporting" color="secondary" justify="center">
          你：{hearing}…
        </Text>
      )}
    </VStack>
  );
}

/** 状态行。线形表示状态：虚线=拨打中，实线=通话中，删除线=已结束。 */
function Status({ children, dashed, struck }: { children: React.ReactNode; dashed?: boolean; struck?: boolean }) {
  return (
    <Text
      hasTabularNumbers
      weight="medium"
      style={{
        textDecorationLine: struck ? "line-through" : "underline",
        textDecorationStyle: dashed ? "dashed" : "solid",
        textDecorationColor: "var(--her-call-rule)",
        textDecorationThickness: "var(--spacing-0-5)",
        textUnderlineOffset: "var(--spacing-1-5)",
      }}
    >
      {children}
    </Text>
  );
}

function Ended({ reason, onRedial, onDismiss }: Props & { reason: keyof typeof endings }) {
  const ending = endings[reason];
  return (
    <VStack hAlign="center" gap={4} maxWidth="26em" role="alert">
      <Status struck>通话已结束</Status>
      <Heading level={3} style={{ textAlign: "center" }}>
        {ending.title}
      </Heading>
      <Text color="secondary" justify="center">
        {ending.body}
      </Text>
      <Text type="supporting" color="secondary" justify="center">
        {ending.counted ? "这次通话计入每小时的限额。" : "这次不计入每小时的限额。"}
      </Text>
      <HStack gap={3} wrap="wrap" hAlign="center">
        <Button label="回到对话" variant="secondary" onClick={onDismiss} />
        {ending.action ? (
          <Button label={ending.action.label} variant="primary" onClick={onDismiss} />
        ) : (
          <Button label="重拨" variant="primary" onClick={onRedial} />
        )}
      </HStack>
    </VStack>
  );
}

function Controls({ phase, micMuted, onToggleMute, onHangUp, onOpenMicPicker }: Props) {
  const live = phase.kind === "connected";
  return (
    <HStack hAlign="center" gap={8} paddingBlock={6}>
      <RoundControl
        label={micMuted ? "取消静音" : "麦克风静音"}
        icon={micMuted ? MicOffIcon : MicIcon}
        isPressed={micMuted}
        isDisabled={!live}
        onClick={onToggleMute}
      />
      <RoundControl label="挂断" icon={HangUpIcon} tone="danger" onClick={onHangUp} />
      <RoundControl label="切换麦克风" icon={MicSwitchIcon} isDisabled={!live} onClick={onOpenMicPicker} />
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
  icon: React.ComponentType<React.SVGProps<SVGSVGElement>>;
  tone?: "danger";
  isPressed?: boolean;
  isDisabled?: boolean;
  onClick: () => void;
}) {
  const size = "calc(var(--spacing-8) * 2)";
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
          width: size,
          height: size,
          borderRadius: "var(--radius-full)",
          ...(tone !== "danger" && {
            background: isPressed ? "var(--color-text-primary)" : "color-mix(in srgb, var(--color-text-primary) 16%, transparent)",
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
