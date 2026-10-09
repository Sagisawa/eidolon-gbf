"use client";

import NextLink from "next/link";

import { Alert, AlertAction, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { copy } from "@/i18n";
import type { Failure } from "@/lib/failure";
import { FailureIcon } from "@/theme/icons";

/**
 * 页面上的一次失败：照原话说明原因（PRODUCT.md「诚实说明状态」）；没登录时给出去登录的入口。
 * 用中性的 Alert 加警示图标，不用 destructive：挂断红只给挂断和真正执行删除、封禁的那一下（DESIGN.md「Tertiary」）。
 */
export function FailureNotice({ failure }: { failure: Failure }) {
  return (
    <Alert>
      <FailureIcon />
      <AlertTitle>{failure.message}</AlertTitle>
      {failure.signedOut && (
        <AlertAction>
          <SignInButton size="sm" />
        </AlertAction>
      )}
    </Alert>
  );
}

/** 没登录时去登录页的按钮。 */
export function SignInButton({ size }: { size?: "sm" }) {
  return (
    <Button size={size} nativeButton={false} render={<NextLink href="/login" />}>
      {copy.failure.signIn}
    </Button>
  );
}
