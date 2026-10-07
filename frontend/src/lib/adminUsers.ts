// The admin console's users page (ADR-0013): listing and searching users, a user's details,
// banning or unbanning them, setting their own limits, and deleting them. The backend never sends what anyone said,
// what was remembered of them or their producer profile, only who they are and how they
// use it.

import { copy } from "@/i18n";
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
  limits: AdminUserLimits | null;
};

/** A user's own limit an hour: a number (0: on their own keys only), unlimited, or null,
 * the deployment's. */
export type UserLimit = number | "unlimited" | null;

/** The limits an admin set for the user, each apart, with a note for the admins. */
export type AdminUserLimits = {
  turns_per_hour: UserLimit;
  calls_per_hour: UserLimit;
  note: string | null;
  updated_at: string;
};

/** One limit as the editor holds it: which kind, and the number typed for "number". */
export type LimitDraft = { choice: "default" | "number" | "unlimited"; count: number | null };

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

/** What a user's own limit is, in words. */
export function describeLimit(limit: UserLimit): string {
  const t = copy.admin.users.limits;
  if (limit === null) return t.default;
  if (limit === "unlimited") return t.unlimited;
  return limit === 0 ? t.ownKeysOnly : t.perHour(limit);
}

/** The editor's starting point for a limit the user has. */
export function limitDraft(limit: UserLimit): LimitDraft {
  if (limit === null) return { choice: "default", count: null };
  if (limit === "unlimited") return { choice: "unlimited", count: null };
  return { choice: "number", count: limit };
}

/** The limits to save from the editor; null while there is nothing to save: both follow
 * the deployment, or a number is chosen but none given. */
export function limitsInput(
  turns: LimitDraft,
  calls: LimitDraft,
): { turns_per_hour: UserLimit; calls_per_hour: UserLimit } | null {
  const limit = (draft: LimitDraft): UserLimit | undefined =>
    draft.choice === "default" ? null : draft.choice === "unlimited" ? "unlimited" : (draft.count ?? undefined);
  const [turnsPerHour, callsPerHour] = [limit(turns), limit(calls)];
  if (turnsPerHour === undefined || callsPerHour === undefined) return null;
  if (turnsPerHour === null && callsPerHour === null) return null;
  return { turns_per_hour: turnsPerHour, calls_per_hour: callsPerHour };
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

/** Set the user's own limits, replacing those they had, from their next turn or call on. */
export async function setUserLimits(
  id: string,
  limits: { turns_per_hour: UserLimit; calls_per_hour: UserLimit },
  note: string,
): Promise<AdminUserDetails> {
  return json(
    await admin(`/api/admin/users/${encodeURIComponent(id)}/limits`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ ...limits, note: note.trim() || null }),
    }),
  );
}

/** Take off the user's own limits; the deployment's hold for them again. */
export async function takeOffUserLimits(id: string): Promise<AdminUserDetails> {
  return json(await admin(`/api/admin/users/${encodeURIComponent(id)}/limits`, { method: "DELETE" }));
}

/** Delete the user and all their data for good, as they would themselves; a banned user's
 * identities can never sign in or be linked again. */
export async function deleteUser(id: string): Promise<void> {
  await expectNoContent(await admin(`/api/admin/users/${encodeURIComponent(id)}`, { method: "DELETE" }));
}
