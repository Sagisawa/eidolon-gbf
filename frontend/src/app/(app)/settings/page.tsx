"use client";

import { useSearchParams } from "next/navigation";
import { Suspense, type ReactNode } from "react";

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
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { copy } from "@/i18n";
import { SETTINGS_TABS, settingsTab, settingsTabSearch, type SettingsTab } from "@/lib/settingsTab";

const t = copy.settings;

/**
 * 设置页：一栏，限宽 640（表单和文字不铺满），顶上四个标签，一次只显示一组（DESIGN.md「设置页」）。
 * 手机和电脑同一个版式，只是电脑上两侧留白。
 */
export default function SettingsPage() {
  return (
    <PageShell header={<SubpageHeader title={t.title} backHref="/conversations" />}>
      {/* 读地址参数的部分在预渲染时等到浏览器里才渲染，按 Next 的要求包一层 Suspense。 */}
      <Suspense fallback={null}>
        <SettingsTabs />
      </Suspense>

      {/* 回去看落地页（/about）：已登录也不会被送走，入口是「继续」。不归哪一组，哪个标签下都在最后。 */}
      <div className="py-6">
        <AppLink href="/about" isStandalone>
          {t.about}
        </AppLink>
      </div>
    </PageShell>
  );
}

/**
 * 四个标签。当前标签记在地址里（lib/settingsTab）；切换时替换当前历史记录、不滚动，按返回直接回对话。
 * 面板切走后保持挂载：没保存的档案、填到一半的表单都留着，切回来也不重新读取。
 */
function SettingsTabs() {
  const params = useSearchParams();

  function select(tab: SettingsTab) {
    // 原生 replaceState 跟 Next 的路由同步（useSearchParams 会更新），不请求、不滚动。
    window.history.replaceState(null, "", settingsTabSearch(params, tab));
  }

  return (
    <Tabs value={settingsTab(params)} onValueChange={(tab) => select(tab as SettingsTab)} className="gap-0">
      {/* 吸在页首下面，铺实底，免得内容从下面透上来。 */}
      <div className="sticky top-0 z-10 border-b bg-background">
        <TabsList variant="line" className="w-full gap-0">
          {SETTINGS_TABS.map((tab) => (
            <TabsTrigger key={tab} value={tab}>
              {t.tabs[tab]}
            </TabsTrigger>
          ))}
        </TabsList>
      </div>

      {SETTINGS_TABS.map((tab) => (
        <TabsContent key={tab} value={tab} keepMounted>
          {PANELS[tab]}
        </TabsContent>
      ))}
    </Tabs>
  );
}

/** 各组的内容，按 spec「各组的内容和顺序」。 */
const PANELS: Record<SettingsTab, ReactNode> = {
  profile: (
    <>
      <ProducerProfileSettings />
      <SettingsSection title={t.memories.title} description={t.memories.hint}>
        <AppLink href="/memories" isStandalone className="self-start">
          {t.memories.manage}
        </AppLink>
      </SettingsSection>
    </>
  ),
  call: <CallSettings />,
  "own-keys": <OwnKeysSettings />,
  "sign-in": (
    <>
      <SignInSettings />
      <AdminEntry />
      <DeleteAccount />
    </>
  ),
};
