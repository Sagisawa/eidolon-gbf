"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { loadAccessKey, saveAccessKey } from "@/lib/accessKey";

export default function SettingsPage() {
  const [key, setKey] = useState("");
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    const stored = loadAccessKey();
    setKey(stored);
    setSaved(stored);
  }, []);

  function submit(event: FormEvent) {
    event.preventDefault();
    const trimmed = key.trim();
    saveAccessKey(trimmed);
    setKey(trimmed);
    setSaved(trimmed);
  }

  const dirty = saved !== null && key.trim() !== saved;

  return (
    <main className="settings">
      <header className="conversation-header">
        <h1>设置</h1>
        <Link href="/" className="ghost-link">
          返回对话
        </Link>
      </header>

      <form className="field" onSubmit={submit}>
        <label htmlFor="access-key">访问密钥</label>
        <p className="hint">由管理员发给你，以 esc_ 开头。只保存在这台设备的浏览器里。</p>
        <div className="field-row">
          <input
            id="access-key"
            type="password"
            value={key}
            onChange={(e) => setKey(e.target.value)}
            placeholder="esc_…"
            autoComplete="off"
            spellCheck={false}
          />
          <button type="submit" disabled={!dirty}>
            保存
          </button>
        </div>
        <p className="hint" role="status">
          {dirty ? "尚未保存" : saved ? "已保存" : "还没有填入访问密钥"}
        </p>
      </form>
    </main>
  );
}
