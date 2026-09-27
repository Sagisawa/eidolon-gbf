"use client";

import { Button } from "@astryxdesign/core/Button";
import { FormLayout } from "@astryxdesign/core/FormLayout";
import { Selector } from "@astryxdesign/core/Selector";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useEffect, useState } from "react";

import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import {
  loadCallPreferences,
  QUALITY_LABELS,
  saveCallPreferences,
  type CallPreferences,
  type Quality,
} from "@/lib/callPreferences";

const t = copy.settings.call;

/** Selector 的值不能是空字符串；「系统默认」的麦克风在选择框里用这个值代表，存下来仍是空白。 */
const SYSTEM_DEFAULT = "system-default";

async function listMics(): Promise<MediaDeviceInfo[]> {
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === "audioinput" && d.deviceId !== "default");
}

/** 麦克风和通话音质，记在这台设备上。 */
export function CallSettings() {
  const [preferences, setPreferences] = useState<CallPreferences | null>(null);
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);
  const [micError, setMicError] = useState("");

  useEffect(() => {
    setPreferences(loadCallPreferences());
    if (!navigator.mediaDevices?.enumerateDevices) return;
    listMics().then(setMics, () => {});
  }, []);

  // 页面获准使用麦克风之前，浏览器不给出麦克风的名称。
  const unnamed = mics.length > 0 && mics.every((m) => !m.label);

  async function allowMicrophone() {
    setMicError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      setMics(await listMics());
    } catch {
      setMicError(t.micDenied);
    }
  }

  function update(change: Partial<CallPreferences>) {
    setPreferences(saveCallPreferences(change));
  }

  if (!preferences) return null;
  return (
    <SettingsSection title={t.title}>
      <FormLayout>
        <VStack gap={2}>
          <Selector
            label={t.mic}
            description={t.micHint}
            value={preferences.micId || SYSTEM_DEFAULT}
            onChange={(value) => update({ micId: value === SYSTEM_DEFAULT ? "" : value })}
            options={[
              { value: SYSTEM_DEFAULT, label: t.micDefault },
              ...mics.map((mic, i) => ({ value: mic.deviceId, label: mic.label || t.micNumbered(i + 1) })),
            ]}
          />
          {(unnamed || micError) && (
            <VStack gap={2} hAlign="start">
              <Text type="supporting" as="p" role={micError ? "alert" : undefined}>
                {micError || t.micUnnamed}
              </Text>
              <Button label={t.micAllow} size="sm" onClick={allowMicrophone} />
            </VStack>
          )}
        </VStack>
        <Selector
          label={t.quality}
          description={t.qualityHint}
          value={preferences.quality}
          onChange={(value) => update({ quality: value as Quality })}
          options={(Object.keys(QUALITY_LABELS) as Quality[]).map((value) => ({ value, label: t.qualities[value] }))}
        />
      </FormLayout>
    </SettingsSection>
  );
}
