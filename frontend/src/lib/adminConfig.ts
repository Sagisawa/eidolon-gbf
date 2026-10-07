// 后台的「配置」页（ADR-0013）：每一项同时有 .env 的值、当前生效的值和后台的覆盖，
// 状态是三种之一：使用 .env 的值、已被后台覆盖、覆盖没有生效（回退到 .env）。
// 各项的字段、表单的换算和校验都写在这里，页面只负责摆放。

import { apiHeaders, json, type LLMProtocol } from "@/lib/api";

export type ConfigStatus = "env" | "overridden" | "failed";

export type ItemName =
  | "chat_llm"
  | "memory_llm"
  | "tts"
  | "stt"
  | "judge"
  | "judge_thresholds"
  | "rerank"
  | "limits";

/** The items, in the order the page shows them. */
export const ITEMS: ItemName[] = [
  "chat_llm",
  "memory_llm",
  "tts",
  "stt",
  "judge",
  "judge_thresholds",
  "rerank",
  "limits",
];

type Value = string | number | boolean | null;

/** An item's values as the admin console shows them: of a key, `<field>_last4` only. */
export type Shown = Record<string, Value>;

/** One item of the configuration: `.env`'s value, the one in effect, the fields the
 * admin console overrides (kept even when the override is not in effect), and why not. */
export type ConfigItem = {
  status: ConfigStatus;
  env: Shown;
  effective: Shown;
  override: Shown | null;
  failure: string | null;
  /** The memory model: whether it is the chat model in effect, set apart nowhere. */
  follows_chat?: boolean;
  /** Thresholds: the model they hold for. */
  model?: string;
};

/** An item `.env` does not configure, so there is nothing to change: why. */
export type UnavailableItem = { unavailable: string };

/** What can only be seen here, and why it cannot be changed. */
export type ReadOnlyItem = { name: string; value: unknown; why: string };

export type AdminConfig = {
  /** False without `EIDOLON_SECRET_KEY`: keys can be seen, not changed. */
  keys_editable: boolean;
  read_only: ReadOnlyItem[];
} & { [K in ItemName]: ConfigItem | UnavailableItem };

export function isAvailable(item: ConfigItem | UnavailableItem): item is ConfigItem {
  return !("unavailable" in item);
}

/** How an item's status is shown: the StatusDot's variant, whether it can be restored to
 * `.env`'s, and why the override is not in effect, if it is not. */
export type StatusDisplay = {
  variant: "neutral" | "accent" | "warning";
  canRestore: boolean;
  failure: string | null;
};

export function statusDisplay(item: ConfigItem): StatusDisplay {
  switch (item.status) {
    case "env":
      return { variant: "neutral", canRestore: false, failure: null };
    case "overridden":
      return { variant: "accent", canRestore: true, failure: null };
    case "failed":
      return { variant: "warning", canRestore: true, failure: item.failure };
  }
}

/** How a field is typed in: a choice, text, a key (left empty to keep it), max_tokens (a
 * positive whole number, empty for the protocol's default), a probability or score from 0
 * to 1, a number of seconds, or a limit (a whole number from 0 up, 0 for none). */
export type FieldKind =
  | "select"
  | "text"
  | "optionalText"
  | "secret"
  | "maxTokens"
  | "probability"
  | "seconds"
  | "limit";

/** The limits, in the order they are shown. */
export const LIMIT_FIELDS = ["turns_per_hour", "calls_per_hour", "call_minutes", "turns_per_call", "history_turns"];

export type FieldSpec = { name: string; kind: FieldKind; options?: readonly string[] };

export type ItemSpec = {
  /** The fields the table shows, a key by its name (shown as its last 4 characters). */
  rows: string[];
  secrets: string[];
  form: FieldSpec[];
};

export const LLM_PROTOCOLS: LLMProtocol[] = ["chat-completions", "responses", "anthropic"];

const LLM: ItemSpec = {
  rows: ["protocol", "base_url", "model", "max_tokens", "api_key"],
  secrets: ["api_key"],
  form: [
    { name: "protocol", kind: "select", options: LLM_PROTOCOLS },
    { name: "base_url", kind: "text" },
    { name: "model", kind: "text" },
    { name: "max_tokens", kind: "maxTokens" },
    { name: "api_key", kind: "secret" },
  ],
};

const THRESHOLD = (names: string[]): ItemSpec => ({
  rows: names,
  secrets: [],
  form: names.map((name) => ({ name, kind: "probability" })),
});

export const ITEM_SPECS: Record<ItemName, ItemSpec> = {
  chat_llm: LLM,
  memory_llm: LLM,
  tts: {
    rows: ["model", "api_key"],
    secrets: ["api_key"],
    form: [
      { name: "model", kind: "text" },
      { name: "api_key", kind: "secret" },
    ],
  },
  stt: {
    rows: ["provider", "soniox_api_key", "dashscope_api_key", "region"],
    secrets: ["soniox_api_key", "dashscope_api_key"],
    form: [
      { name: "provider", kind: "select", options: ["soniox", "bailian"] },
      { name: "api_key", kind: "secret" },
    ],
  },
  judge: {
    rows: ["provider", "model", "account_id", "emotion_timeout", "api_key"],
    secrets: ["api_key"],
    form: [
      { name: "provider", kind: "select", options: ["jev", "cloudflare"] },
      { name: "model", kind: "text" },
      { name: "account_id", kind: "optionalText" },
      { name: "emotion_timeout", kind: "seconds" },
      { name: "api_key", kind: "secret" },
    ],
  },
  judge_thresholds: THRESHOLD(["recall", "emotion"]),
  rerank: THRESHOLD(["references", "memories"]),
  limits: { rows: LIMIT_FIELDS, secrets: [], form: LIMIT_FIELDS.map((name) => ({ name, kind: "limit" })) },
};

/** One field of an item, as the table shows it: `.env`'s, the one in effect, and whether
 * the admin console overrides it, with what. `inEffect` marks an override the effective
 * value comes from; one that is not in effect is shown all the same. */
export type FieldRow = {
  field: string;
  env: Value;
  effective: Value;
  overridden: boolean;
  override: Value;
  inEffect: boolean;
};

function valueOf(shown: Shown, field: string, secrets: string[]): Value | undefined {
  return secrets.includes(field) ? shown[`${field}_last4`] : shown[field];
}

export function rows(item: ConfigItem, spec: ItemSpec): FieldRow[] {
  return spec.rows.map((field) => {
    const override = item.override ? valueOf(item.override, field, spec.secrets) : undefined;
    return {
      field,
      env: valueOf(item.env, field, spec.secrets) ?? null,
      effective: valueOf(item.effective, field, spec.secrets) ?? null,
      overridden: override !== undefined,
      override: override ?? null,
      inEffect: override !== undefined && item.status === "overridden",
    };
  });
}

/** An item's form, as typed: starts from the values in effect, every key empty. */
export type Form = Record<string, string>;

export function formOf(spec: ItemSpec, effective: Shown): Form {
  return Object.fromEntries(
    spec.form.map(({ name, kind }) => {
      const value = kind === "secret" ? null : effective[name];
      return [name, value === null || value === undefined ? "" : String(value)];
    }),
  );
}

export type Problem = { field: string; reason: "required" | "maxTokens" | "probability" | "seconds" | "limit" };

export type Change = Record<string, string | number | null>;

/** What saving the form sends, or the first problem that keeps it from being saved. A key
 * left empty, or one that cannot be changed here, stays as it is; so does an optional
 * field left empty. */
export function changeOf(spec: ItemSpec, form: Form, keysEditable: boolean): { change: Change } | { problem: Problem } {
  const change: Change = {};
  for (const { name, kind } of spec.form) {
    const typed = (form[name] ?? "").trim();
    switch (kind) {
      case "select":
        change[name] = form[name];
        break;
      case "text":
        if (!typed) return { problem: { field: name, reason: "required" } };
        change[name] = typed;
        break;
      case "optionalText":
        if (typed) change[name] = typed;
        break;
      case "secret":
        if (keysEditable && typed) change[name] = typed;
        break;
      case "maxTokens":
        if (typed && !/^[1-9]\d*$/.test(typed)) return { problem: { field: name, reason: "maxTokens" } };
        change[name] = typed ? Number(typed) : null;
        break;
      case "probability": {
        const value = Number(typed);
        if (!typed || !(value >= 0 && value <= 1)) return { problem: { field: name, reason: "probability" } };
        change[name] = value;
        break;
      }
      case "limit":
        if (!/^\d+$/.test(typed)) return { problem: { field: name, reason: "limit" } };
        change[name] = Number(typed);
        break;
      case "seconds": {
        const value = Number(typed);
        if (!typed || !(value > 0 && value <= 30)) return { problem: { field: name, reason: "seconds" } };
        change[name] = value;
        break;
      }
    }
  }
  return { change };
}

/** A read-only setting's value, in words: a list joined, a setting set or not, the parts
 * of one with several. */
export function readOnlyValue(value: unknown, words: { set: string; unset: string; none: string }): string {
  if (value === null || value === undefined || value === "") return words.none;
  if (typeof value === "boolean") return value ? words.set : words.unset;
  if (Array.isArray(value)) return value.length ? value.map((v) => readOnlyValue(v, words)).join("、") : words.none;
  if (typeof value === "object") {
    return Object.entries(value)
      .map(([key, part]) => `${key}：${readOnlyValue(part, words)}`)
      .join("；");
  }
  return String(value);
}

export async function getAdminConfig(): Promise<AdminConfig> {
  return json(await fetch("/api/admin/config", { headers: apiHeaders() }));
}

/** Try the item and keep it; fails with what the service said if the try fails. */
export async function saveItem(name: ItemName, change: Change): Promise<AdminConfig> {
  return json(
    await fetch(`/api/admin/config/${name}`, {
      method: "PUT",
      headers: apiHeaders({ "content-type": "application/json" }),
      body: JSON.stringify(change),
    }),
  );
}

/** Back to `.env`'s, from the next turn and call on. */
export async function restoreItem(name: ItemName): Promise<AdminConfig> {
  return json(await fetch(`/api/admin/config/${name}`, { method: "DELETE", headers: apiHeaders() }));
}
