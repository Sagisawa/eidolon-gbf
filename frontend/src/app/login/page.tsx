"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
import { FailureNotice } from "@/components/FailureNotice";
import {
  devLogin,
  getSignInOptions,
  listCharacters,
  type Character,
  type SignInOptions,
} from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { PROVIDER_LABELS, signInFailure, signInUrl } from "@/lib/signIn";

/** What visitors who are not signed in see: what this is, who there is to talk to, and
 * the ways to sign in. */
export default function LoginPage() {
  const [options, setOptions] = useState<SignInOptions | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    setRefusal(signInFailure(new URLSearchParams(window.location.search).get("error")));
    getSignInOptions().then(setOptions, (e) => setFailure(toFailure(e)));
    listCharacters().then(setCharacters, () => {}); // the showcase is only a nicety
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
    <main className="settings landing">
      <header className="landing-header">
        <h1>Eidolon-SC</h1>
        <p className="landing-lede">
          和《偶像大师 闪耀色彩》283 事务所的偶像们打电话、聊天。她们会用自己的声音回答你，
          记得原作里和制作人一起走过的事，也会记住你告诉她们的事。
        </p>
      </header>

      {refusal && (
        <p className="error" role="alert">
          {refusal}
        </p>
      )}

      <section className="field" aria-label="登录">
        {options?.providers.map((provider) => (
          <a key={provider} href={signInUrl(provider)} className="sign-in-button">
            用 {PROVIDER_LABELS[provider]} 登录
          </a>
        ))}
        {options && options.providers.length === 0 && !options.dev_login && (
          <p className="hint">部署者还没有配置登录方式。</p>
        )}
        <p className="hint">
          登录即表示你已阅读<Link href="/privacy">隐私政策</Link>和
          <Link href="/terms">使用条款</Link>。第一次登录时会请你确认一次。
        </p>
      </section>

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

      {characters.length > 0 && (
        <section className="field" aria-labelledby="cast">
          <h2 id="cast" className="section-title">
            可以说话的偶像
          </h2>
          <ul className="character-list">
            {characters.map((character) => (
              <li key={character.id} className="character-card">
                {character.avatar_url ? (
                  <img src={character.avatar_url} alt="" className="avatar" />
                ) : (
                  <span className="avatar placeholder" aria-hidden>
                    {character.name[0]}
                  </span>
                )}
                <span className="character-text">
                  <span className="character-name">{character.name}</span>
                  <span className="character-intro">{character.intro}</span>
                </span>
              </li>
            ))}
          </ul>
        </section>
      )}

      <footer className="landing-footer">
        <p className="hint">
          非官方的粉丝作品，与版权方无关。角色由 AI 扮演。 <Link href="/privacy">隐私政策</Link> ·{" "}
          <Link href="/terms">使用条款</Link>
        </p>
      </footer>
    </main>
  );
}
