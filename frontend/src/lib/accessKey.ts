// The user's access key lives only in this browser's local storage.

const STORAGE_KEY = "eidolon.accessKey";

export function loadAccessKey(): string {
  try {
    return localStorage.getItem(STORAGE_KEY) ?? "";
  } catch {
    return "";
  }
}

export function saveAccessKey(key: string): void {
  try {
    if (key) localStorage.setItem(STORAGE_KEY, key);
    else localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Storage unavailable (e.g. private mode): the key just won't be remembered.
  }
}
