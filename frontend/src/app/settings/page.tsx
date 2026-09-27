"use client";

import Link from "next/link";
import { CallSettings } from "@/components/CallSettings";
import { DeleteAccount } from "@/components/DeleteAccount";
import { OwnKeysSettings } from "@/components/OwnKeysSettings";
import { ProducerProfileSettings } from "@/components/ProducerProfileSettings";
import { SignInSettings } from "@/components/SignInSettings";

export default function SettingsPage() {
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

      <OwnKeysSettings />

      <SignInSettings />

      <DeleteAccount />
    </main>
  );
}
