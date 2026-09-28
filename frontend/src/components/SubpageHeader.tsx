"use client";

import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { StackItem } from "@astryxdesign/core/Stack";
import NextLink from "next/link";
import type { ReactNode } from "react";

import { copy } from "@/i18n";
import { BackIcon } from "@/theme/icons";

type Props = {
  title: string;
  /** 返回键去哪里；不传就没有返回键。 */
  backHref?: string;
  /** 页首末端的操作。 */
  end?: ReactNode;
};

/** 页面里一节的标题：语义上是 h2，字号和页首标题一样用 Title（DESIGN.md「Typography」），靠字重和留白分层。 */
export function SectionHeading({ children, id }: { children: ReactNode; id?: string }) {
  return (
    <Heading level={2} id={id} style={{ fontSize: "var(--text-large-size)" }}>
      {children}
    </Heading>
  );
}

/** 设置、记忆、静态页的页首：返回键、标题（Title 字号，DESIGN.md「Typography」）和末端操作。 */
export function SubpageHeader({ title, backHref, end }: Props) {
  return (
    <HStack vAlign="center" gap={3}>
      {backHref && (
        <Button
          label={copy.common.back}
          icon={<BackIcon />}
          isIconOnly
          variant="ghost"
          href={backHref}
          as={NextLink}
        />
      )}
      <StackItem size="fill">
        <Heading level={1} style={{ fontSize: "var(--text-large-size)" }}>
          {title}
        </Heading>
      </StackItem>
      {end}
    </HStack>
  );
}
