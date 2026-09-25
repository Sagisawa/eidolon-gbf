"use client";

import { useEffect, useState } from "react";
import {
  loadCallPreferences,
  QUALITY_LABELS,
  saveCallPreferences,
  type CallPreferences,
  type Quality,
} from "@/lib/callPreferences";

async function listMics(): Promise<MediaDeviceInfo[]> {
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === "audioinput" && d.deviceId !== "default");
}

/** Microphone and call quality, remembered on this device. */
export function CallSettings() {
  const [preferences, setPreferences] = useState<CallPreferences | null>(null);
  const [mics, setMics] = useState<MediaDeviceInfo[]>([]);
  const [micError, setMicError] = useState("");

  useEffect(() => {
    setPreferences(loadCallPreferences());
    if (!navigator.mediaDevices?.enumerateDevices) return;
    listMics().then(setMics, () => {});
  }, []);

  // Browsers only name the microphones once the page may use one.
  const unnamed = mics.length > 0 && mics.every((m) => !m.label);

  async function allowMicrophone() {
    setMicError("");
    try {
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
      stream.getTracks().forEach((track) => track.stop());
      setMics(await listMics());
    } catch {
      setMicError("没有获得麦克风权限，请在浏览器设置中允许后重试");
    }
  }

  function update(change: Partial<CallPreferences>) {
    setPreferences(saveCallPreferences(change));
  }

  if (!preferences) return null;
  return (
    <>
      <div className="field">
        <label htmlFor="mic">麦克风</label>
        <p className="hint">语音通话时使用的麦克风。</p>
        <select id="mic" value={preferences.micId} onChange={(e) => update({ micId: e.target.value })}>
          <option value="">系统默认</option>
          {mics.map((mic, i) => (
            <option key={mic.deviceId} value={mic.deviceId}>
              {mic.label || `麦克风 ${i + 1}`}
            </option>
          ))}
        </select>
        {(unnamed || micError) && (
          <p className="hint">
            {micError || "浏览器还没有允许本页使用麦克风，因此看不到名称。"}{" "}
            <button type="button" className="ghost" onClick={allowMicrophone}>
              允许使用麦克风
            </button>
          </p>
        )}
      </div>

      <div className="field">
        <label htmlFor="quality">通话音质</label>
        <p className="hint">角色语音的音质；网络不好或想省流量时选低一些。下次接通时生效。</p>
        <select
          id="quality"
          value={preferences.quality}
          onChange={(e) => update({ quality: e.target.value as Quality })}
        >
          {Object.entries(QUALITY_LABELS).map(([value, label]) => (
            <option key={value} value={value}>
              {label}
            </option>
          ))}
        </select>
      </div>
    </>
  );
}
