"use client";

import Link from "next/link";
import { FormEvent, useState } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import { agreeToTerms, logout } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

/** Asked once, the first time a user signs in: nothing else works until they agree. */
export default function ConsentPage() {
  const [terms, setTerms] = useState(false);
  const [age, setAge] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      await agreeToTerms();
      window.location.assign("/");
    } catch (e) {
      setFailure(toFailure(e));
      setBusy(false);
    }
  }

  async function signOut() {
    await logout().catch(() => {});
    window.location.assign("/login");
  }

  return (
    <main className="settings">
      <header className="page-header">
        <h1>开始之前</h1>
      </header>

      <form className="field" onSubmit={submit}>
        <p>
          你和角色的对话、角色记下的关于你的事，会保存在这台服务器上，并交给第三方服务处理（语言模型、语音合成与识别等）。
          详情请看<Link href="/privacy">隐私政策</Link>和<Link href="/terms">使用条款</Link>。
        </p>
        <label className="check">
          <input type="checkbox" checked={terms} onChange={(e) => setTerms(e.target.checked)} />
          我已阅读并同意隐私政策和使用条款
        </label>
        <label className="check">
          <input type="checkbox" checked={age} onChange={(e) => setAge(e.target.checked)} />
          我已年满 13 岁
        </label>
        {failure && <FailureNotice failure={failure} />}
        <div className="field-row">
          <button type="submit" disabled={!terms || !age || busy}>
            同意并开始
          </button>
          <button type="button" className="ghost" onClick={signOut}>
            退出登录
          </button>
        </div>
        <p className="hint">不同意的话，退出登录即可；在你同意之前，不会保存任何对话。</p>
      </form>
    </main>
  );
}
