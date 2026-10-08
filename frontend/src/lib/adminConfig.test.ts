import { describe, expect, it } from "vitest";

import {
  changeOf,
  formOf,
  ITEM_SPECS,
  UNLIMITED,
  readOnlyValue,
  rows,
  statusDisplay,
  type ConfigItem,
  type Shown,
} from "@/lib/adminConfig";

const ENV: Shown = {
  protocol: "chat-completions",
  base_url: "https://env.example/v1",
  model: "env-model",
  max_tokens: null,
  api_key_last4: "aaaa",
};
const OVERRIDE: Shown = { model: "new-model", api_key_last4: "bbbb" };

function item(status: ConfigItem["status"]): ConfigItem {
  return {
    status,
    env: ENV,
    effective: status === "overridden" ? { ...ENV, ...OVERRIDE } : ENV,
    override: status === "env" ? null : OVERRIDE,
    failure: status === "failed" ? "401 key revoked" : null,
  };
}

describe("statusDisplay", () => {
  it("marks only the overridden and failed states, restorable once overridden, with why it is not in effect", () => {
    expect(statusDisplay(item("env"))).toEqual({ variant: null, canRestore: false, failure: null });
    expect(statusDisplay(item("overridden"))).toEqual({ variant: "accent", canRestore: true, failure: null });
    expect(statusDisplay(item("failed"))).toEqual({
      variant: "warning",
      canRestore: true,
      failure: "401 key revoked",
    });
  });
});

describe("rows", () => {
  it("marks the overridden fields, in effect only while the override is, a key by its last 4", () => {
    for (const status of ["overridden", "failed"] as const) {
      const byField = Object.fromEntries(rows(item(status), ITEM_SPECS.chat_llm).map((row) => [row.field, row]));
      const inEffect = status === "overridden";
      expect(byField.model, status).toEqual({
        field: "model",
        env: "env-model",
        effective: inEffect ? "new-model" : "env-model",
        overridden: true,
        override: "new-model",
        inEffect,
      });
      expect(byField.api_key, status).toEqual({
        field: "api_key",
        env: "aaaa",
        effective: inEffect ? "bbbb" : "aaaa",
        overridden: true,
        override: "bbbb",
        inEffect,
      });
      expect(byField.max_tokens, status).toEqual({
        field: "max_tokens",
        env: null,
        effective: null,
        overridden: false,
        override: null,
        inEffect: false,
      });
    }
  });

  it("shows each key of speech recognition by the service it is for", () => {
    const stt: ConfigItem = {
      status: "overridden",
      env: { provider: "soniox", soniox_api_key_last4: "1111", dashscope_api_key_last4: null, region: null },
      effective: { provider: "bailian", soniox_api_key_last4: "1111", dashscope_api_key_last4: "2222", region: "beijing" },
      override: { provider: "bailian", dashscope_api_key_last4: "2222", region: "beijing" },
      failure: null,
    };

    const byField = Object.fromEntries(rows(stt, ITEM_SPECS.stt).map((row) => [row.field, row]));

    expect(byField.soniox_api_key).toMatchObject({ effective: "1111", overridden: false });
    expect(byField.dashscope_api_key).toMatchObject({ env: null, effective: "2222", overridden: true });
  });
});

describe("formOf and changeOf", () => {
  const llm = ITEM_SPECS.chat_llm;
  const form = { ...formOf(llm, { ...ENV, max_tokens: 1024 }), api_key: " sk-new " };

  it("starts from the values in effect, the key left empty", () => {
    expect(formOf(llm, { ...ENV, max_tokens: 1024 })).toEqual({
      protocol: "chat-completions",
      base_url: "https://env.example/v1",
      model: "env-model",
      max_tokens: "1024",
      api_key: "",
    });
  });

  it("sends the key only when it can be changed and was typed", () => {
    expect(changeOf(llm, form, true)).toEqual({
      change: {
        protocol: "chat-completions",
        base_url: "https://env.example/v1",
        model: "env-model",
        max_tokens: 1024,
        api_key: "sk-new",
      },
    });
    expect(changeOf(llm, form, false)).toEqual({ change: expect.not.objectContaining({ api_key: expect.anything() }) });
    expect(changeOf(llm, { ...form, api_key: "  " }, true)).toEqual({
      change: expect.not.objectContaining({ api_key: expect.anything() }),
    });
  });

  it("takes an empty max_tokens as the default and names what keeps the form from being saved", () => {
    expect(changeOf(llm, { ...form, max_tokens: "" }, true)).toMatchObject({ change: { max_tokens: null } });
    for (const bad of ["0", "-1", "1.5", "abc"]) {
      expect(changeOf(llm, { ...form, max_tokens: bad }, true), bad).toEqual({
        problem: { field: "max_tokens", reason: "maxTokens" },
      });
    }
    expect(changeOf(llm, { ...form, model: " " }, true)).toEqual({ problem: { field: "model", reason: "required" } });
  });

  it("takes thresholds from 0 to 1 and seconds above 0", () => {
    const thresholds = ITEM_SPECS.judge_thresholds;
    expect(changeOf(thresholds, { recall: "0.7", emotion: "0" }, true)).toEqual({ change: { recall: 0.7, emotion: 0 } });
    for (const bad of ["1.1", "-0.1", "", "high"]) {
      expect(changeOf(thresholds, { recall: bad, emotion: "0.5" }, true), bad).toEqual({
        problem: { field: "recall", reason: "probability" },
      });
    }
    const judge = { provider: "jev", model: "typesafe/jev-1.13", account_id: "", api_key: "" };
    expect(changeOf(ITEM_SPECS.judge, { ...judge, emotion_timeout: "0" }, true)).toEqual({
      problem: { field: "emotion_timeout", reason: "seconds" },
    });
    expect(changeOf(ITEM_SPECS.judge, { ...judge, emotion_timeout: "1.5" }, true)).toEqual({
      change: { provider: "jev", model: "typesafe/jev-1.13", emotion_timeout: 1.5 },
    });
  });
});

describe("limits", () => {
  const limits = ITEM_SPECS.limits;
  const form = {
    turns_per_hour: "2",
    calls_per_hour: UNLIMITED,
    call_minutes: "10",
    turns_per_call: "40",
    history_turns: "20",
  };

  it("starts a limit of 0 as none, not as a number", () => {
    expect(formOf(limits, { ...form, calls_per_hour: 0, turns_per_hour: 2 }).calls_per_hour).toBe(UNLIMITED);
    expect(formOf(limits, { ...form, calls_per_hour: 0, turns_per_hour: 2 }).turns_per_hour).toBe("2");
  });

  it("takes whole numbers from 1 up, and sends none as 0", () => {
    expect(changeOf(limits, form, true)).toEqual({
      change: { turns_per_hour: 2, calls_per_hour: 0, call_minutes: 10, turns_per_call: 40, history_turns: 20 },
    });
  });

  it("refuses one that is 0, negative, not whole or empty", () => {
    for (const bad of ["0", "-1", "1.5", "", "十"]) {
      expect(changeOf(limits, { ...form, calls_per_hour: bad }, true), bad).toEqual({
        problem: { field: "calls_per_hour", reason: "limit" },
      });
    }
  });
});

describe("readOnlyValue", () => {
  const words = { set: "已设置", unset: "未设置", none: "—" };

  it("says a setting is set, never what it is, and lists the parts of the others", () => {
    expect(readOnlyValue(true, words)).toBe("已设置");
    expect(readOnlyValue(false, words)).toBe("未设置");
    expect(readOnlyValue(["github:1001", "google:g-1"], words)).toBe("github:1001、google:g-1");
    expect(readOnlyValue([], words)).toBe("—");
    expect(readOnlyValue(null, words)).toBe("—");
    expect(readOnlyValue({ ice_servers: ["stun:a"], turn: [] }, words)).toBe("ice_servers：stun:a；turn：—");
  });
});
