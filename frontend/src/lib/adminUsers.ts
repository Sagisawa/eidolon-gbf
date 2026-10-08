// The admin console's users page (ADR-0013): listing and searching users, a user's details,
// banning or unbanning them, setting their own limits, and deleting them. The backend never sends what anyone said,
// what was remembered of them or their producer profile, only who they are and how they
// use it.

import type { TableSortState } from "@astryxdesign/core/Table";

import { copy } from "@/i18n";
import { apiHeaders, expectNoContent, followRedirect, json, type OwnService } from "@/lib/api";
import { formatCount } from "@/lib/dashboard";
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
  /** The turns and calls taken in the last 24 hours, rejected ones not counted. */
  usage_24h: { turns: number; calls: number };
};

/** How many, on the deployer's keys and on the user's own. */
export type KeyedCount = { deployer: number; own_keys: number };

/** What a user did in one range: the turns (those in calls too) and calls they took, and
 * the turns and calls rejected, which are counted only as rejected. */
export type RangeUsage = { turns: KeyedCount; calls: KeyedCount; rejected: KeyedCount };

export const USAGE_RANGES = ["24h", "7d", "30d"] as const;
export type UsageRange = (typeof USAGE_RANGES)[number];

/** A user's recent usage, from the activity records, for each range. */
export type AdminUserUsage = Record<UsageRange, RangeUsage>;

/** How the list is sorted: newest first, or by the last 24 hours' turns or calls, most first. */
export const USER_SORTS = ["newest", "turns", "calls"] as const;
export type UserSort = (typeof USER_SORTS)[number];

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

/** A user's own page adds when they were banned, the note only admins see, and their
 * recent usage. */
export type AdminUserDetails = AdminUser & {
  banned_at: string | null;
  ban_note: string | null;
  usage: AdminUserUsage;
};

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

/** The list's sort from the table's: a usage column's header sorts by it, most first,
 * whichever way the header was clicked (the backend sorts only that way); none, newest. */
export function userSort(state: TableSortState): UserSort {
  const key = state[0]?.sortKey;
  return key === "turns" || key === "calls" ? key : "newest";
}

/** The table's sort state showing the list's sort, so that clicking a sorted column's
 * header again takes the sort off. */
export function sortState(sort: UserSort): TableSortState {
  return sort === "newest" ? [] : [{ sortKey: sort, direction: "descending" }];
}

/** A count as the usage section shows it: the total, and below it on whose keys, for
 * any at all. */
export function describeCount(count: KeyedCount): { total: string; split: string | null } {
  const total = count.deployer + count.own_keys;
  return {
    total: formatCount(total),
    split:
      total === 0 ? null : copy.admin.users.usage.split(formatCount(count.deployer), formatCount(count.own_keys)),
  };
}

export type UsageRow = { what: keyof RangeUsage; label: string } & Record<UsageRange, KeyedCount>;

/** The usage section's rows: turns, calls and rejections, each across the ranges. */
export function usageRows(usage: AdminUserUsage): UsageRow[] {
  const labels = copy.admin.users.usage.rows;
  return (["turns", "calls", "rejected"] as const).map((what) => ({
    what,
    label: labels[what],
    "24h": usage["24h"][what],
    "7d": usage["7d"][what],
    "30d": usage["30d"][what],
  }));
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

/** A page of the users, or of those `query` finds by name, email or user id, sorted by
 * `sort` before they are cut into pages. */
export async function listAdminUsers(query: string, page: number, sort: UserSort): Promise<AdminUserPage> {
  const params = new URLSearchParams({
    q: query,
    offset: String(pageOffset(page)),
    limit: String(USERS_PAGE_SIZE),
    sort,
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
