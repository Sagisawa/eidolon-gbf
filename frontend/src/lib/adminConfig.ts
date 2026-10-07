// 后台的「配置」页（ADR-0013）：每一项同时有 .env 的值、当前生效的值和后台的覆盖，
// 状态是三种之一：使用 .env 的值、已被后台覆盖、覆盖已失效并回退到 .env。

import { apiHeaders, json, type LLMProtocol } from "@/lib/api";

export type ConfigStatus = "env" | "overridden" | "failed";

/** A model slot as the admin console shows it: of its key, only the last 4 characters. */
export type LLMShown = {
  protocol: LLMProtocol;
  base_url: string;
  model: string;
  max_tokens: number | null;
  api_key_last4: string;
};

/** One item of the configuration: `.env`'s value, the one in effect, the fields the
 * admin console overrides (kept even when the override failed), and why it failed. */
export type ConfigItem<T> = {
  status: ConfigStatus;
  env: T;
  effective: T;
  override: Partial<T> | null;
  failure: string | null;
};

export type AdminConfig = {
  /** False without `EIDOLON_SECRET_KEY`: keys can be seen, not changed. */
  keys_editable: boolean;
  chat_llm: ConfigItem<LLMShown>;
};

/** How an item's status is shown: the StatusDot's variant, whether it can be restored to
 * `.env`'s, and the failure to explain, if any. */
export type StatusDisplay = {
  variant: "neutral" | "accent" | "warning";
  canRestore: boolean;
  failure: string | null;
};

export function statusDisplay(item: ConfigItem<unknown>): StatusDisplay {
  switch (item.status) {
    case "env":
      return { variant: "neutral", canRestore: false, failure: null };
    case "overridden":
      return { variant: "accent", canRestore: true, failure: null };
    case "failed":
      return { variant: "warning", canRestore: true, failure: item.failure };
  }
}

export const LLM_FIELDS = ["protocol", "base_url", "model", "max_tokens", "api_key"] as const;

export type LLMField = (typeof LLM_FIELDS)[number];

type Value = string | number | null;

/** One field of a model slot, as the table shows it: `.env`'s, the one in effect, and
 * whether the admin console overrides it, with what. `inEffect` marks an override the
 * effective value comes from; a failed override is shown but not in effect. */
export type FieldRow = {
  field: LLMField;
  env: Value;
  effective: Value;
  overridden: boolean;
  override: Value;
  inEffect: boolean;
};

function valueOf(shown: Partial<LLMShown>, field: LLMField): Value | undefined {
  return field === "api_key" ? shown.api_key_last4 : shown[field];
}

export function llmRows(item: ConfigItem<LLMShown>): FieldRow[] {
  return LLM_FIELDS.map((field) => {
    const override = item.override ? valueOf(item.override, field) : undefined;
    return {
      field,
      env: valueOf(item.env, field) ?? null,
      effective: valueOf(item.effective, field) ?? null,
      overridden: override !== undefined,
      override: override ?? null,
      inEffect: override !== undefined && item.status === "overridden",
    };
  });
}

/** The form for a model slot, as typed: starts from the values in effect, the key empty. */
export type LLMForm = {
  protocol: LLMProtocol;
  base_url: string;
  model: string;
  max_tokens: string;
  api_key: string;
};

export function llmForm(effective: LLMShown): LLMForm {
  return {
    protocol: effective.protocol,
    base_url: effective.base_url,
    model: effective.model,
    max_tokens: effective.max_tokens === null ? "" : String(effective.max_tokens),
    api_key: "",
  };
}

export type LLMChange = {
  protocol: LLMProtocol;
  base_url: string;
  model: string;
  max_tokens: number | null;
  api_key?: string;
};

/** What saving the form sends, or null while it cannot be saved: the address and model
 * are needed, and max_tokens is empty (the protocol's default) or a positive whole number.
 * A key left empty, or one that cannot be changed here, stays as it is. */
export function llmChange(form: LLMForm, keysEditable: boolean): LLMChange | null {
  const baseUrl = form.base_url.trim();
  const model = form.model.trim();
  const maxTokens = form.max_tokens.trim();
  if (!baseUrl || !model) return null;
  if (maxTokens && !/^[1-9]\d*$/.test(maxTokens)) return null;
  const change: LLMChange = {
    protocol: form.protocol,
    base_url: baseUrl,
    model,
    max_tokens: maxTokens ? Number(maxTokens) : null,
  };
  const apiKey = form.api_key.trim();
  if (keysEditable && apiKey) change.api_key = apiKey;
  return change;
}

export async function getAdminConfig(): Promise<AdminConfig> {
  return json(await fetch("/api/admin/config", { headers: apiHeaders() }));
}

/** Try the chat model and keep it; fails with what the service said if the try fails. */
export async function saveChatLLM(change: LLMChange): Promise<AdminConfig> {
  return json(
    await fetch("/api/admin/config/chat_llm", {
      method: "PUT",
      headers: apiHeaders({ "content-type": "application/json" }),
      body: JSON.stringify(change),
    }),
  );
}

/** Back to `.env`'s chat model, from the next turn and call on. */
export async function restoreChatLLM(): Promise<AdminConfig> {
  return json(await fetch("/api/admin/config/chat_llm", { method: "DELETE", headers: apiHeaders() }));
}
