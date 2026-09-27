import type { Provider } from "@/lib/signIn";
import { detectTimezone } from "@/lib/timezone";

export type Character = {
  id: string;
  name: string;
  intro: string;
  avatar_url: string | null;
};

export type Conversation = {
  id: string;
  character_id: string;
  created_at: string;
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

/** A turn's events: `user`, then any `delta`s, then `done` or `error`. */
export type TurnEvent =
  | { type: "user"; text: string }
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

/** During a call each utterance, spoken or typed, is a turn; the backend also says, when the
 * call reaches its time or turn limit, why it is about to hang up. */
export type CallEvent = TurnEvent | { type: "ended"; message: string };

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

/** fetch() for the backend API; sends the browser on when it has to sign in first. */
async function api(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(path, { ...init, headers: apiHeaders(init.headers) });
  const to = redirectFor(res.status);
  if (to && window.location.pathname !== to) window.location.assign(to);
  return res;
}

/** The ways to sign in the backend offers. */
export type SignInOptions = { providers: Provider[]; dev_login: boolean };

export async function getSignInOptions(): Promise<SignInOptions> {
  return json(await fetch("/api/auth/providers"));
}

/** An identity the user signs in with. */
export type SignInMethod = { provider: Provider; display_name: string; email: string | null };

export type Account = { name: string; sign_in_methods: SignInMethod[] };

/** The signed-in user; sends the browser to sign in, or to agree to the terms, first. */
export async function getAccount(): Promise<Account> {
  return json(await api("/api/account"));
}

/** Stop signing in with the identity at `provider`; refused for the last one. */
export async function unlinkSignInMethod(provider: Provider): Promise<void> {
  await expectNoContent(await api(`/api/account/sign-in-methods/${provider}`, { method: "DELETE" }));
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

/** The STUN/TURN servers for a call; fails with the reason when calls are unavailable. */
export async function getIceServers(): Promise<RTCIceServer[]> {
  const body = await json<{ iceServers: RTCIceServer[] }>(await api("/api/ice-servers"));
  return body.iceServers;
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
