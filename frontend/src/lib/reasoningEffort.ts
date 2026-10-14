// 思考强度（GLOSSARY.md「思考强度」）和额外请求参数：后台的模型和设置页的自带 LLM 共用这一份。
// 档位按接口原样发给服务，服务不支持时保存或检查时报错（ADR-0019），所以这里只管接口写得出哪些档。

/** The efforts, as the backend's `config.REASONING_EFFORTS` has them, in order. */
export const REASONING_EFFORTS = ["none", "minimal", "low", "medium", "high", "xhigh", "max"] as const;

export type ReasoningEffort = (typeof REASONING_EFFORTS)[number];

/** In a form, no effort: nothing is sent, the model's own default holds. */
export const EFFORT_UNSET = "unset";

/** The efforts `protocol` has a way to write: the Anthropic protocol has no minimal. */
export function effortsFor(protocol: string): ReasoningEffort[] {
  return REASONING_EFFORTS.filter((effort) => !(protocol === "anthropic" && effort === "minimal"));
}

/** A model's effort choices in a form, unset first. */
export function effortChoices(protocol: string): string[] {
  return [EFFORT_UNSET, ...effortsFor(protocol)];
}

/** The effort a form's choice sends: null when unset, undefined when `protocol` cannot write it. */
export function effortOf(choice: string, protocol: string): ReasoningEffort | null | undefined {
  if (choice === EFFORT_UNSET) return null;
  return effortsFor(protocol).find((effort) => effort === choice);
}

export type JsonObject = { [key: string]: unknown };

/** An extra request body as typed in: empty for none, else what keeps it from being sent,
 * if it is not a JSON object. Which keys it may not set the backend checks (`config.checked_extra_body`). */
export function parseExtraBody(text: string): { value: JsonObject | null } | { problem: "json" | "jsonObject" } {
  if (!text.trim()) return { value: null };
  let value: unknown;
  try {
    value = JSON.parse(text);
  } catch {
    return { problem: "json" };
  }
  if (typeof value !== "object" || value === null || Array.isArray(value)) return { problem: "jsonObject" };
  return { value: value as JsonObject };
}

/** An extra request body as a form starts with it: indented JSON, empty for none. */
export function extraBodyText(value: unknown): string {
  return value === null || value === undefined ? "" : JSON.stringify(value, null, 2);
}
