import { describe, expect, it } from "vitest";

import {
  llmChange,
  llmForm,
  llmRows,
  statusDisplay,
  type ConfigItem,
  type LLMShown,
} from "@/lib/adminConfig";

const ENV: LLMShown = {
  protocol: "chat-completions",
  base_url: "https://env.example/v1",
  model: "env-model",
  max_tokens: null,
  api_key_last4: "aaaa",
};
const OVERRIDE: Partial<LLMShown> = { model: "new-model", api_key_last4: "bbbb" };

function item(status: ConfigItem<LLMShown>["status"]): ConfigItem<LLMShown> {
  return {
    status,
    env: ENV,
    effective: status === "overridden" ? { ...ENV, ...OVERRIDE } : ENV,
    override: status === "env" ? null : OVERRIDE,
    failure: status === "failed" ? "401 key revoked" : null,
  };
}

describe("statusDisplay", () => {
  it("shows each of the three states, restorable once overridden, with why it failed", () => {
    expect(statusDisplay(item("env"))).toEqual({ variant: "neutral", canRestore: false, failure: null });
    expect(statusDisplay(item("overridden"))).toEqual({ variant: "accent", canRestore: true, failure: null });
    expect(statusDisplay(item("failed"))).toEqual({
      variant: "warning",
      canRestore: true,
      failure: "401 key revoked",
    });
  });
});

describe("llmRows", () => {
  it("marks the overridden fields, in effect only while the override has not failed", () => {
    for (const status of ["overridden", "failed"] as const) {
      const rows = Object.fromEntries(llmRows(item(status)).map((row) => [row.field, row]));
      const inEffect = status === "overridden";
      expect(rows.model, status).toEqual({
        field: "model",
        env: "env-model",
        effective: inEffect ? "new-model" : "env-model",
        overridden: true,
        override: "new-model",
        inEffect,
      });
      expect(rows.api_key, status).toEqual({
        field: "api_key",
        env: "aaaa",
        effective: inEffect ? "bbbb" : "aaaa",
        overridden: true,
        override: "bbbb",
        inEffect,
      });
      expect(rows.max_tokens, status).toEqual({
        field: "max_tokens",
        env: null,
        effective: null,
        overridden: false,
        override: null,
        inEffect: false,
      });
    }
  });
});

describe("llmChange", () => {
  const form = { ...llmForm({ ...ENV, max_tokens: 1024 }), api_key: " sk-new " };

  it("starts from the values in effect, the key left empty", () => {
    expect(llmForm({ ...ENV, max_tokens: 1024 })).toEqual({
      protocol: "chat-completions",
      base_url: "https://env.example/v1",
      model: "env-model",
      max_tokens: "1024",
      api_key: "",
    });
  });

  it("sends the key only when it can be changed and was typed", () => {
    expect(llmChange(form, true)).toEqual({
      protocol: "chat-completions",
      base_url: "https://env.example/v1",
      model: "env-model",
      max_tokens: 1024,
      api_key: "sk-new",
    });
    expect(llmChange(form, false)).not.toHaveProperty("api_key");
    expect(llmChange({ ...form, api_key: "  " }, true)).not.toHaveProperty("api_key");
  });

  it("takes an empty max_tokens as the default and refuses one that is not a positive whole number", () => {
    expect(llmChange({ ...form, max_tokens: "" }, true)?.max_tokens).toBeNull();
    for (const bad of ["0", "-1", "1.5", "abc"]) {
      expect(llmChange({ ...form, max_tokens: bad }, true), bad).toBeNull();
    }
    expect(llmChange({ ...form, model: " " }, true)).toBeNull();
  });
});
