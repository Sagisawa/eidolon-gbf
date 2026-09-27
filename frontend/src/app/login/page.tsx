"use client";

import { FormEvent, useState } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import { devLogin } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

/** For now, signing in by name with the backend's development switch on. */
export default function LoginPage() {
  const [name, setName] = useState("");
  const [failure, setFailure] = useState<Failure | null>(null);

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
      <form className="field" onSubmit={submit}>
        <label htmlFor="dev-name">开发登录</label>
        <p className="hint">后端设置了 EIDOLON_DEV_LOGIN=1 时，可以直接以这个名字的用户登录。</p>
        <div className="field-row">
          <input id="dev-name" value={name} onChange={(e) => setName(e.target.value)} />
          <button type="submit" disabled={!name.trim()}>
            登录
          </button>
        </div>
        {failure && <FailureNotice failure={failure} />}
      </form>
    </main>
  );
}
