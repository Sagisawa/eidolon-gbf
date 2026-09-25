import { loadAccessKey } from "@/lib/accessKey";

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

export type TurnEvent =
  | { type: "delta"; segment: number; lang: "ja" | "zh"; text: string }
  | { type: "done"; message: Message }
  | { type: "error"; message: string };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
  }

  /** The access key is missing, invalid or revoked. */
  get unauthorized(): boolean {
    return this.status === 401;
  }
}

async function json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new ApiError(body?.detail ?? `请求失败（${res.status}）`, res.status);
  }
  return res.json();
}

/** fetch() for the backend API, carrying the access key saved on the settings page. */
function api(path: string, init: RequestInit = {}): Promise<Response> {
  const headers = new Headers(init.headers);
  const key = loadAccessKey();
  if (key) headers.set("authorization", `Bearer ${key}`);
  return fetch(path, { ...init, headers });
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
