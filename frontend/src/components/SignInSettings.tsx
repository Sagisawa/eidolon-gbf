"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { Text } from "@astryxdesign/core/Text";
import { useEffect, useState } from "react";

import { FailureNotice } from "@/components/FailureNotice";
import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
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

const t = copy.settings.signIn;

/** 用户登录用的身份：绑定、解绑，以及退出登录。 */
export function SignInSettings() {
  const [account, setAccount] = useState<Account | null>(null);
  const [options, setOptions] = useState<SignInOptions | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    // 绑定完一个身份回到这里：说一声结果。
    const params = new URLSearchParams(window.location.search);
    const linked = params.get("linked") as Provider | null;
    if (linked && linked in PROVIDER_LABELS) setNotice(t.linked(PROVIDER_LABELS[linked]));
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
  const onlyOne = methods.length <= 1;

  return (
    <SettingsSection title={t.title} description={t.hint}>
      {notice && <Banner status="success" title={notice} isDismissable onDismiss={() => setNotice(null)} />}
      {failure && <FailureNotice failure={failure} />}
      {methods.length > 0 && (
        <List hasDividers>
          {methods.map((method) => (
            <ListItem
              key={method.provider}
              label={PROVIDER_LABELS[method.provider]}
              description={
                <Text color="secondary" wordBreak="break-word">
                  {method.email ? `${method.display_name} · ${method.email}` : method.display_name}
                </Text>
              }
              endContent={
                <Button
                  variant="ghost"
                  size="sm"
                  label={t.unlinkLabel(PROVIDER_LABELS[method.provider])}
                  isDisabled={onlyOne}
                  tooltip={onlyOne ? t.onlyMethod : undefined}
                  onClick={() => unlink(method.provider)}
                >
                  {t.unlink}
                </Button>
              }
            />
          ))}
        </List>
      )}
      {linkable.length > 0 && (
        <HStack gap={2} wrap="wrap">
          {linkable.map((provider) => (
            <Button key={provider} label={t.link(PROVIDER_LABELS[provider])} href={linkUrl(provider)} />
          ))}
        </HStack>
      )}
      {/* 退出登录和绑定是两件事，分开一行，窄屏换行时不会搅在一起 */}
      <HStack gap={2} wrap="wrap">
        <Button variant="ghost" label={t.signOut} onClick={() => signOut(false)} />
        <Button variant="ghost" label={t.signOutEverywhere} onClick={() => signOut(true)} />
      </HStack>
    </SettingsSection>
  );
}
