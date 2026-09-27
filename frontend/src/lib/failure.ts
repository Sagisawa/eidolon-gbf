import { ApiError } from "@/lib/api";

/** An error to show on a page; `signedOut` adds a link to the sign-in page.
 * `countsTowardLimit` is set when it is known whether what failed still counts towards the
 * hourly limit (CONTEXT.md「限额」); left out when it is not known or does not apply. */
export type Failure = { message: string; signedOut: boolean; countsTowardLimit?: boolean };

export function toFailure(e: unknown): Failure {
  return {
    message: (e as Error).message,
    signedOut: e instanceof ApiError && e.unauthorized,
  };
}
