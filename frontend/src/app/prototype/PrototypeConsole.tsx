import { BottomSheet } from "@astryxdesign/core/BottomSheet";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { Icon } from "@astryxdesign/core/Icon";
import { List, ListItem } from "@astryxdesign/core/List";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Switch } from "@astryxdesign/core/Switch";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useState } from "react";

import { type EndReason, endings } from "./call";
import { SlidersIcon } from "./icons";

export type Scenario = "idle" | "dialing" | "connected" | "ended";

type Props = {
  scenario: Scenario;
  reason: EndReason;
  collapsed: boolean;
  hearing: boolean;
  nearLimit: boolean;
  empty: boolean;
  onScenario: (s: Scenario) => void;
  onReason: (r: EndReason) => void;
  onCollapsed: (v: boolean) => void;
  onHearing: (v: boolean) => void;
  onNearLimit: (v: boolean) => void;
  onEmpty: (v: boolean) => void;
};

/** 原型专用：直接跳到任意一种状态。正式界面里没有它。 */
export function PrototypeConsole(p: Props) {
  const [open, setOpen] = useState(false);
  return (
    <>
      <Button
        label="原型控制台"
        icon={<Icon icon={SlidersIcon} />}
        variant="secondary"
        size="sm"
        elevation="low"
        onClick={() => setOpen(true)}
        style={{ position: "fixed", insetBlockEnd: "calc(var(--spacing-12) * 2.5)", insetInlineEnd: "var(--spacing-4)", zIndex: 50 }}
      />
      <BottomSheet isOpen={open} onOpenChange={setOpen} label="原型控制台" height="capped">
        <VStack gap={5} padding={5}>
          <Heading level={2}>原型控制台</Heading>
          <Text color="secondary">假数据。点通话键、发消息、挂断也都能直接操作。</Text>
          <SegmentedControl label="通话状态" value={p.scenario} onChange={(v) => p.onScenario(v as Scenario)} layout="fill">
            <SegmentedControlItem value="idle" label="没有通话" />
            <SegmentedControlItem value="dialing" label="拨打中" />
            <SegmentedControlItem value="connected" label="通话中" />
            <SegmentedControlItem value="ended" label="因故结束" />
          </SegmentedControl>
          {p.scenario === "ended" && (
            <List density="compact">
              {(Object.keys(endings) as EndReason[]).map((r) => (
                <ListItem
                  key={r}
                  label={endings[r].title}
                  description={endings[r].counted ? "计入限额" : "不计入限额"}
                  isSelected={p.reason === r}
                  onClick={() => p.onReason(r)}
                />
              ))}
            </List>
          )}
          <Switch label="通话层收起" value={p.collapsed} onChange={p.onCollapsed} labelSpacing="spread" />
          <Switch label="正在听用户说话" value={p.hearing} onChange={p.onHearing} labelSpacing="spread" />
          <Switch label="离时长上限不到 1 分钟" value={p.nearLimit} onChange={p.onNearLimit} labelSpacing="spread" />
          <Switch label="空对话" value={p.empty} onChange={p.onEmpty} labelSpacing="spread" />
        </VStack>
      </BottomSheet>
    </>
  );
}
