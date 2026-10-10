import type { Provider } from "@/lib/signIn";
import { forgetOwnKeys, turnOwnLLM, type BailianRegion, type LocalLLM } from "@/lib/localOwnKeys";
import { detectTimezone } from "@/lib/timezone";
import type { Emotion, Nod } from "@/lib/standAnimations";

export type Character = {
  id: string;
  name: string;
  intro: string;
  avatar_url: string | null;
  /** Her image colour, `#rrggbb`; the interface only uses what `herVars()` derives from it. */
  color: string;
  background_url: string | null;
  /** Her Spine stand on the call layer; null (her call background alone) unless the deployment
   * configures her idol, her default outfit and where the stands are served from. */
  stand: Stand | null;
  /** Her idol number in the original; the list comes in their order, those without one last. */
  idol_id: number | null;
  /** Her name in simplified Chinese as the community writes it (八宫巡); null when not configured. */
  name_zh: string | null;
  /** Her full name in hiragana, family and given name a space apart (さくらぎ まの); null when not configured. */
  name_kana: string | null;
  /** Her full name in romaji, family name first, a space apart (Sakuragi Mano); null when not configured. */
  name_romaji: string | null;
  /** The name of her unit, from the world setting; null when there is none or it does not say. */
  unit: string | null;
  /** Her unit's name in hiragana, from the world setting; null along with `unit`. */
  unit_reading: string | null;
  /** Where her unit is in the units' official order, from 0; null along with `unit`. */
  unit_order: number | null;
  /** What she says to a visitor on the landing page; null when she has no greeting. */
  greeting: Greeting | null;
};

/** A character's greeting (GLOSSARY.md「招呼」). */
export type Greeting = {
  /** What she says in Japanese, without its delivery cues. */
  ja: string;
  /** Its Chinese subtitle. */
  subtitle: string;
  /** Its audio, an mp3 in the stands' bucket; null unless the deployment serves the stand assets
   * and she has a voice. The server does not check that it was uploaded: when it fails to load, show
   * the subtitle alone. */
  audio_url: string | null;
};

/** Where a character's stand comes from. */
export type Stand = {
  /** The outfit she wears unless the user picks another. */
  default_outfit: Outfit;
  /** Her outfit list: `{idol_id, cards}`, each card with its `everyday` clothes and `stage`
   * costume (either may be null), whose `url` and `thumbnail` are relative to the list
   * (docs/deploy.md「立绘素材」). */
  outfits_url: string;
};

/** One outfit of her stand: `id` is `stand/<enzaId>` or `stand_costume/<enzaId>`, and `url` the
 * directory (ending in `/`) holding its `data.json`, `data.atlas` and `data.png`. */
export type Outfit = { id: string; url: string };

export type Conversation = {
  id: string;
  character_id: string;
  created_at: string;
};

/** A character's newest conversation with the user and its last message (null while it has
 * none), for the conversation list. */
export type LatestConversation = {
  character_id: string;
  conversation_id: string;
  created_at: string;
  last_message: Pick<Message, "role" | "text" | "ja" | "zh" | "created_at"> | null;
};

export type Segment = { ja: string; zh: string };

export type Message = {
  id: number;
  role: "user" | "character";
  text: string | null;
  ja: string | null;
  zh: string | null;
  segments: Segment[];
  created_at: string;
};

/** A turn's events: `user`, then any `delta`s, then `done` or `error`. In a call, `user` says
 * which of her replies in the call it opens, numbered from 1 (a turn replied to afresh opens
 * again, with the next number). */
export type TurnEvent =
  | { type: "user"; text: string; reply?: number }
  | { type: "delta"; segment: number; lang: "ja" | "zh"; text: string }
  | { type: "done"; message: Message }
  | { type: "error"; message: string };

export type Gender = "male" | "female";

/** How the characters treat the user; a field left null keeps its default. */
export type ProducerProfile = {
  form_of_address: string | null;
  gender: Gender | null;
  timezone: string | null;
};

/** Something a character remembers about the user, with the character it was told to;
 * the name is null for a character no longer configured. */
export type Memory = {
  id: number;
  text: string;
  source_character_id: string;
  source_character_name: string | null;
  created_at: string;
  /** 已被后来的记忆取代：角色不会再想起，删掉取代它的那条就恢复（ADR-0014）。 */
  superseded: boolean;
};

/** During a call each utterance, spoken or typed, is a turn; the backend also says when each
 * segment of her voice starts playing, her emotion in each, who starts and stops speaking,
 * and, when it is about to hang up (the call reached its time or turn limit, a voice service
 * or an own key failed), why, and whether the call counted towards the hourly limit. */
export type CallEvent =
  | TurnEvent
  | SegmentPlaying
  | SegmentEmotion
  | Speaking
  | { type: "ended"; reason: BackendEndReason; message: string; counts: boolean };

/** Pipecat's standard RTVI events, not server messages: her voice starts or stops playing
 * (stopping at once when she is interrupted), the user starts or stops speaking. */
export type Speaking = { type: (typeof SPEAKING)[number] };

export const SPEAKING = [
  "bot-started-speaking",
  "bot-stopped-speaking",
  "user-started-speaking",
  "user-stopped-speaking",
] as const;

/** Her voice has started playing segment `segment` of reply `reply`, replies being numbered
 * from 1 within the call. Sent as the segment's first audio goes out, so it arrives a little
 * before it is heard; a segment cut off before it is voiced gets none. */
export type SegmentPlaying = { type: "segment-playing"; reply: number; segment: number };

/** How she feels in segment `segment` of reply `reply`, and whether she nods (`yes`) or shakes
 * her head (`no`) at it; `calm` when it could not be told for sure. Sent once the segment is
 * complete and judged, which may be before or after it starts playing; a segment that could
 * not be judged in time gets none. */
export type SegmentEmotion = {
  type: "emotion";
  reply: number;
  segment: number;
  emotion: Emotion;
  nod: Nod["kind"] | null;
};

/** Why the backend hung up (`EndReason` in `call.py`). */
export type BackendEndReason = "not_connected" | "dropped" | "duration_limit" | "turn_limit" | "own_key";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }

  /** The browser is not signed in, or its session has expired. */
  get unauthorized(): boolean {
    return this.status === 401;
  }
}

/** The status of a request from a user who has not yet agreed to the privacy policy and
 * terms of use. */
export const CONSENT_REQUIRED = 428;

/** The page a response sends the browser to before it can go on, if any: the landing page,
 * to sign in there, when it is not signed in; agreeing to the terms when the user has not yet. */
export function redirectFor(status: number): string | null {
  if (status === 401) return "/";
  if (status === CONSENT_REQUIRED) return "/consent";
  return null;
}

export async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    let message = describe(body?.detail) ?? `请求失败（${res.status}）`;
    if (res.status === 429) message = overLimit(message, body?.retry_at);
    throw new ApiError(message, res.status);
  }
  return res.json();
}

/** The user has used up this hour's turns or calls: say when they can go on, in local time.
 * A user an admin set to their own keys only has no time to wait for (`retry_at` null). */
function overLimit(reason: string, retryAt: unknown): string {
  if (retryAt === null) return `${reason}。`;
  const exact = typeof retryAt === "string" ? Date.parse(retryAt) : NaN;
  if (isNaN(exact)) return `${reason}，请稍后再试。`;
  const at = new Date(Math.ceil(exact / 60_000) * 60_000); // shown to the minute, never early
  const time = at.toLocaleTimeString("zh-CN", { hour: "2-digit", minute: "2-digit" });
  const sameDay = at.toDateString() === new Date().toDateString();
  const day = sameDay ? "" : `${at.getMonth() + 1}月${at.getDate()}日 `;
  return `${reason}，${day}${time} 之后可以再用。`;
}

/** The backend's reason for a failure. A rejected request body lists its problems;
 * the first one's message says what to fix. */
function describe(detail: unknown): string | undefined {
  if (typeof detail === "string") return detail;
  const first = Array.isArray(detail) ? detail[0]?.msg : undefined;
  return typeof first === "string" ? first.replace(/^Value error, /, "") : undefined;
}

/** The headers every backend request carries besides the session cookie: the time zone
 * this browser reports. */
export function apiHeaders(init?: HeadersInit): Headers {
  const headers = new Headers(init);
  headers.set("x-timezone", detectTimezone());
  return headers;
}

/** Sends the browser to the page a response says it must go to first, unless it is there. */
export function followRedirect(res: Response): void {
  const to = redirectFor(res.status);
  if (to && window.location.pathname !== to) window.location.assign(to);
}

/** fetch() for the backend API; sends the browser on when it has to sign in, or agree to the
 * terms, first. */
async function api(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(path, { ...init, headers: apiHeaders(init.headers) });
  followRedirect(res);
  return res;
}

/** The ways to sign in the backend offers, and how to reach the deployer (null if the
 * deployer gave none), which a banned user is told. */
export type SignInOptions = { providers: Provider[]; dev_login: boolean; contact: string | null };

export async function getSignInOptions(): Promise<SignInOptions> {
  return json(await fetch("/api/auth/providers"));
}

/** An identity the user signs in with. */
export type SignInMethod = { provider: Provider; display_name: string; email: string | null };

/** `id`: who the user is, which this browser keeps their own keys apart by (see `localOwnKeys`).
 * `is_admin`: the user may enter the admin console (`/admin`). */
export type Account = { id: string; name: string; sign_in_methods: SignInMethod[]; is_admin: boolean };

/** The signed-in user; sends the browser to sign in, or to agree to the terms, first. */
export async function getAccount(): Promise<Account> {
  return json(await api("/api/account"));
}

/** Stop signing in with the identity at `provider`; refused for the last one. */
export async function unlinkSignInMethod(provider: Provider): Promise<void> {
  await expectNoContent(await api(`/api/account/sign-in-methods/${provider}`, { method: "DELETE" }));
}

export type OwnService = "llm" | "tts" | "stt";

/** The kinds of interface a user's own LLM may speak: the backend's `LLM_PROTOCOLS`, which this
 * follows (and `copy.settings.ownKeys.protocols` names). */
export const LLM_PROTOCOLS = ["chat-completions", "responses", "anthropic"] as const;

export type LLMProtocol = (typeof LLM_PROTOCOLS)[number];

/** The speech recognition services a user may bring a key for. */
export type SttProvider = "soniox" | "bailian";

/**
 * Try the user's own LLM, which the server does not keep; fails with what the service said if
 * the try fails. Its address and model as this browser is to keep them.
 */
export async function checkOwnLLM(llm: LocalLLM): Promise<Pick<LocalLLM, "base_url" | "model">> {
  return json(
    await api("/api/account/keys/llm/check", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(llm),
    }),
  );
}

/**
 * Try the user's own key for speech synthesis ("tts") or recognition ("stt", by the service
 * `provider` names), which the server does not keep; fails with what the service said if the try
 * fails. For speech recognition, the region a DashScope key works in, for this browser to keep
 * with it (null for Soniox).
 */
export async function checkOwnSpeechKey(
  service: "tts" | "stt",
  apiKey: string,
  provider?: SttProvider,
): Promise<{ region?: BailianRegion | null }> {
  return json(
    await api(`/api/account/keys/${service}/check`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, provider }),
    }),
  );
}

/** Delete the user and all their data for good, signing them out everywhere; then forget the own
 * keys this browser keeps for them. */
export async function deleteAccount(userId: string): Promise<void> {
  await expectNoContent(
    await api("/api/account/delete", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ confirm: true }),
    }),
  );
  forgetOwnKeys(userId);
}

/** Sign the user out on every device, this one included, forgetting the own keys this browser
 * keeps for them (none to forget without `userId`); other devices keep theirs. */
export async function logoutEverywhere(userId?: string): Promise<void> {
  await expectNoContent(await api("/api/account/logout-everywhere", { method: "POST" }));
  if (userId) forgetOwnKeys(userId);
}

/** Agree to the privacy policy and terms of use, saying the user is 13 or older. */
export async function agreeToTerms(): Promise<void> {
  await expectNoContent(
    await fetch("/api/account/consent", {
      method: "POST",
      headers: apiHeaders({ "content-type": "application/json" }),
      body: JSON.stringify({ agree_to_terms: true, at_least_13: true }),
    }),
  );
}

/** Sign in as the user with this name (development only). */
export async function devLogin(name: string): Promise<void> {
  await expectNoContent(
    await fetch("/api/auth/dev-login", {
      method: "POST",
      headers: apiHeaders({ "content-type": "application/json" }),
      body: JSON.stringify({ name }),
    }),
  );
}

/** Sign this browser out, forgetting the own keys it keeps for the user. Without `userId`, as
 * before the user has agreed to the terms, there are none: keys are only kept after. */
export async function logout(userId?: string): Promise<void> {
  await expectNoContent(await fetch("/api/auth/logout", { method: "POST" }));
  if (userId) forgetOwnKeys(userId);
}

export async function getProfile(): Promise<ProducerProfile> {
  return json(await api("/api/profile"));
}

export async function saveProfile(profile: ProducerProfile): Promise<ProducerProfile> {
  return json(
    await api("/api/profile", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(profile),
    }),
  );
}

/** Newest first. */
export async function listMemories(): Promise<Memory[]> {
  return json(await api("/api/memories"));
}

export async function deleteMemory(id: number): Promise<void> {
  await expectNoContent(await api(`/api/memories/${id}`, { method: "DELETE" }));
}

export async function clearMemories(): Promise<void> {
  await expectNoContent(await api("/api/memories", { method: "DELETE" }));
}

/** Checks a response that carries no body. */
export async function expectNoContent(res: Response): Promise<void> {
  if (!res.ok) await json(res);
}

export async function listCharacters(): Promise<Character[]> {
  return json(await api("/api/characters"));
}

export async function listConversations(characterId: string): Promise<Conversation[]> {
  return json(await api(`/api/conversations?character_id=${encodeURIComponent(characterId)}`));
}

/** Each character's newest conversation with the user, with its last message; characters
 * the user has never talked to are left out. */
export async function listLatestConversations(): Promise<LatestConversation[]> {
  return json(await api("/api/conversations/latest"));
}

export async function createConversation(characterId: string): Promise<Conversation> {
  return json(
    await api("/api/conversations", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ character_id: characterId }),
    }),
  );
}

export async function listMessages(conversationId: string): Promise<Message[]> {
  return json(await api(`/api/conversations/${conversationId}/messages`));
}

/** What a call needs before it starts: the STUN/TURN servers, how long it may last in seconds
 * (null for no limit), and whether it is exempt from the hourly limit (on the user's own keys
 * alone). Fails with the reason when calls are unavailable. */
export type CallSetup = { iceServers: RTCIceServer[]; maxCallSeconds: number | null; callExempt: boolean };

/** Asked before a call that is to bring the user's own keys for `own`, naming those services but
 * bringing none of the keys: the call itself brings them. */
export async function getCallSetup(own: readonly OwnService[]): Promise<CallSetup> {
  return json(await api(own.length ? `/api/ice-servers?own=${own.join(",")}` : "/api/ice-servers"));
}

/**
 * Sends one text turn, bringing the user's own LLM if this browser keeps one for them, and yields
 * the reply's server-sent events as they arrive.
 */
export async function* sendTurn(conversationId: string, text: string, userId: string): AsyncGenerator<TurnEvent> {
  const res = await api(`/api/conversations/${conversationId}/turns`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text, own_llm: turnOwnLLM(userId) }),
  });
  if (!res.ok || !res.body) {
    await json(res);
    return;
  }
  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += value;
    let end;
    while ((end = buffer.indexOf("\n\n")) >= 0) {
      const frame = buffer.slice(0, end);
      buffer = buffer.slice(end + 2);
      const data = frame
        .split("\n")
        .filter((line) => line.startsWith("data: "))
        .map((line) => line.slice(6))
        .join("\n");
      if (data) yield JSON.parse(data) as TurnEvent;
    }
  }
}
