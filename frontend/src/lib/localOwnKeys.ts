// 浏览器里存的自带密钥（GLOSSARY.md「自带密钥」，ADR-0017）：服务器不保存，只存在这个浏览器的 localStorage 里，
// 按用户分开存（键为 eidolon.ownKeys.<用户 ID>），值是明文 JSON。每次发请求都现读，别的标签页改了，下一次请求就用上。
// 存储不可用（隐私模式等）时不抛错：读到的是什么都没存，存的也存不下。

import type { LLMProtocol, OwnService, SttProvider } from "@/lib/api";

/** 自带的 LLM，原样就是文字回合请求体里的 `own_llm`。 */
export type LocalLLM = { api_key: string; base_url: string; model: string; protocol: LLMProtocol };

/** 语音合成（Fish Audio）的 key。 */
export type LocalTtsKey = { api_key: string };

/** 阿里云百炼的 key 能用的地域，校验时由服务器判断出来。 */
export type BailianRegion = "beijing" | "singapore";

/** 语音识别的 key，连同它所属的服务商；百炼的还有地域。 */
export type LocalSttKey = { api_key: string; provider: SttProvider; region?: BailianRegion };

/** 一位用户在这个浏览器里存的自带密钥，每项都可以没有。 */
export type LocalOwnKeys = { llm?: LocalLLM; tts?: LocalTtsKey; stt?: LocalSttKey };

const PROTOCOLS: readonly unknown[] = ["chat-completions", "responses", "anthropic"] satisfies LLMProtocol[];
const STT_PROVIDERS: readonly unknown[] = ["soniox", "bailian"] satisfies SttProvider[];
const REGIONS: readonly unknown[] = ["beijing", "singapore"] satisfies BailianRegion[];

function storageKey(userId: string): string {
  return `eidolon.ownKeys.${userId}`;
}

/** 这位用户在这个浏览器里存的自带密钥；存错了的那一项当作没有。 */
export function localOwnKeys(userId: string): LocalOwnKeys {
  let stored: unknown;
  try {
    stored = JSON.parse(localStorage.getItem(storageKey(userId)) ?? "{}");
  } catch {
    return {};
  }
  if (!isRecord(stored)) return {};
  const keys: LocalOwnKeys = {};
  const { llm, tts, stt } = stored;
  if (
    isRecord(llm) &&
    isString(llm.api_key) &&
    isString(llm.base_url) &&
    isString(llm.model) &&
    PROTOCOLS.includes(llm.protocol)
  ) {
    keys.llm = { api_key: llm.api_key, base_url: llm.base_url, model: llm.model, protocol: llm.protocol as LLMProtocol };
  }
  if (isRecord(tts) && isString(tts.api_key)) keys.tts = { api_key: tts.api_key };
  if (
    isRecord(stt) &&
    isString(stt.api_key) &&
    STT_PROVIDERS.includes(stt.provider) &&
    (stt.region === undefined || REGIONS.includes(stt.region))
  ) {
    keys.stt = { api_key: stt.api_key, provider: stt.provider as SttProvider };
    if (stt.region !== undefined) keys.stt.region = stt.region as BailianRegion;
  }
  return keys;
}

/** 存下（或换掉）这位用户某一项服务的 key。 */
export function keepOwnKey<S extends OwnService>(userId: string, service: S, key: NonNullable<LocalOwnKeys[S]>): void {
  write(userId, { ...localOwnKeys(userId), [service]: key });
}

/** 删掉这位用户某一项服务的 key，这一项改回用部署者的服务。 */
export function forgetOwnKey(userId: string, service: OwnService): void {
  const keys = localOwnKeys(userId);
  delete keys[service];
  write(userId, keys);
}

/** 删掉这位用户在这个浏览器里存的全部自带密钥。 */
export function forgetOwnKeys(userId: string): void {
  try {
    localStorage.removeItem(storageKey(userId));
  } catch {
    // 存储不可用：本来也什么都没存下。
  }
}

/** 文字回合要带的 `own_llm`：这位用户存的 LLM，没有就不带。 */
export function turnOwnLLM(userId: string): LocalLLM | undefined {
  return localOwnKeys(userId).llm;
}

/** 界面上再显示时，一把 key 只露出末 4 位。 */
export function last4(apiKey: string): string {
  return apiKey.slice(-4);
}

function write(userId: string, keys: LocalOwnKeys): void {
  try {
    localStorage.setItem(storageKey(userId), JSON.stringify(keys));
  } catch {
    // 存储不可用：这次存不下。
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}
