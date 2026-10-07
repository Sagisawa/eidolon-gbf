import type { Provider } from "@/lib/signIn";
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

/** The page a response sends the browser to before it can go on, if any: signing in
 * when it is not signed in, agreeing to the terms when the user has not yet. */
export function redirectFor(status: number): string | null {
  if (status === 401) return "/login";
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

/** The user has used up this hour's turns or calls: say when they can go on, in local time. */
function overLimit(reason: string, retryAt: unknown): string {
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

/** `is_admin`: the user may enter the admin console (`/admin`). */
export type Account = { name: string; sign_in_methods: SignInMethod[]; is_admin: boolean };

/** The signed-in user; sends the browser to sign in, or to agree to the terms, first. */
export async function getAccount(): Promise<Account> {
  return json(await api("/api/account"));
}

/** Stop signing in with the identity at `provider`; refused for the last one. */
export async function unlinkSignInMethod(provider: Provider): Promise<void> {
  await expectNoContent(await api(`/api/account/sign-in-methods/${provider}`, { method: "DELETE" }));
}

export type OwnService = "llm" | "tts" | "stt";

export type LLMProtocol = "chat-completions" | "responses" | "anthropic";

/** A key the user brought, as they may see it: only its last 4 characters. */
export type OwnKey = { last4: string };

export type OwnLLM = OwnKey & { base_url: string; model: string; protocol: LLMProtocol };

/** The speech recognition services a user may bring a key for. */
export type SttProvider = "soniox" | "bailian";

export type OwnSttKey = OwnKey & { provider: SttProvider };

export type OwnKeys = {
  /** Whether the deployment lets users bring their own keys at all. */
  available: boolean;
  keys: { llm?: OwnLLM; tts?: OwnKey; stt?: OwnSttKey };
  /** What of the user's use does not count towards the hourly limits. */
  exempt: { turns: boolean; calls: boolean };
  protocols: LLMProtocol[];
};

export async function getOwnKeys(): Promise<OwnKeys> {
  return json(await api("/api/account/keys"));
}

/** Try the user's own LLM and keep it; fails with what the service said if the try fails. */
export async function saveOwnLLM(
  llm: Omit<OwnLLM, "last4"> & { api_key: string },
): Promise<OwnLLM> {
  return json(
    await api("/api/account/keys/llm", {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(llm),
    }),
  );
}

/**
 * Try the user's own key for speech synthesis ("tts") or recognition ("stt", by the service
 * `provider` names) and keep it.
 */
export async function saveOwnSpeechKey(
  service: "tts" | "stt",
  apiKey: string,
  provider?: SttProvider,
): Promise<OwnKey> {
  return json(
    await api(`/api/account/keys/${service}`, {
      method: "PUT",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ api_key: apiKey, provider }),
    }),
  );
}

/** Forget the user's own key for `service`; the deployer's is used again. */
export async function deleteOwnKey(service: OwnService): Promise<void> {
  await expectNoContent(await api(`/api/account/keys/${service}`, { method: "DELETE" }));
}

/** Delete the user and all their data for good, signing them out everywhere. */
export async function deleteAccount(): Promise<void> {
  await expectNoContent(
    await api("/api/account/delete", {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify({ confirm: true }),
    }),
  );
}

/** Sign the user out on every device, this one included. */
export async function logoutEverywhere(): Promise<void> {
  await expectNoContent(await api("/api/account/logout-everywhere", { method: "POST" }));
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

/** Sign this browser out. */
export async function logout(): Promise<void> {
  await expectNoContent(await fetch("/api/auth/logout", { method: "POST" }));
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
async function expectNoContent(res: Response): Promise<void> {
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

export async function getCallSetup(): Promise<CallSetup> {
  return json(await api("/api/ice-servers"));
}

/** Sends one text turn and yields the reply's server-sent events as they arrive. */
export async function* sendTurn(conversationId: string, text: string): AsyncGenerator<TurnEvent> {
  const res = await api(`/api/conversations/${conversationId}/turns`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    body: JSON.stringify({ text }),
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
