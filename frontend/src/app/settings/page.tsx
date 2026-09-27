"use client";

import { VStack } from "@astryxdesign/core/VStack";

import { AppLink } from "@/components/AppLink";
import { CallSettings } from "@/components/CallSettings";
import { DeleteAccount } from "@/components/DeleteAccount";
import { OwnKeysSettings } from "@/components/OwnKeysSettings";
import { PageShell } from "@/components/PageShell";
import { ProducerProfileSettings } from "@/components/ProducerProfileSettings";
import { SettingsSection } from "@/components/SettingsSection";
import { SignInSettings } from "@/components/SignInSettings";
import { SubpageHeader } from "@/components/SubpageHeader";
import { copy } from "@/i18n";

const t = copy.settings;

/**
 * 设置页：一栏，限宽 640（表单和文字不铺满，Astryx「Layout · Shell」），节与节之间用分隔线。
 * 手机和电脑同一个版式，只是电脑上两侧留白。
 */
export default function SettingsPage() {
  return (
    <PageShell contentWidth={640} padding={4} header={<SubpageHeader title={t.title} backHref="/" />}>
      <VStack>
        <ProducerProfileSettings />

        <SettingsSection title={t.memories.title} description={t.memories.hint}>
          <AppLink href="/memories" isStandalone hasUnderline>
            {t.memories.manage}
          </AppLink>
        </SettingsSection>

        <CallSettings />

        <OwnKeysSettings />

        <SignInSettings />

        <DeleteAccount />
      </VStack>
    </PageShell>
  );
}
