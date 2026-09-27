"use client";

import { Button } from "@astryxdesign/core/Button";
import { CheckboxInput } from "@astryxdesign/core/CheckboxInput";
import { HStack } from "@astryxdesign/core/HStack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { FormEvent, useState } from "react";

import { AppLink } from "@/components/AppLink";
import { FailureNotice } from "@/components/FailureNotice";
import { LegalFooter } from "@/components/LegalFooter";
import { PageShell } from "@/components/PageShell";
import { SubpageHeader } from "@/components/SubpageHeader";
import { copy } from "@/i18n";
import { interpolate } from "@/i18n/interpolate";
import { agreeToTerms, logout } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

const t = copy.consent;

/** 第一次登录时问一次：同意之前，别的都用不了。 */
export default function ConsentPage() {
  const [terms, setTerms] = useState(false);
  const [age, setAge] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      await agreeToTerms();
      window.location.assign("/");
    } catch (e) {
      setFailure(toFailure(e));
      setBusy(false);
    }
  }

  async function signOut() {
    await logout().catch(() => {});
    window.location.assign("/login");
  }

  return (
    <PageShell
      contentWidth={640}
      padding={4}
      header={<SubpageHeader title={t.title} />}
      footer={<LegalFooter />}
    >
      <form onSubmit={submit}>
        <VStack gap={6} paddingBlock={6}>
          <Text as="p">
            {interpolate(t.intro, {
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
          <VStack gap={3}>
            <CheckboxInput label={t.agreeTerms} value={terms} onChange={setTerms} />
            <CheckboxInput label={t.agreeAge} value={age} onChange={setAge} />
          </VStack>
          {failure && <FailureNotice failure={failure} />}
          <VStack gap={3}>
            <HStack gap={2} wrap="wrap">
              <Button type="submit" variant="primary" label={t.submit} isDisabled={!terms || !age} isLoading={busy} />
              <Button variant="ghost" label={t.signOut} onClick={signOut} />
            </HStack>
            <Text type="supporting" as="p">
              {t.declineHint}
            </Text>
          </VStack>
        </VStack>
      </form>
    </PageShell>
  );
}
