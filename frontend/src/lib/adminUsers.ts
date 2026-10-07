// The admin console's users page (ADR-0013): listing and searching users, a user's details,
// banning or unbanning them, and deleting them. The backend never sends what anyone said,
// what was remembered of them or their producer profile, only who they are and how they
// use it.

import { apiHeaders, expectNoContent, followRedirect, json, type OwnService } from "@/lib/api";
import type { Provider } from "@/lib/signIn";

/** An identity a user signs in with; `subject` is what `EIDOLON_ADMINS` names it by. */
export type AdminSignInMethod = {
  provider: Provider;
  subject: string;
  display_name: string;
  email: string | null;
};

/** A user as the list shows them. `last_active_at` is null for a user signed in nowhere;
 * `own_keys` says only whether they brought their own key for each service. */
export type AdminUser = {
  id: string;
  name: string;
  sign_in_methods: AdminSignInMethod[];
  created_at: string;
  last_active_at: string | null;
  banned: boolean;
  is_admin: boolean;
  own_keys: Record<OwnService, boolean>;
};

/** A user's own page adds when they were banned and the note only admins see. */
export type AdminUserDetails = AdminUser & { banned_at: string | null; ban_note: string | null };

export type AdminUserPage = { users: AdminUser[]; total: number };

export const USERS_PAGE_SIZE = 50;

const OWN_SERVICES: OwnService[] = ["llm", "tts", "stt"];

/** What an admin can do about the user from the users page: ban them, lift their ban, or
 * nothing, for an admin, who cannot be banned in the admin console. */
export function banAction(user: AdminUser): "ban" | "unban" | null {
  if (user.is_admin) return null;
  return user.banned ? "unban" : "ban";
}

/** The services the user brought their own keys for. */
export function broughtKeys(ownKeys: Record<OwnService, boolean>): OwnService[] {
  return OWN_SERVICES.filter((service) => ownKeys[service]);
}

/** How many users the pages before `page` (counted from 1) hold. */
export function pageOffset(page: number): number {
  return (page - 1) * USERS_PAGE_SIZE;
}

async function admin(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(path, { ...init, headers: apiHeaders(init.headers) });
  followRedirect(res);
  return res;
}

/** A page of the users, newest first, or of those `query` finds by name, email or user id. */
export async function listAdminUsers(query: string, page: number): Promise<AdminUserPage> {
  const params = new URLSearchParams({
    q: query,
    offset: String(pageOffset(page)),
    limit: String(USERS_PAGE_SIZE),
  });
  return json(await admin(`/api/admin/users?${params}`));
}

export async function getAdminUser(id: string): Promise<AdminUserDetails> {
  return json(await admin(`/api/admin/users/${encodeURIComponent(id)}`));
}

/** Ban the user, with a note for the admins; they are signed out everywhere at once. */
export async function banUser(id: string, note: string): Promise<AdminUserDetails> {
  return json(
    await admin(`/api/admin/users/${encodeURIComponent(id)}/ban`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ note: note.trim() || null }),
    }),
  );
}

export async function unbanUser(id: string): Promise<AdminUserDetails> {
  return json(await admin(`/api/admin/users/${encodeURIComponent(id)}/ban`, { method: "DELETE" }));
}

/** Delete the user and all their data for good, as they would themselves; a banned user's
 * identities can never sign in or be linked again. */
export async function deleteUser(id: string): Promise<void> {
  await expectNoContent(await admin(`/api/admin/users/${encodeURIComponent(id)}`, { method: "DELETE" }));
}
