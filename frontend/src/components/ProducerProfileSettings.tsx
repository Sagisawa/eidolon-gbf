"use client";

import { FormEvent, useEffect, useMemo, useState } from "react";
import { getProfile, saveProfile, type Gender, type ProducerProfile } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { FailureNotice } from "@/components/FailureNotice";
import { detectTimezone, listTimezones } from "@/lib/timezone";

/** Same as the backend's MAX_FORM_OF_ADDRESS_LENGTH. */
const MAX_FORM_OF_ADDRESS = 20;

type Draft = { formOfAddress: string; gender: Gender | ""; timezone: string };

function toDraft(profile: ProducerProfile): Draft {
  return {
    formOfAddress: profile.form_of_address ?? "",
    gender: profile.gender ?? "",
    timezone: profile.timezone ?? "",
  };
}

function sameDraft(a: Draft, b: Draft): boolean {
  return (
    a.formOfAddress.trim() === b.formOfAddress.trim() &&
    a.gender === b.gender &&
    a.timezone === b.timezone
  );
}

/** The producer profile: kept on the backend with the user, so every device shares it. */
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

  // A time zone saved on another device may be unknown to this browser; keep it choosable.
  const timezoneOptions = useMemo(
    () =>
      draft?.timezone && !timezones.includes(draft.timezone)
        ? [draft.timezone, ...timezones]
        : timezones,
    [draft?.timezone, timezones],
  );

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!draft) return;
    setSaving(true);
    setFailure(null);
    try {
      const profile = await saveProfile({
        form_of_address: draft.formOfAddress.trim() || null,
        gender: draft.gender || null,
        timezone: draft.timezone || null,
      });
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
      <div className="field">
        <label>制作人档案</label>
        {failure ? <FailureNotice failure={failure} /> : <p className="hint">正在读取…</p>}
      </div>
    );
  }

  const update = (change: Partial<Draft>) => setDraft({ ...draft, ...change });
  const dirty = !sameDraft(draft, saved);

  return (
    <form onSubmit={submit}>
      <div className="field">
        <label htmlFor="form-of-address">称呼</label>
        <p className="hint">
          角色对你的叫法，只改变叫法，你仍然是她们的制作人。留空时，角色按各自的习惯称呼你。
        </p>
        <div className="field-row">
          <input
            id="form-of-address"
            value={draft.formOfAddress}
            onChange={(e) => update({ formOfAddress: e.target.value })}
            maxLength={MAX_FORM_OF_ADDRESS}
            placeholder="例如：小林さん"
            autoComplete="off"
          />
        </div>
      </div>

      <div className="field">
        <label htmlFor="gender">性别</label>
        <p className="hint">只影响角色现在怎么对待你，不会改写她们回忆中的原作剧情。</p>
        <select
          id="gender"
          value={draft.gender}
          onChange={(e) => update({ gender: e.target.value as Gender | "" })}
        >
          <option value="">沿用原作设定（男性）</option>
          <option value="male">男性</option>
          <option value="female">女性</option>
        </select>
      </div>

      <div className="field">
        <label htmlFor="timezone">时区</label>
        <p className="hint">
          角色口中的「今天」「今晚」按这个时区计算。自动时使用当前设备检测到的时区。
        </p>
        <select
          id="timezone"
          value={draft.timezone}
          onChange={(e) => update({ timezone: e.target.value })}
        >
          <option value="">自动（{detected || "当前设备的时区"}）</option>
          {timezoneOptions.map((zone) => (
            <option key={zone} value={zone}>
              {zone}
            </option>
          ))}
        </select>
      </div>

      <div className="field">
        {failure && <FailureNotice failure={failure} />}
        <div className="field-row">
          <button type="submit" disabled={!dirty || saving}>
            {saving ? "正在保存…" : "保存档案"}
          </button>
        </div>
        <p className="hint" role="status">
          {dirty ? "尚未保存" : "已保存，所有设备共用这份档案"}
        </p>
      </div>
    </form>
  );
}
