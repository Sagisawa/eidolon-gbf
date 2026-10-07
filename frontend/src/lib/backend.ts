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
