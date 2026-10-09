"use client";

import NextLink from "next/link";
import type { ReactNode } from "react";

import { Button } from "@/components/ui/button";
import { copy } from "@/i18n";
import { BackIcon } from "@/theme/icons";

type Props = {
  title: string;
  /** 返回键去哪里；不传就没有返回键。 */
  backHref?: string;
  /** 页首末端的操作。 */
  end?: ReactNode;
};

/** 页面里一节的标题：语义上是 h2，字号和页首标题一样（Header name），靠字重和留白分层。 */
export function SectionHeading({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <h2 id={id} className="text-header">
      {children}
    </h2>
  );
}

/** 设置、记忆、静态页的页首：返回键、标题和末端操作。放在 PageShell 的 header 里。 */
export function SubpageHeader({ title, backHref, end }: Props) {
  return (
    <div className="flex w-full items-center gap-2">
      {backHref && (
        <Button
          variant="ghost"
          size="icon-lg"
          aria-label={copy.common.back}
          nativeButton={false}
          render={<NextLink href={backHref} />}
          className="-ml-2"
        >
          <BackIcon />
        </Button>
      )}
      <h1 className="min-w-0 flex-1 truncate text-header">{title}</h1>
      {end}
    </div>
  );
}
