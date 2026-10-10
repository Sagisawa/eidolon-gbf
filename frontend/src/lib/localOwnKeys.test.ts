import { afterEach, describe, expect, it, vi } from "vitest";
import {
  canKeepOwnKeys,
  forgetOwnKey,
  forgetOwnKeys,
  keepOwnKey,
  localOwnKeys,
  ownServices,
  turnOwnLLM,
} from "@/lib/localOwnKeys";

const LLM = {
  api_key: "sk-my-own-key-1234",
  base_url: "https://llm.example.com/v1",
  model: "my-model",
  protocol: "chat-completions",
} as const;
const STT = { api_key: "sk-my-dashscope-dddd", provider: "bailian", region: "singapore" } as const;

/** This browser's local storage, in memory. */
function storage(initial: Record<string, string> = {}) {
  const items = new Map(Object.entries(initial));
  vi.stubGlobal("localStorage", {
    getItem: (key: string) => items.get(key) ?? null,
    setItem: (key: string, value: string) => void items.set(key, value),
    removeItem: (key: string) => void items.delete(key),
  });
  return items;
}

afterEach(() => vi.unstubAllGlobals());

describe("own keys kept in this browser", () => {
  it("are kept for each user apart, in plain JSON under the user's own key", () => {
    const items = storage();

    keepOwnKey("u1", "llm", LLM);
    keepOwnKey("u1", "stt", STT);
    keepOwnKey("u2", "tts", { api_key: "fish-their-own-key" });

    expect(localOwnKeys("u1")).toEqual({ llm: LLM, stt: STT });
    expect(localOwnKeys("u2")).toEqual({ tts: { api_key: "fish-their-own-key" } });
    expect(localOwnKeys("u3")).toEqual({});
    expect(JSON.parse(items.get("eidolon.ownKeys.u1")!)).toEqual({ llm: LLM, stt: STT });
  });

  it("replace the one kept for a service, and forget one or all of a user's", () => {
    storage();
    keepOwnKey("u1", "llm", LLM);
    keepOwnKey("u1", "tts", { api_key: "fish-my-own-key" });
    keepOwnKey("u2", "llm", LLM);

    keepOwnKey("u1", "llm", { ...LLM, model: "another-model" });
    expect(localOwnKeys("u1").llm?.model).toBe("another-model");

    forgetOwnKey("u1", "llm");
    expect(localOwnKeys("u1")).toEqual({ tts: { api_key: "fish-my-own-key" } });

    forgetOwnKeys("u1");
    expect(localOwnKeys("u1")).toEqual({});
    expect(localOwnKeys("u2")).toEqual({ llm: LLM });
  });

  it("are read afresh each time, so a change in another tab holds for the next request", () => {
    const items = storage();
    keepOwnKey("u1", "llm", LLM);

    items.set("eidolon.ownKeys.u1", JSON.stringify({ llm: { ...LLM, api_key: "sk-changed-elsewhere" } }));

    expect(turnOwnLLM("u1")?.api_key).toBe("sk-changed-elsewhere");
  });

  it("leave out what is stored wrongly, keeping what is right", () => {
    storage({
      "eidolon.ownKeys.u1": JSON.stringify({
        llm: { ...LLM, protocol: "grpc" },
        tts: { api_key: 42 },
        stt: { ...STT, region: "mars" },
      }),
      "eidolon.ownKeys.u2": "{not json",
      "eidolon.ownKeys.u3": JSON.stringify({ llm: LLM, stt: { api_key: "soniox-key-bbbb", provider: "soniox" } }),
    });

    expect(localOwnKeys("u1")).toEqual({});
    expect(localOwnKeys("u2")).toEqual({});
    expect(localOwnKeys("u3")).toEqual({ llm: LLM, stt: { api_key: "soniox-key-bbbb", provider: "soniox" } });
  });
});

describe("what a call brings", () => {
  it("names the services the user keeps their own keys for", () => {
    storage();
    keepOwnKey("u1", "stt", STT);
    keepOwnKey("u1", "llm", LLM);

    expect(ownServices(localOwnKeys("u1"))).toEqual(["llm", "stt"]);
    expect(ownServices(localOwnKeys("u2"))).toEqual([]);
  });
});

describe("a browser that cannot keep own keys", () => {
  it("says so when its storage refuses to keep anything, and nothing it was given is brought", () => {
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => {
        throw new DOMException("quota", "QuotaExceededError");
      },
      removeItem: () => {},
    });

    expect(canKeepOwnKeys()).toBe(false);
    keepOwnKey("u1", "llm", LLM);
    expect(localOwnKeys("u1")).toEqual({});
    expect(turnOwnLLM("u1")).toBeUndefined();
  });

  it("says so when its storage cannot even be reached, without throwing", () => {
    const unreachable = () => {
      throw new DOMException("denied", "SecurityError");
    };
    vi.stubGlobal("localStorage", { getItem: unreachable, setItem: unreachable, removeItem: unreachable });

    expect(canKeepOwnKeys()).toBe(false);
    expect(() => keepOwnKey("u1", "llm", LLM)).not.toThrow();
    expect(() => forgetOwnKeys("u1")).not.toThrow();
    expect(localOwnKeys("u1")).toEqual({});
  });

  it("is not one whose storage works, which is left as it was", () => {
    const items = storage({ "eidolon.ownKeys.u1": JSON.stringify({ llm: LLM }) });

    expect(canKeepOwnKeys()).toBe(true);
    expect([...items.keys()]).toEqual(["eidolon.ownKeys.u1"]);
  });
});
