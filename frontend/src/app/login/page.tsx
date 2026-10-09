"use client";

import { FormEvent, useEffect, useState } from "react";

import { AppLink } from "@/components/app/AppLink";
import { FailureNotice } from "@/components/app/FailureNotice";
import { MarkedAvatar } from "@/components/app/MarkedAvatar";
import { PageShell } from "@/components/app/PageShell";
import { SectionHeading } from "@/components/app/SubpageHeader";
import { LegalFooter } from "@/components/LegalFooter";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { copy } from "@/i18n";
import { interpolate } from "@/i18n/interpolate";
import {
  devLogin,
  getSignInOptions,
  listCharacters,
  type Character,
  type SignInOptions,
} from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { PROVIDER_LABELS, signInFailure, signInUrl } from "@/lib/signIn";
import { FailureIcon } from "@/theme/icons";

const t = copy.login;

/** 没登录的访客看到的页面：这是什么、有哪些偶像可以说话、怎样登录。 */
export default function LoginPage() {
  const [options, setOptions] = useState<SignInOptions | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [refusal, setRefusal] = useState<string | null>(null);
  const [name, setName] = useState("");
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    setRefusal(new URLSearchParams(window.location.search).get("error"));
    getSignInOptions().then(setOptions, (e) => setFailure(toFailure(e)));
    // 角色名单随 characters.toml 变化，从后端取；取不到只是少了展示，不算失败。
    listCharacters().then(setCharacters, () => {});
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

  const refusalText = refusal ? signInFailure(refusal, options?.contact) : null;

  return (
    <PageShell footer={<LegalFooter />}>
      <div className="flex flex-col gap-8 py-2">
        <div className="flex flex-col gap-3">
          <h1 className="text-list-title">{copy.app.name}</h1>
          <p className="text-body">{t.lede}</p>
        </div>

        {/* 登录被拒绝：和 FailureNotice 一样用中性的 Alert 加警示图标，挂断红只给挂断和删除、封禁（DESIGN.md「Tertiary」）。 */}
        {refusal && (
          <Alert>
            <FailureIcon />
            <AlertTitle>{t.refusedTitle}</AlertTitle>
            {refusalText && <AlertDescription>{refusalText}</AlertDescription>}
          </Alert>
        )}

        <section aria-label={t.signInRegion} className="flex max-w-90 flex-col gap-3">
          {options?.providers.map((provider, i) => (
            // 登录要整页跳到后端的 OAuth 入口，用普通的 <a>，不走客户端路由。
            <Button
              key={provider}
              variant={i === 0 ? "default" : "outline"}
              size="lg"
              nativeButton={false}
              render={<a href={signInUrl(provider)} />}
              className="w-full"
            >
              {t.signInWith(PROVIDER_LABELS[provider])}
            </Button>
          ))}
          {options && options.providers.length === 0 && !options.dev_login && (
            <p className="text-body text-muted-foreground">{t.noProviders}</p>
          )}
          <p className="text-sm text-muted-foreground">
            {interpolate(t.agreement, {
              privacy: (
                <AppLink key="privacy" href="/privacy">
                  {copy.legal.privacy}
                </AppLink>
              ),
              terms: (
                <AppLink key="terms" href="/terms">
                  {copy.legal.terms}
                </AppLink>
              ),
            })}
          </p>
        </section>

        {options?.dev_login && (
          <form onSubmit={submit} className="flex max-w-90 flex-col gap-3">
            <div className="flex flex-col gap-1">
              <SectionHeading>{t.devTitle}</SectionHeading>
              <p className="text-body text-muted-foreground">{t.devHint}</p>
            </div>
            <div className="flex items-center gap-2">
              <Input aria-label={t.devName} value={name} onChange={(e) => setName(e.target.value)} className="flex-1" />
              <Button type="submit" disabled={!name.trim()}>
                {t.devSubmit}
              </Button>
            </div>
          </form>
        )}

        {failure && <FailureNotice failure={failure} />}

        {characters.length > 0 && (
          <section className="flex flex-col gap-2">
            <SectionHeading>{t.castTitle}</SectionHeading>
            {/* 偶像名单是行，不套卡片（DESIGN.md「Conversation list」）。 */}
            <ul className="flex flex-col">
              {characters.map((character) => (
                <li key={character.id} className="flex items-center gap-3 py-3">
                  <MarkedAvatar name={character.name} src={character.avatar_url} />
                  <div className="flex min-w-0 flex-col gap-0.5">
                    <span className="text-row-name">{character.name}</span>
                    <span className="text-sm text-muted-foreground">{character.intro}</span>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        )}
      </div>
    </PageShell>
  );
}
