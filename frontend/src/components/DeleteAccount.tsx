"use client";

import { useState } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import { deleteAccount } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

/** Deleting all of the user's data, asked for twice. */
export function DeleteAccount() {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  async function remove() {
    setBusy(true);
    setFailure(null);
    try {
      await deleteAccount();
      window.location.assign("/login");
    } catch (e) {
      setFailure(toFailure(e));
      setBusy(false);
    }
  }

  return (
    <div className="field">
      <label>删除我的全部数据</label>
      <p className="hint">
        彻底删除你的记忆、对话、制作人档案、登录方式、自带密钥、会话和用量记录，无法恢复。所有设备都会退出登录；之后再用同一个账号登录，会是一位全新的用户。
      </p>
      {failure && <FailureNotice failure={failure} />}
      {confirming ? (
        <div className="field-row" role="alertdialog" aria-label="确认删除全部数据">
          <button type="button" className="danger" disabled={busy} onClick={remove}>
            {busy ? "正在删除…" : "确认删除，无法恢复"}
          </button>
          <button type="button" className="ghost" disabled={busy} onClick={() => setConfirming(false)}>
            取消
          </button>
        </div>
      ) : (
        <button type="button" className="danger" onClick={() => setConfirming(true)}>
          删除我的全部数据
        </button>
      )}
    </div>
  );
}
