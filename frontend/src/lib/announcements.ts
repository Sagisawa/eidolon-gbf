// Announcements (GLOSSARY.md「公告」): what admins write in the admin console for every user
// to see. Only a body, in Markdown, with no title and no author; written as a draft, then
// published, withdrawn or deleted. Editing a published one keeps when it was published;
// withdrawing it and publishing it again makes it new.

import { api, expectNoContent, json } from "@/lib/api";

/** The most characters a body may have, as the backend allows. */
export const MAX_BODY = 5000;

export type AnnouncementStatus = "draft" | "published";

/** An announcement as admins see it. `published_at` is null while a draft. */
export type AdminAnnouncement = {
  id: string;
  body: string;
  status: AnnouncementStatus;
  published_at: string | null;
  created_at: string;
  /** When its body was last written. */
  updated_at: string;
};

/** An announcement as users see it: published, and nothing of who wrote it. */
export type Announcement = { id: string; body: string; published_at: string };

/** Every announcement, drafts first (last written first), then the latest published. */
export async function listAdminAnnouncements(): Promise<AdminAnnouncement[]> {
  return json(await api("/api/admin/announcements"));
}

export async function getAdminAnnouncement(id: string): Promise<AdminAnnouncement> {
  return json(await api(`/api/admin/announcements/${encodeURIComponent(id)}`));
}

/** A new draft of `body`; refused if it is empty or too long. */
export async function writeAnnouncement(body: string): Promise<AdminAnnouncement> {
  return json(
    await api("/api/admin/announcements", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body }),
    }),
  );
}

/** Replace its body; a published one stays published as of when it was. */
export async function editAnnouncement(id: string, body: string): Promise<AdminAnnouncement> {
  return json(
    await api(`/api/admin/announcements/${encodeURIComponent(id)}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ body }),
    }),
  );
}

/** Publish it now, for every user to see. */
export async function publishAnnouncement(id: string): Promise<AdminAnnouncement> {
  return json(await api(`/api/admin/announcements/${encodeURIComponent(id)}/publish`, { method: "POST" }));
}

/** Make it a draft again; published again later, it is new. */
export async function withdrawAnnouncement(id: string): Promise<AdminAnnouncement> {
  return json(await api(`/api/admin/announcements/${encodeURIComponent(id)}/publish`, { method: "DELETE" }));
}

export async function deleteAnnouncement(id: string): Promise<void> {
  await expectNoContent(await api(`/api/admin/announcements/${encodeURIComponent(id)}`, { method: "DELETE" }));
}

/** The latest announcements published, newest first. */
export async function listAnnouncements(): Promise<Announcement[]> {
  return json(await api("/api/announcements"));
}

/** How many characters of a body the admin console's list shows. */
export const EXCERPT_LENGTH = 40;

/**
 * The start of a body as plain text, for telling announcements apart where they have no
 * title: the Markdown marks dropped (the words of links, images and code kept), every run
 * of whitespace one space, and cut at `EXCERPT_LENGTH` characters with an ellipsis.
 */
export function excerpt(body: string): string {
  const text = body
    .replace(/^[ \t]*(?:[-*+]|\d+[.)]|#{1,6}|>)[ \t]+/gm, "")
    .replace(/!?\[([^\]]*)\]\([^)]*\)/g, "$1")
    .replace(/[*_`~]/g, "")
    .replace(/\s+/g, " ")
    .trim();
  const chars = Array.from(text);
  return chars.length > EXCERPT_LENGTH ? `${chars.slice(0, EXCERPT_LENGTH).join("")}…` : text;
}
