import type { ReactNode } from "react";

import { AboutSettings } from "@/components/AboutSettings";
import { AdminEntry } from "@/components/AdminEntry";
import { CallSettings } from "@/components/CallSettings";
import { DeleteAccount } from "@/components/DeleteAccount";
import { MemoriesSettings } from "@/components/MemoriesSettings";
import { OwnKeysSettings } from "@/components/OwnKeysSettings";
import { ProducerProfileSettings } from "@/components/ProducerProfileSettings";
import { SettingsPane } from "@/components/settings/SettingsPane";
import { SignInSettings } from "@/components/SignInSettings";
import { SignOutSettings } from "@/components/SignOutSettings";
import type { SettingsCategory } from "@/lib/settingsCategory";

/** 各类二级页面的内容，按 spec「设置：二级」。记忆自己带页首末端的「清空」，整页由它画。 */
const PANELS: Record<Exclude<SettingsCategory, "memories">, ReactNode> = {
  profile: <ProducerProfileSettings />,
  call: <CallSettings />,
  "own-keys": <OwnKeysSettings />,
  "sign-in": (
    <>
      <SignInSettings />
      <AdminEntry />
      <SignOutSettings />
      <DeleteAccount />
    </>
  ),
  about: <AboutSettings />,
};

/** 设置一类的二级页面。 */
export function SettingsCategoryPage({ category }: { category: SettingsCategory }) {
  if (category === "memories") return <MemoriesSettings />;
  return <SettingsPane category={category}>{PANELS[category]}</SettingsPane>;
}
