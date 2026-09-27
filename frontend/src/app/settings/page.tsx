"use client";

import Link from "next/link";
import { useState } from "react";
import { CallSettings } from "@/components/CallSettings";
import { FailureNotice } from "@/components/FailureNotice";
import { ProducerProfileSettings } from "@/components/ProducerProfileSettings";
import { logout } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

export default function SettingsPage() {
  const [failure, setFailure] = useState<Failure | null>(null);

  async function signOut() {
    setFailure(null);
    try {
      await logout();
      window.location.assign("/login");
    } catch (e) {
      setFailure(toFailure(e));
    }
  }

  return (
    <main className="settings">
      <header className="page-header">
        <h1>设置</h1>
        <Link href="/" className="ghost-link">
          返回
        </Link>
      </header>

      <ProducerProfileSettings />

      <div className="field">
        <label>记忆</label>
        <p className="hint">查看角色们记下的关于你的事，可以逐条删除或全部清空。</p>
        <Link href="/memories" className="ghost-link">
          管理记忆
        </Link>
      </div>

      <CallSettings />

      <div className="field">
        <label>登录</label>
        {failure && <FailureNotice failure={failure} />}
        <div className="field-row">
          <button type="button" className="ghost" onClick={signOut}>
            退出登录
          </button>
        </div>
      </div>
    </main>
  );
}
