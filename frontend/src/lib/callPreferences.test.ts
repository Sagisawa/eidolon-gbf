import { afterEach, describe, expect, it, vi } from "vitest";
import { loadCallPreferences, saveCallPreferences } from "@/lib/callPreferences";

const KEY = "eidolon.callPreferences";

/** This browser's local storage, in memory. */
function storage(initial: Record<string, string> = {}) {
  const items = new Map(Object.entries(initial));
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
  });
  return items;
}

afterEach(() => vi.unstubAllGlobals());

describe("call preferences", () => {
  it("start on the system default microphone, standard quality, voice on", () => {
    storage();

    expect(loadCallPreferences()).toEqual({ micId: "", quality: "standard", muted: false });
  });

  it("remember the microphone chosen, keeping the rest", () => {
    storage();
    saveCallPreferences({ quality: "high" });

    saveCallPreferences({ micId: "usb" });

    expect(loadCallPreferences()).toEqual({ micId: "usb", quality: "high", muted: false });
  });

  it("fall back to the defaults for what is stored wrongly, keeping what is right", () => {
    storage({ [KEY]: JSON.stringify({ micId: 3, quality: "ultra", muted: true }) });

    expect(loadCallPreferences()).toEqual({ micId: "", quality: "standard", muted: true });
  });

  it("fall back to the defaults when what is stored cannot be read", () => {
    storage({ [KEY]: "{not json" });

    expect(loadCallPreferences()).toEqual({ micId: "", quality: "standard", muted: false });
  });

  it("go on without being remembered when storage is unavailable", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => {
        throw new DOMException("full", "QuotaExceededError");
      },
    });

    expect(saveCallPreferences({ micId: "usb" }).micId).toBe("usb");
  });
});
