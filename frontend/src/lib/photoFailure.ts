// What the note in place of a photo not sent says (GLOSSARY.md「照片」, DESIGN.md「Chat bubbles ·
// 照片」): why, as the backend names it (`store.PhotoFailure`), in a few words; where the user's
// own image key failed, a link to set their own keys as well.

import { copy } from "@/i18n";

const reasons = copy.conversation.photo.reasons;

/** Why a photo was not sent: the backend's `store.PhotoFailure`. */
export type PhotoFailure = keyof typeof reasons;

function isPhotoFailure(reason: string): reason is PhotoFailure {
  return Object.hasOwn(reasons, reason);
}

/**
 * The note's line on why the photo was not sent, and whether it links to the own keys' settings; a
 * reason it does not know, or none, is told as the image service failing.
 */
export function photoFailureNote(reason: string | null): { reason: string; toOwnKeys: boolean } {
  const failure: PhotoFailure = reason !== null && isPhotoFailure(reason) ? reason : "service_error";
  return { reason: reasons[failure], toOwnKeys: failure === "own_key_failed" };
}
