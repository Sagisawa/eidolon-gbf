// 浏览器里存的自带密钥（GLOSSARY.md「自带密钥」，ADR-0017）：服务器不保存，只存在这个浏览器的 localStorage 里，
// 按用户分开存（键为 eidolon.ownKeys.<用户 ID>），值是明文 JSON。每次发请求都现读，别的标签页改了，下一次请求就用上。
// 存储不可用（隐私模式等）时不抛错：读到的是什么都没存，存的也存不下；`canKeepOwnKeys` 如实报告，设置页据此告诉用户。
// 不退而存在内存里。

// 下面几份取值列表跟后端同步（不做代码生成）：后端改了，这里照着改。

/** 能自带 key 的服务：后端 `own_keys.Service`。 */
export const OWN_SERVICES = ["llm", "tts", "stt"] as const;
export type OwnService = (typeof OWN_SERVICES)[number];

/** 自带的 LLM 能用的接口协议：后端 `config.LLM_PROTOCOLS`（`copy.settings.ownKeys.protocols` 给它们起名）。
 * 设置页和后台配置页的选项都从这里来。 */
export const LLM_PROTOCOLS = ["chat-completions", "responses", "anthropic"] as const;
export type LLMProtocol = (typeof LLM_PROTOCOLS)[number];

/** 语音识别的服务商：后端 `config.SttProvider`。设置页和后台配置页的选项都从这里来。 */
export const STT_PROVIDERS = ["soniox", "bailian"] as const;
export type SttProvider = (typeof STT_PROVIDERS)[number];

/** 阿里云百炼的 key 能用的地域，校验时由服务器判断出来：后端 `config.BailianRegion`。 */
const BAILIAN_REGIONS = ["beijing", "singapore"] as const;
export type BailianRegion = (typeof BAILIAN_REGIONS)[number];

/** 自带的 LLM，原样就是请求里 `own_keys` 的 `llm`。 */
export type LocalLLM = { api_key: string; base_url: string; model: string; protocol: LLMProtocol };

/** 语音合成（Fish Audio）的 key。 */
export type LocalTtsKey = { api_key: string };

/** 语音识别的 key，连同它所属的服务商；百炼的还有地域。 */
export type LocalSttKey = { api_key: string; provider: SttProvider; region?: BailianRegion };

/** 一位用户在这个浏览器里存的自带密钥，每项都可以没有。原样就是请求里的 `own_keys`（后端 `OwnKeysInput`）。 */
export type LocalOwnKeys = { llm?: LocalLLM; tts?: LocalTtsKey; stt?: LocalSttKey };

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
    isOneOf(llm.protocol, LLM_PROTOCOLS)
  ) {
    keys.llm = { api_key: llm.api_key, base_url: llm.base_url, model: llm.model, protocol: llm.protocol };
  }
  if (isRecord(tts) && isString(tts.api_key)) keys.tts = { api_key: tts.api_key };
  if (
    isRecord(stt) &&
    isString(stt.api_key) &&
    isOneOf(stt.provider, STT_PROVIDERS) &&
    (stt.region === undefined || isOneOf(stt.region, BAILIAN_REGIONS))
  ) {
    keys.stt = { api_key: stt.api_key, provider: stt.provider };
    if (stt.region !== undefined) keys.stt.region = stt.region;
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

/** 一次文字回合要带的 `own_keys`：只有这位用户存的 LLM（文字回合用不上语音 key，不带出去）；没存 LLM 就不带。 */
export function turnOwnKeys(userId: string): { llm: LocalLLM } | undefined {
  const { llm } = localOwnKeys(userId);
  return llm && { llm };
}

/** 存了 key 的那几项服务：通话预检时只报这些服务名，不带 key；也是判断计不计入限额的依据。 */
export function ownServices(keys: LocalOwnKeys): OwnService[] {
  return OWN_SERVICES.filter((service) => keys[service] !== undefined);
}

/** 这个浏览器能不能存自带密钥：试着写一下再删掉。隐私模式、禁用了本地存储时是不能。 */
export function canKeepOwnKeys(): boolean {
  const probe = "eidolon.ownKeys.probe";
  try {
    localStorage.setItem(probe, "1");
    localStorage.removeItem(probe);
    return true;
  } catch {
    return false;
  }
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

function isOneOf<T extends string>(value: unknown, known: readonly T[]): value is T {
  return typeof value === "string" && (known as readonly string[]).includes(value);
}

function isString(value: unknown): value is string {
  return typeof value === "string";
}
