"use client";

import { useEffect, useState } from "react";

import { AppLink } from "@/components/app/AppLink";
import { SettingsSection } from "@/components/app/SettingsSection";
import { copy } from "@/i18n";
import { getAccount } from "@/lib/api";

const t = copy.settings.admin;

/** 设置页里进入后台的入口：只有管理者看得到，其他人这一节整个不出现。 */
export function AdminEntry() {
  const [isAdmin, setIsAdmin] = useState(false);

  useEffect(() => {
    getAccount().then((account) => setIsAdmin(account.is_admin), () => {});
  }, []);

  if (!isAdmin) return null;
  return (
    <SettingsSection title={t.title} description={t.hint}>
      <AppLink href="/admin" isStandalone className="self-start">
        {t.enter}
      </AppLink>
    </SettingsSection>
  );
}
