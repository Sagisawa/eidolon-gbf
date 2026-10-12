// Where the navigation shell's rules send the call (.scratch/app-navigation spec「外壳持有的东西」
// 「通话条」, ADR-0018): the conversations and settings share one shell, and the call belongs to
// it, not to her conversation page. Given a URL and whom the call under way is with (or no one),
// these say whether that URL is in the shell, whether the call bar shows across its top, and
// whether going there keeps the call, asks first and then hangs up, or just goes.

/** Going somewhere, with or without a call under way:
 * - `keep`: a page in the shell; the call goes on;
 * - `ask`: another character's conversation, or out of the shell; ask first, hang up if confirmed;
 * - `go`: no call under way; nothing to ask. */
export type Departure = "keep" | "ask" | "go";

/** The path of a URL, and whether it is on this site: the app links within itself by path, so
 * a URL with a host of its own is taken to be another site. */
function pathOf(href: string): { path: string; local: boolean } {
  const url = new URL(href, "http://shell.invalid");
  return { path: url.pathname, local: url.host === "shell.invalid" };
}

/** Whose conversation page this path is, or null if it is not one. */
function conversationOf(path: string): string | null {
  const match = /^\/conversation\/([^/]+)\/?$/.exec(path);
  return match ? decodeURIComponent(match[1]) : null;
}

/** The conversations (list and each character's page) and the settings are in the shell;
 * memories, the admin console, `/about`, the privacy policy, the terms, sign-in and consent
 * are out of it, and so is anything on another site. */
export function isInShell(href: string): boolean {
  const { path, local } = pathOf(href);
  if (!local) return false;
  return (
    path === "/conversations" ||
    conversationOf(path) !== null ||
    path === "/settings" ||
    path.startsWith("/settings/")
  );
}

/** The call bar across the top of the shell: while a call is under way, on a page in the shell
 * other than her own conversation page, which has its own bar under its header. Whether the
 * call layer is folded away is the caller's to add. */
export function showsShellCallBar(href: string, callee: string | null): boolean {
  if (callee === null || !isInShell(href)) return false;
  return conversationOf(pathOf(href).path) !== callee;
}

/** What going to `href` in this tab does to the call with `callee` (null for no call): one
 * character at a time, so another character's conversation asks, as does leaving the shell.
 * Links that open in a new tab never come here. */
export function departure(href: string, callee: string | null): Departure {
  if (callee === null) return "go";
  if (!isInShell(href)) return "ask";
  const other = conversationOf(pathOf(href).path);
  return other !== null && other !== callee ? "ask" : "keep";
}
