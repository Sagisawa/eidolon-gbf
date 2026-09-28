"use client";

import { Button } from "@astryxdesign/core/Button";
import { FormLayout } from "@astryxdesign/core/FormLayout";
import { HStack } from "@astryxdesign/core/HStack";
import { Selector } from "@astryxdesign/core/Selector";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { FormEvent, useEffect, useMemo, useState } from "react";

import { FailureNotice } from "@/components/FailureNotice";
import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import { getProfile, saveProfile, type Gender } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { clampFormOfAddress, fromDraft, sameDraft, toDraft, type Draft } from "@/lib/producerProfile";
import { detectTimezone, listTimezones } from "@/lib/timezone";

const t = copy.settings.profile;

/** Selector 的值不能是空字符串；「沿用默认」在选择框里用这个值代表，草稿里仍是空白。 */
const DEFAULT = "default";

/** 制作人档案：存在后端、跟着用户走，所有设备共用。 */
export function ProducerProfileSettings() {
  const [saved, setSaved] = useState<Draft | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [saving, setSaving] = useState(false);
  const [detected, setDetected] = useState("");
  const [timezones, setTimezones] = useState<string[]>([]);

  useEffect(() => {
    setDetected(detectTimezone());
    setTimezones(listTimezones());
  }, []);

  useEffect(() => {
    let current = true;
    getProfile().then(
      (profile) => {
        if (!current) return;
        setSaved(toDraft(profile));
        setDraft(toDraft(profile));
      },
      (e) => current && setFailure(toFailure(e)),
    );
    return () => {
      current = false;
    };
  }, []);

  // 别的设备上存的时区，这个浏览器可能不认识；照样放进选项里。
  const timezoneOptions = useMemo(
    () => [
      { value: DEFAULT, label: t.timezoneAuto(detected || t.timezoneUnknown) },
      ...(draft?.timezone && !timezones.includes(draft.timezone) ? [draft.timezone] : []),
      ...timezones,
    ],
    [detected, draft?.timezone, timezones],
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setSaving(true);
    setFailure(null);
    try {
      const profile = await saveProfile(fromDraft(draft));
      setSaved(toDraft(profile));
      setDraft(toDraft(profile));
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setSaving(false);
    }
  }

  if (!draft || !saved) {
    return (
      <SettingsSection title={t.title}>
        {failure ? <FailureNotice failure={failure} /> : <Text color="secondary">{copy.settings.loading}</Text>}
      </SettingsSection>
    );
  }

  const update = (change: Partial<Draft>) => setDraft({ ...draft, ...change });
  const dirty = !sameDraft(draft, saved);

  return (
    <SettingsSection title={t.title}>
      <form onSubmit={submit}>
        <FormLayout>
          <TextInput
            label={t.formOfAddress}
            description={t.formOfAddressHint}
            value={draft.formOfAddress}
            onChange={(value) => update({ formOfAddress: clampFormOfAddress(value) })}
            placeholder={t.formOfAddressPlaceholder}
            autoComplete="off"
          />
          <Selector
            label={t.gender}
            description={t.genderHint}
            value={draft.gender || DEFAULT}
            onChange={(value) => update({ gender: value === DEFAULT ? "" : (value as Gender) })}
            options={[
              { value: DEFAULT, label: t.genderDefault },
              { value: "male", label: t.male },
              { value: "female", label: t.female },
            ]}
          />
          <Selector
            label={t.timezone}
            description={t.timezoneHint}
            value={draft.timezone || DEFAULT}
            onChange={(value) => update({ timezone: value === DEFAULT ? "" : value })}
            options={timezoneOptions}
            hasSearch
            searchPlaceholder={t.timezoneSearch}
          />
          {failure && <FailureNotice failure={failure} />}
          <HStack gap={3} vAlign="center" wrap="wrap">
            <Button type="submit" variant="primary" label={t.save} isDisabled={!dirty} isLoading={saving} />
            <Text type="supporting" role="status">
              {dirty ? t.unsaved : t.saved}
            </Text>
          </HStack>
        </FormLayout>
      </form>
    </SettingsSection>
  );
}
