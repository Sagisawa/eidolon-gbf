// The time zone this browser reports, sent with every request so that the
// character's "today" and "tonight" match the user's; a time zone set in the
// producer profile takes precedence on the backend.

export const FALLBACK_TIMEZONE = "Asia/Shanghai";

export function detectTimezone(): string {
  try {
    return Intl.DateTimeFormat().resolvedOptions().timeZone || FALLBACK_TIMEZONE;
  } catch {
    return FALLBACK_TIMEZONE;
  }
}

/** Every time zone this browser knows, for choosing one by hand. */
export function listTimezones(): string[] {
  try {
    return Intl.supportedValuesOf("timeZone");
  } catch {
    return [FALLBACK_TIMEZONE];
  }
}
