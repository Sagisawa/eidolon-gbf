import { ApiError } from "@/lib/api";

/** An error to show on a page; `signedOut` adds a link to the sign-in page. */
export type Failure = { message: string; signedOut: boolean };

export function toFailure(e: unknown): Failure {
  return {
    message: (e as Error).message,
    signedOut: e instanceof ApiError && e.unauthorized,
  };
}
