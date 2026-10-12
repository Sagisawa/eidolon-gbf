// The categories of the settings, each at a path of its own (.scratch/app-navigation spec
// 「设置：一级」「设置：网址」): `/settings` is the first level, the list of them; `/settings/<category>`
// is a category's page, the second level, with nothing below it. A refresh or a shared link opens
// the same category. The old addresses (`/settings?tab=…`, `/memories`) are sent to the new paths,
// and settings addresses we do not know to `/settings`.

/** The first level's groups, top to bottom, with a separator between each two. */
export const SETTINGS_GROUPS = [["profile", "memories"], ["call", "own-keys"], ["sign-in"], ["about"]] as const;

export const SETTINGS_CATEGORIES = SETTINGS_GROUPS.flat();

export type SettingsCategory = (typeof SETTINGS_CATEGORIES)[number];

const ROOT = "/settings";

function isCategory(name: string | null | undefined): name is SettingsCategory {
  return SETTINGS_CATEGORIES.some((known) => known === name);
}

/** A link straight to a category, e.g. from the call's end. */
export function settingsHref(category: SettingsCategory): string {
  return `${ROOT}/${category}`;
}

/** The category whose page the path is, or null for the first level and anything else. */
export function settingsCategory(path: string): SettingsCategory | null {
  const match = /^\/settings\/([^/]+)$/.exec(path);
  return match && isCategory(match[1]) ? match[1] : null;
}

/** The category on show beside the list on a desktop: the first level alone shows the profile. */
export function shownCategory(path: string): SettingsCategory {
  return settingsCategory(path) ?? "profile";
}

/** Where an old or unknown settings address goes instead (replacing it in the history), or null
 * if it is fine as it is. The address's other parameters stay. */
export function settingsRedirect(href: string): string | null {
  const url = new URL(href, "http://settings.invalid");
  const path = url.pathname;
  const params = url.searchParams;
  let to: string;
  if (path === "/memories") to = settingsHref("memories");
  else if (path === ROOT && params.has("tab")) {
    const tab = params.get("tab");
    params.delete("tab");
    to = isCategory(tab) ? settingsHref(tab) : ROOT;
  } else if (path.startsWith(`${ROOT}/`) && settingsCategory(path) === null) to = ROOT;
  else return null;
  const search = params.toString();
  return search ? `${to}?${search}` : to;
}
