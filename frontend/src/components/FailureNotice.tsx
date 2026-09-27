"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import NextLink from "next/link";

import { copy } from "@/i18n";
import type { Failure } from "@/lib/failure";

/** 页面上的一次失败：照原话说明原因（PRODUCT.md「诚实说明状态」）；没登录时给出去登录的入口。 */
export function FailureNotice({ failure }: { failure: Failure }) {
  return (
    <Banner
      status="error"
      title={failure.message}
      endContent={
        failure.signedOut ? (
          <Button label={copy.failure.signIn} href="/login" as={NextLink} size="sm" />
        ) : undefined
      }
    />
  );
}
