"use client";

import NextLink from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import {
  Breadcrumb,
  BreadcrumbItem,
  BreadcrumbLink,
  BreadcrumbList,
  BreadcrumbPage,
  BreadcrumbSeparator,
} from "@/components/ui/breadcrumb";
import { Separator } from "@/components/ui/separator";
import {
  Sidebar,
  SidebarContent,
  SidebarFooter,
  SidebarGroup,
  SidebarGroupContent,
  SidebarHeader,
  SidebarInset,
  SidebarMenu,
  SidebarMenuButton,
  SidebarMenuItem,
  SidebarProvider,
  SidebarTrigger,
} from "@/components/ui/sidebar";
import { copy } from "@/i18n";
import { ADMIN_HREFS, ADMIN_PAGES, adminPage, type AdminPage } from "@/lib/admin";
import { BackIcon, ConfigIcon, DashboardIcon, UsersIcon } from "@/theme/icons";

const t = copy.admin;

const ICONS: Record<AdminPage, typeof DashboardIcon> = {
  dashboard: DashboardIcon,
  config: ConfigIcon,
  users: UsersIcon,
};

type Props = {
  name: string;
  /** 面包屑在「后台 › 当前页」后面再接的一级，例如用户详情里的用户名。 */
  trail?: string;
  children: ReactNode;
};

/**
 * 后台的外壳（DESIGN.md「Layout · 后台」）：shadcn Sidebar（16rem），头部「后台」和「管理者：{name}」，
 * 菜单「看板 / 配置 / 用户」，底部「返回设置」；窄屏（< 768px）侧栏收进 Sheet。
 * 内容区顶上一条 48px 的页首：SidebarTrigger、细竖线、面包屑。各页的内容列由 AdminPage 限宽。
 */
export function AdminShell({ name, trail, children }: Props) {
  const current = adminPage(usePathname());
  return (
    <SidebarProvider>
      <Sidebar aria-label={t.nav}>
        <SidebarHeader className="px-4 py-3">
          <p className="text-sm font-semibold">{t.title}</p>
          <p className="truncate text-xs text-muted-foreground">{t.signedInAs(name)}</p>
        </SidebarHeader>
        <SidebarContent>
          <SidebarGroup>
            <SidebarGroupContent>
              <SidebarMenu>
                {ADMIN_PAGES.map((page) => {
                  const Icon = ICONS[page];
                  return (
                    <SidebarMenuItem key={page}>
                      <SidebarMenuButton isActive={page === current} render={<NextLink href={ADMIN_HREFS[page]} />}>
                        <Icon />
                        <span>{t.pages[page]}</span>
                      </SidebarMenuButton>
                    </SidebarMenuItem>
                  );
                })}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter>
          <SidebarMenu>
            <SidebarMenuItem>
              <SidebarMenuButton render={<NextLink href="/settings" />}>
                <BackIcon />
                <span>{t.backToSettings}</span>
              </SidebarMenuButton>
            </SidebarMenuItem>
          </SidebarMenu>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <header className="flex h-12 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger aria-label={t.toggleNav} className="-ml-1" />
          <Separator orientation="vertical" className="mr-1 data-[orientation=vertical]:h-4" />
          <Breadcrumb aria-label={t.breadcrumb}>
            <BreadcrumbList>
              <BreadcrumbItem>{t.title}</BreadcrumbItem>
              <BreadcrumbSeparator />
              <BreadcrumbItem>
                {trail ? (
                  <BreadcrumbLink render={<NextLink href={ADMIN_HREFS[current]} />}>{t.pages[current]}</BreadcrumbLink>
                ) : (
                  <BreadcrumbPage>{t.pages[current]}</BreadcrumbPage>
                )}
              </BreadcrumbItem>
              {trail && (
                <>
                  <BreadcrumbSeparator />
                  <BreadcrumbItem>
                    <BreadcrumbPage>{trail}</BreadcrumbPage>
                  </BreadcrumbItem>
                </>
              )}
            </BreadcrumbList>
          </Breadcrumb>
        </header>
        {children}
      </SidebarInset>
    </SidebarProvider>
  );
}
