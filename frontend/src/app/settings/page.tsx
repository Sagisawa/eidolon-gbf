"use client";

import { AdminEntry } from "@/components/AdminEntry";
import { AppLink } from "@/components/app/AppLink";
import { PageShell } from "@/components/app/PageShell";
import { SettingsSection } from "@/components/app/SettingsSection";
import { SubpageHeader } from "@/components/app/SubpageHeader";
import { CallSettings } from "@/components/CallSettings";
import { DeleteAccount } from "@/components/DeleteAccount";
import { OwnKeysSettings } from "@/components/OwnKeysSettings";
import { ProducerProfileSettings } from "@/components/ProducerProfileSettings";
import { SignInSettings } from "@/components/SignInSettings";
import { copy } from "@/i18n";

const t = copy.settings;

/**
 * 设置页：一栏，限宽 640（表单和文字不铺满），一节一节靠分隔线和留白分开。
 * 手机和电脑同一个版式，只是电脑上两侧留白。
 */
export default function SettingsPage() {
  return (
    <PageShell header={<SubpageHeader title={t.title} backHref="/" />}>
      <ProducerProfileSettings />

      <SettingsSection title={t.memories.title} description={t.memories.hint}>
        <AppLink href="/memories" isStandalone className="self-start">
          {t.memories.manage}
        </AppLink>
      </SettingsSection>

      <CallSettings />

      <OwnKeysSettings />

      <SignInSettings />

      <AdminEntry />

      <DeleteAccount />
    </PageShell>
  );
}
