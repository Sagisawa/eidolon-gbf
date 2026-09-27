"use client";

import { FormEvent, useEffect, useState } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import {
  deleteOwnKey,
  getOwnKeys,
  saveOwnLLM,
  type LLMProtocol,
  type OwnKeys,
  type OwnService,
} from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

const PROTOCOL_LABELS: Record<LLMProtocol, string> = {
  "chat-completions": "OpenAI 兼容（Chat Completions）",
  responses: "OpenAI Responses",
  anthropic: "Anthropic Messages",
};

/** The keys the user brings to pay for their own use; hidden unless the deployment
 * allows it. */
export function OwnKeysSettings() {
  const [keys, setKeys] = useState<OwnKeys | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    getOwnKeys().then(setKeys, (e) => setFailure(toFailure(e)));
  }, []);

  async function remove(service: OwnService) {
    setFailure(null);
    try {
      await deleteOwnKey(service);
      setKeys(await getOwnKeys());
    } catch (e) {
      setFailure(toFailure(e));
    }
  }

  if (failure && !keys) return <FailureNotice failure={failure} />;
  if (!keys?.available) return null;

  return (
    <div className="field">
      <label>自带密钥</label>
      <p className="hint">
        填了自己的 API key，这一项服务就改用你的额度，费用由你承担。自带的密钥调用失败时，这一轮会失败并提示是哪一项出了问题，不会改用部署者的密钥。界面上只显示密钥的末
        4 位。
      </p>
      {failure && <FailureNotice failure={failure} />}
      <OwnLLMForm
        current={keys.keys.llm}
        protocols={keys.protocols}
        onSaved={async () => setKeys(await getOwnKeys())}
        onDelete={() => remove("llm")}
      />
    </div>
  );
}

function OwnLLMForm({
  current,
  protocols,
  onSaved,
  onDelete,
}: {
  current: OwnKeys["keys"]["llm"];
  protocols: LLMProtocol[];
  onSaved: () => Promise<void>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [baseUrl, setBaseUrl] = useState(current?.base_url ?? "");
  const [model, setModel] = useState(current?.model ?? "");
  const [protocol, setProtocol] = useState<LLMProtocol>(current?.protocol ?? "chat-completions");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      await saveOwnLLM({ base_url: baseUrl.trim(), api_key: apiKey.trim(), model: model.trim(), protocol });
      setApiKey("");
      setEditing(false);
      await onSaved();
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="own-key">
      <h3 className="own-key-title">LLM（扮演角色、记住你说的事）</h3>
      <p className="hint">小模型会降低角色扮演和记忆的质量。模型需要支持流式输出和工具调用，保存前会先试调一次。</p>
      {current && !editing && (
        <div className="field-row own-key-current">
          <span>
            {current.model} · {current.base_url} · 密钥末 4 位 {current.last4}
          </span>
          <button type="button" className="ghost" onClick={() => setEditing(true)}>
            修改
          </button>
          <button type="button" className="ghost" onClick={onDelete}>
            删除
          </button>
        </div>
      )}
      {(!current || editing) && (
        <form onSubmit={submit} className="own-key-form">
          <label htmlFor="llm-protocol">接口类型</label>
          <select
            id="llm-protocol"
            value={protocol}
            onChange={(e) => setProtocol(e.target.value as LLMProtocol)}
          >
            {protocols.map((p) => (
              <option key={p} value={p}>
                {PROTOCOL_LABELS[p]}
              </option>
            ))}
          </select>
          <label htmlFor="llm-base-url">接口地址（base_url）</label>
          <input
            id="llm-base-url"
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            placeholder="https://api.openai.com/v1"
            spellCheck={false}
          />
          <label htmlFor="llm-model">模型名</label>
          <input id="llm-model" value={model} onChange={(e) => setModel(e.target.value)} spellCheck={false} />
          <label htmlFor="llm-key">API key</label>
          <input
            id="llm-key"
            type="password"
            value={apiKey}
            onChange={(e) => setApiKey(e.target.value)}
            autoComplete="off"
            spellCheck={false}
          />
          {failure && <FailureNotice failure={failure} />}
          <div className="field-row">
            <button type="submit" disabled={busy || !baseUrl.trim() || !model.trim() || !apiKey.trim()}>
              {busy ? "正在试调…" : "试调并保存"}
            </button>
            {editing && (
              <button type="button" className="ghost" onClick={() => setEditing(false)}>
                取消
              </button>
            )}
          </div>
        </form>
      )}
    </div>
  );
}
