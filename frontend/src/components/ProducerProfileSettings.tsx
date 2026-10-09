"use client";

import { FormEvent, useEffect, useId, useMemo, useState } from "react";

import { FailureNotice } from "@/components/app/FailureNotice";
import { SettingsSection } from "@/components/app/SettingsSection";
import { Button } from "@/components/ui/button";
import {
  Combobox,
  ComboboxContent,
  ComboboxInput,
  ComboboxItem,
  ComboboxList,
  ComboboxSelectTrigger,
} from "@/components/ui/combobox";
import { Field, FieldDescription, FieldGroup, FieldLabel } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Spinner } from "@/components/ui/spinner";
import { copy } from "@/i18n";
import { getProfile, saveProfile, type Gender } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { clampFormOfAddress, fromDraft, sameDraft, toDraft, type Draft } from "@/lib/producerProfile";
import { detectTimezone, listTimezones } from "@/lib/timezone";

const t = copy.settings.profile;

/** 「沿用默认」在选择框里用这个值代表（选择框的值不用空字符串），草稿里仍是空白。 */
const DEFAULT = "default";

/** 制作人档案：存在后端、跟着用户走，所有设备共用。 */
export function ProducerProfileSettings() {
  const [saved, setSaved] = useState<Draft | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [saving, setSaving] = useState(false);
  const [detected, setDetected] = useState("");
  const [timezones, setTimezones] = useState<string[]>([]);
  const id = useId();

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
      ...(draft?.timezone && !timezones.includes(draft.timezone) ? [draft.timezone] : []).map(asOption),
      ...timezones.map(asOption),
    ],
    [detected, draft?.timezone, timezones],
  );
  const timezoneLabels = useMemo(
    () => new Map(timezoneOptions.map((option) => [option.value, option.label])),
    [timezoneOptions],
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
        {failure ? (
          <FailureNotice failure={failure} />
        ) : (
          <p className="text-body text-muted-foreground">{copy.settings.loading}</p>
        )}
      </SettingsSection>
    );
  }

  const update = (change: Partial<Draft>) => setDraft({ ...draft, ...change });
  const dirty = !sameDraft(draft, saved);
  const genderOptions = [
    { value: DEFAULT, label: t.genderDefault },
    { value: "male", label: t.male },
    { value: "female", label: t.female },
  ];

  return (
    <SettingsSection title={t.title}>
      <form onSubmit={submit}>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor={`${id}-address`}>{t.formOfAddress}</FieldLabel>
            <Input
              id={`${id}-address`}
              value={draft.formOfAddress}
              onChange={(event) => update({ formOfAddress: clampFormOfAddress(event.target.value) })}
              placeholder={t.formOfAddressPlaceholder}
              autoComplete="off"
            />
            <FieldDescription>{t.formOfAddressHint}</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor={`${id}-gender`}>{t.gender}</FieldLabel>
            <Select
              items={genderOptions}
              value={draft.gender || DEFAULT}
              onValueChange={(value) => update({ gender: value === DEFAULT || !value ? "" : (value as Gender) })}
            >
              <SelectTrigger id={`${id}-gender`} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {genderOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <FieldDescription>{t.genderHint}</FieldDescription>
          </Field>

          <Field>
            <FieldLabel htmlFor={`${id}-timezone`}>{t.timezone}</FieldLabel>
            <Combobox
              items={timezoneOptions.map((option) => option.value)}
              itemToStringLabel={(value: string) => timezoneLabels.get(value) ?? value}
              value={draft.timezone || DEFAULT}
              onValueChange={(value) => update({ timezone: value === DEFAULT || !value ? "" : value })}
            >
              <ComboboxSelectTrigger id={`${id}-timezone`} className="w-full" />
              <ComboboxContent>
                <ComboboxInput showTrigger={false} placeholder={t.timezoneSearch} />
                <ComboboxList>
                  {(value: string) => (
                    <ComboboxItem key={value} value={value}>
                      {timezoneLabels.get(value) ?? value}
                    </ComboboxItem>
                  )}
                </ComboboxList>
              </ComboboxContent>
            </Combobox>
            <FieldDescription>{t.timezoneHint}</FieldDescription>
          </Field>

          {failure && <FailureNotice failure={failure} />}

          <div className="flex flex-wrap items-center gap-3">
            <Button type="submit" disabled={!dirty || saving}>
              {saving && <Spinner data-icon="inline-start" />}
              {t.save}
            </Button>
            <p role="status" className="text-subtitle text-muted-foreground">
              {dirty ? t.unsaved : t.saved}
            </p>
          </div>
        </FieldGroup>
      </form>
    </SettingsSection>
  );
}

function asOption(zone: string) {
  return { value: zone, label: zone };
}
