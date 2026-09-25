import { ApiError } from "@/lib/api";

/** An error to show on a page; `needsKey` adds a link to the settings page. */
export type Failure = { message: string; needsKey: boolean };

export function toFailure(e: unknown): Failure {
  return {
    message: (e as Error).message,
    needsKey: e instanceof ApiError && e.unauthorized,
  };
}
