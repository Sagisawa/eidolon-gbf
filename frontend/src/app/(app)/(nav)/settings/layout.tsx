"use client";

import { usePathname } from "next/navigation";
import { Fragment, type ReactNode } from "react";

import { SettingsRow } from "@/components/settings/SettingsRow";
import { Separator } from "@/components/ui/separator";
import { copy } from "@/i18n";
import { SETTINGS_GROUPS, settingsCategory, settingsHref, shownCategory } from "@/lib/settingsCategory";
import { cn } from "@/lib/utils";
import { AboutIcon, MemoriesIcon, OwnKeysIcon, PhoneIcon, ProfileIcon, SignInIcon } from "@/theme/icons";

const t = copy.settings;

const ICONS = {
  profile: ProfileIcon,
  memories: MemoriesIcon,
  call: PhoneIcon,
  "own-keys": OwnKeysIcon,
  "sign-in": SignInIcon,
  about: AboutIcon,
};

/**
 * 设置（DESIGN.md「设置页」）：一级是六类的列表，分四组、组间一条分隔线；二级是一类的页面（`/settings/<类别>`），没有三级。
 * - 电脑：导航栏右边第二栏 320px 的一级列表，顶上「设置」大标题，当前那一类铺中性底色、不带 ›；右栏是这一类的二级页面。
 *   只打开 `/settings` 时右栏是档案，档案是当前项。
 * - 手机：`/settings` 只露一级列表，每行末尾一个 ›；`/settings/<类别>` 只露二级页面，页首返回键回到一级。
 * 两种屏宽同一套路由，露哪一级只靠 CSS 断点，首屏不闪。
 */
export default function SettingsLayout({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const isFirstLevel = settingsCategory(pathname) === null;
  const current = shownCategory(pathname);

  return (
    <div className="flex h-full bg-background text-foreground">
      <nav
        aria-label={t.title}
        className={cn(
          "flex w-80 shrink-0 flex-col border-r max-md:w-full max-md:border-r-0",
          !isFirstLevel && "max-md:hidden",
        )}
      >
        <header className="flex min-h-14 shrink-0 items-center pt-3 pr-2 pb-2 pl-4">
          <h1 className="text-list-title">{t.title}</h1>
        </header>
        <div className="min-h-0 flex-1 overflow-y-auto pb-4">
          {SETTINGS_GROUPS.map((group, i) => (
            <Fragment key={group[0]}>
              {i > 0 && <Separator className="my-1" />}
              <ul>
                {group.map((category) => (
                  <li key={category}>
                    <SettingsRow
                      href={settingsHref(category)}
                      label={t.categories[category]}
                      Icon={ICONS[category]}
                      isCurrent={category === current}
                    />
                  </li>
                ))}
              </ul>
            </Fragment>
          ))}
        </div>
      </nav>
      <div className={cn("min-w-0 flex-1", isFirstLevel && "max-md:hidden")}>{children}</div>
    </div>
  );
}
