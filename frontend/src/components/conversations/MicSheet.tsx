"use client";

import { BottomSheet } from "@astryxdesign/core/BottomSheet";
import { Heading } from "@astryxdesign/core/Heading";
import { List, ListItem } from "@astryxdesign/core/List";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useEffect, useState } from "react";

import { copy } from "@/i18n";
import { listMicrophones } from "@/lib/microphone";
import { listRow } from "@/theme/herVars";

const t = copy.call.micSheet;

type Props = {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  /** 她的印象色：选中行铺她的 paper。 */
  color: string;
  /** 正在用的麦克风；空白是系统默认。 */
  micId: string;
  /** 选了另一个麦克风（空白是系统默认）。 */
  onSelect: (micId: string) => void;
};

/**
 * 通话中切换麦克风（DESIGN.md「BottomSheet」）：列出这台设备上的麦克风，当前这个标明「正在使用」，
 * 选中行铺她的 paper、次要字用 paperMuted。选中后当场换过去，也成为以后通话的默认麦克风。
 */
export function MicSheet({ isOpen, onOpenChange, color, micId, onSelect }: Props) {
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);

  // 每次打开都重新列一遍：通话中可能刚插上或拔掉了设备。
  useEffect(() => {
    if (!isOpen) return;
    let current = true;
    listMicrophones().then(
      (found) => current && setMics(found),
      () => {},
    );
    return () => {
      current = false;
    };
  }, [isOpen]);

  const choices = [
    { id: "", label: t.systemDefault },
    ...mics.map((mic, i) => ({ id: mic.deviceId, label: mic.label || t.numbered(i + 1) })),
  ];

  return (
    <BottomSheet isOpen={isOpen} onOpenChange={onOpenChange} label={t.title} height="hug">
      <VStack gap={3} padding={5}>
        <VStack gap={1}>
          <Heading level={2}>{t.title}</Heading>
          <Text type="supporting" color="secondary">
            {t.hint}
          </Text>
        </VStack>
        <List>
          {choices.map((choice) => {
            const inUse = choice.id === micId;
            return (
              <ListItem
                key={choice.id || "system-default"}
                label={choice.label}
                description={inUse ? t.inUse : undefined}
                isSelected={inUse}
                style={listRow(color, inUse)}
                onClick={() => {
                  onOpenChange(false);
                  if (!inUse) onSelect(choice.id);
                }}
              />
            );
          })}
        </List>
      </VStack>
    </BottomSheet>
  );
}
