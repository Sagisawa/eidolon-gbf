"use client";

import { FormEvent, useEffect, useState } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import { devLogin, getSignInOptions, type SignInOptions } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { PROVIDER_LABELS, signInFailure, signInUrl } from "@/lib/signIn";

export default function LoginPage() {
  const [options, setOptions] = useState<SignInOptions | null>(null);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    setRefusal(signInFailure(new URLSearchParams(window.location.search).get("error")));
    getSignInOptions().then(setOptions, (e) => setFailure(toFailure(e)));
  }, []);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setFailure(null);
    try {
      await devLogin(name.trim());
      window.location.assign("/");
    } catch (e) {
      setFailure(toFailure(e));
    }
  }

  return (
    <main className="settings">
      <header className="page-header">
        <h1>登录</h1>
      </header>

      {refusal && (
        <p className="error" role="alert">
          {refusal}
        </p>
      )}

      <div className="field">
        {options?.providers.map((provider) => (
          <a key={provider} href={signInUrl(provider)} className="sign-in-button">
            用 {PROVIDER_LABELS[provider]} 登录
          </a>
        ))}
        {options && options.providers.length === 0 && !options.dev_login && (
          <p className="hint">部署者还没有配置登录方式。</p>
        )}
      </div>

      {options?.dev_login && (
        <form className="field" onSubmit={submit}>
          <label htmlFor="dev-name">开发登录</label>
          <p className="hint">后端打开了 EIDOLON_DEV_LOGIN，可以直接以这个名字的用户登录。</p>
          <div className="field-row">
            <input id="dev-name" value={name} onChange={(e) => setName(e.target.value)} />
            <button type="submit" disabled={!name.trim()}>
              登录
            </button>
          </div>
        </form>
      )}

      {failure && <FailureNotice failure={failure} />}
    </main>
  );
}
