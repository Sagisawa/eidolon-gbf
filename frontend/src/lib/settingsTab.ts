// Which tab of the settings page is open. Kept in the address (`?tab=`), so a refresh or a shared
// link opens the same group; a missing or unknown tab opens the profile.

export const SETTINGS_TABS = ["profile", "call", "own-keys", "sign-in"] as const;

export type SettingsTab = (typeof SETTINGS_TABS)[number];

const PARAM = "tab";

/** The tab the address names, or the profile when it names none we know. */
export function settingsTab(params: Pick<URLSearchParams, "get">): SettingsTab {
  const tab = params.get(PARAM);
  return SETTINGS_TABS.find((known) => known === tab) ?? "profile";
}

/** The query string (with its `?`) that opens `tab`, keeping the address's other parameters. */
export function settingsTabSearch(params: Pick<URLSearchParams, "toString">, tab: SettingsTab): string {
  const next = new URLSearchParams(params.toString());
  next.set(PARAM, tab);
  return `?${next}`;
}

/** A link straight to a tab of the settings page, e.g. from the call's end. */
export function settingsHref(tab: SettingsTab): string {
  return `/settings${settingsTabSearch(new URLSearchParams(), tab)}`;
}
