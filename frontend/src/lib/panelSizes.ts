// How wide the conversation list is and how tall the message input rests on this device's
// wide screen, as the producer last dragged them. Kept in this browser's local storage.

export type Panel = "list" | "composer";

const STORAGE_KEY = "eidolon.panelSizes";

function loadAll(): Partial<Record<Panel, unknown>> {
  try {
    const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "{}");
    return typeof stored === "object" && stored !== null ? stored : {};
  } catch {
    return {};
  }
}

/** The size last dragged to, in pixels; null when never dragged or stored wrongly. */
export function loadPanelSize(panel: Panel): number | null {
  const size = loadAll()[panel];
  return typeof size === "number" && Number.isFinite(size) && size > 0 ? size : null;
}

export function savePanelSize(panel: Panel, size: number): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify({ ...loadAll(), [panel]: Math.round(size) }));
  } catch {
    // Storage unavailable (e.g. private mode): the size just won't be remembered.
  }
}
