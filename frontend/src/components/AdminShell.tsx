"use client";

import { AppShell } from "@astryxdesign/core/AppShell";
import { SideNav, SideNavHeading, SideNavItem, SideNavSection } from "@astryxdesign/core/SideNav";
import NextLink from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { copy } from "@/i18n";
import { ADMIN_HREFS, ADMIN_PAGES, adminPage, type AdminPage } from "@/lib/admin";
import { BackIcon, ConfigIcon, DashboardIcon, UsersIcon } from "@/theme/icons";

const t = copy.admin;

const ICONS: Record<AdminPage, typeof DashboardIcon> = {
  dashboard: DashboardIcon,
  config: ConfigIcon,
  users: UsersIcon,
};

/**
 * 后台的外壳：Astryx AppShell 加侧边导航（看板、配置、用户）。电脑上侧栏常驻，
 * 窄屏下 AppShell 把侧栏收进抽屉，顶上留一个打开它的按钮。
 */
export function AdminShell({ name, children }: { name: string; children: ReactNode }) {
  const current = adminPage(usePathname());
  return (
    <AppShell
      variant="section"
      contentPadding={6}
      sideNav={
        <SideNav
          header={<SideNavHeading heading={t.title} subheading={t.signedInAs(name)} />}
          footer={<SideNavItem label={t.backToSettings} icon={BackIcon} href="/settings" as={NextLink} />}
        >
          <SideNavSection title={t.nav} isHeaderHidden>
            {ADMIN_PAGES.map((page) => (
              <SideNavItem
                key={page}
                label={t.pages[page]}
                icon={ICONS[page]}
                href={ADMIN_HREFS[page]}
                as={NextLink}
                isSelected={page === current}
              />
            ))}
          </SideNavSection>
        </SideNav>
      }
    >
      {children}
    </AppShell>
  );
}
