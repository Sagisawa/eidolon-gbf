// Server side only: where the backend is, for the API proxy and the server components
// that ask the backend before rendering.

export const BACKEND_URL = process.env.BACKEND_URL ?? "http://localhost:8000";

/** The admin console's front door, asked with the browser's cookies: the admin, or null
 * when the backend says there is no admin console for this browser (404). */
export async function getAdmin(cookie: string): Promise<{ name: string } | null> {
  const res = await fetch(`${BACKEND_URL}/api/admin`, { headers: { cookie }, cache: "no-store" });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`后台接口出错（${res.status}）`);
  return res.json();
}

/** The cookie the backend keeps a browser's session in (`SESSION_COOKIE` in `sessions.py`). */
const SESSION_COOKIE = "eidolon_session";

/** Whether the browser whose cookies these are has a live session. A browser without a session
 * cookie, a visitor, is told no without asking the backend; one whose session has expired or
 * ended, or that the backend cannot answer for, is not either. A user yet to agree to the terms
 * is signed in (the backend answers 428). */
export async function isSignedIn(cookie: string): Promise<boolean> {
  if (!cookie.split(/;\s*/).some((pair) => pair.startsWith(`${SESSION_COOKIE}=`))) return false;
  try {
    const res = await fetch(`${BACKEND_URL}/api/account`, { headers: { cookie }, cache: "no-store" });
    return res.ok || res.status === 428;
  } catch {
    return false;
  }
}
