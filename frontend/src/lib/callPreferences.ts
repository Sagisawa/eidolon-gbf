// How this device takes calls: microphone, call quality and the mute switch.
// Kept in this browser's local storage, like the access key.

export type Quality = "low" | "standard" | "high";

export const QUALITY_LABELS: Record<Quality, string> = {
  low: "省流量",
  standard: "标准",
  high: "高音质",
};

export type CallPreferences = {
  /** Microphone device id; empty for the system default. */
  micId: string;
  quality: Quality;
  /** Show the character's replies as text only, without playing her voice. */
  muted: boolean;
};

const STORAGE_KEY = "eidolon.callPreferences";
const DEFAULTS: CallPreferences = { micId: "", quality: "standard", muted: false };

export function loadCallPreferences(): CallPreferences {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    return {
      micId: typeof stored.micId === "string" ? stored.micId : DEFAULTS.micId,
      quality: stored.quality in QUALITY_LABELS ? stored.quality : DEFAULTS.quality,
      muted: typeof stored.muted === "boolean" ? stored.muted : DEFAULTS.muted,
    };
  } catch {
    return { ...DEFAULTS };
  }
}

export function saveCallPreferences(change: Partial<CallPreferences>): CallPreferences {
  const next = { ...loadCallPreferences(), ...change };
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    // Storage unavailable (e.g. private mode): the preference just won't be remembered.
  }
  return next;
}
