"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { StackItem } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { VStack } from "@astryxdesign/core/VStack";
import { FormEvent, useEffect, useState } from "react";

import { AppLink } from "@/components/AppLink";
import { FailureNotice } from "@/components/FailureNotice";
import { LegalFooter } from "@/components/LegalFooter";
import { MarkedAvatar } from "@/components/MarkedAvatar";
import { PageShell } from "@/components/PageShell";
import { SectionHeading } from "@/components/SubpageHeader";
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

  return (
    <PageShell contentWidth={640} padding={4} footer={<LegalFooter />}>
      <VStack gap={8} paddingBlock={8}>
        <VStack gap={3}>
          <Heading level={1}>{copy.app.name}</Heading>
          <Text as="p">{t.lede}</Text>
        </VStack>

        {refusal && (
          <Banner
            status="error"
            title={t.refusedTitle}
            description={signInFailure(refusal, options?.contact) ?? undefined}
          />
        )}

        <VStack as="section" aria-label={t.signInRegion} gap={3} maxWidth={360}>
          {options?.providers.map((provider, i) => (
            <Button
              key={provider}
              label={t.signInWith(PROVIDER_LABELS[provider])}
              href={signInUrl(provider)}
              variant={i === 0 ? "primary" : "secondary"}
              size="lg"
              width="100%"
            />
          ))}
          {options && options.providers.length === 0 && !options.dev_login && (
            <Text color="secondary">{t.noProviders}</Text>
          )}
          <Text type="supporting" as="p">
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
          </Text>
        </VStack>

        {options?.dev_login && (
          <form onSubmit={submit}>
            <VStack gap={3} maxWidth={360}>
              <VStack gap={1}>
                <SectionHeading>{t.devTitle}</SectionHeading>
                <Text color="secondary">{t.devHint}</Text>
              </VStack>
              <HStack gap={2} vAlign="end">
                <StackItem size="fill">
                  <TextInput label={t.devName} isLabelHidden value={name} onChange={setName} />
                </StackItem>
                <Button type="submit" label={t.devSubmit} isDisabled={!name.trim()} />
              </HStack>
            </VStack>
          </form>
        )}

        {failure && <FailureNotice failure={failure} />}

        {characters.length > 0 && (
          <List
            header={<SectionHeading>{t.castTitle}</SectionHeading>}
            density="spacious"
          >
            {characters.map((character) => (
              <ListItem
                key={character.id}
                label={character.name}
                description={<Text color="secondary">{character.intro}</Text>}
                startContent={
                  <MarkedAvatar name={character.name} src={character.avatar_url} color={character.color} />
                }
              />
            ))}
          </List>
        )}
      </VStack>
    </PageShell>
  );
}
