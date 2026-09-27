"use client";

import { useEffect, useState } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import {
  getAccount,
  getSignInOptions,
  logout,
  logoutEverywhere,
  unlinkSignInMethod,
  type Account,
  type SignInOptions,
} from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { PROVIDER_LABELS, linkUrl, signInFailure, type Provider } from "@/lib/signIn";

/** The identities the user signs in with, linking and unlinking them, and signing out. */
export function SignInSettings() {
  const [account, setAccount] = useState<Account | null>(null);
  const [options, setOptions] = useState<SignInOptions | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    // Coming back from linking an identity: say how it went.
    const params = new URLSearchParams(window.location.search);
    const linked = params.get("linked") as Provider | null;
    if (linked && linked in PROVIDER_LABELS) setNotice(`已绑定 ${PROVIDER_LABELS[linked]}。`);
    const refusal = signInFailure(params.get("error"));
    if (refusal) setFailure({ message: refusal, signedOut: false });
    getAccount().then(setAccount, (e) => setFailure(toFailure(e)));
    getSignInOptions().then(setOptions, () => {});
  }, []);

  async function unlink(provider: Provider) {
    setNotice(null);
    setFailure(null);
    try {
      await unlinkSignInMethod(provider);
      setAccount(await getAccount());
    } catch (e) {
      setFailure(toFailure(e));
    }
  }

  async function signOut(everywhere: boolean) {
    setFailure(null);
    try {
      await (everywhere ? logoutEverywhere() : logout());
      window.location.assign("/login");
    } catch (e) {
      setFailure(toFailure(e));
    }
  }

  const methods = account?.sign_in_methods ?? [];
  const linkable = (options?.providers ?? []).filter(
    (provider) => !methods.some((m) => m.provider === provider),
  );

  return (
    <div className="field">
      <label>登录方式</label>
      <p className="hint">
        绑定另一种登录方式后，用哪一种登录都是你，看到的是同一份记忆。邮箱相同的账号不会自动合并。
      </p>
      {notice && (
        <p className="hint" role="status">
          {notice}
        </p>
      )}
      {failure && <FailureNotice failure={failure} />}
      <ul className="sign-in-methods">
        {methods.map((method) => (
          <li key={method.provider}>
            <span>
              <strong>{PROVIDER_LABELS[method.provider]}</strong> {method.display_name}
              {method.email && <span className="hint"> {method.email}</span>}
            </span>
            <button
              type="button"
              className="ghost"
              disabled={methods.length <= 1}
              title={methods.length <= 1 ? "这是你唯一的登录方式，不能解绑" : undefined}
              onClick={() => unlink(method.provider)}
            >
              解绑
            </button>
          </li>
        ))}
      </ul>
      {linkable.map((provider) => (
        <a key={provider} href={linkUrl(provider)} className="ghost-link link-button">
          绑定 {PROVIDER_LABELS[provider]}
        </a>
      ))}
      <div className="field-row sign-out-row">
        <button type="button" className="ghost" onClick={() => signOut(false)}>
          退出登录
        </button>
        <button type="button" className="ghost" onClick={() => signOut(true)}>
          退出所有设备
        </button>
      </div>
    </div>
  );
}
