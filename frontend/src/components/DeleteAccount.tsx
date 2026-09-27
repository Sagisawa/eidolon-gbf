"use client";

import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Button } from "@astryxdesign/core/Button";
import { HStack } from "@astryxdesign/core/HStack";
import { useState } from "react";

import { FailureNotice } from "@/components/FailureNotice";
import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import { deleteAccount } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

const t = copy.settings.deleteAccount;

/** 删除用户的全部数据；要再确认一次（PRODUCT.md「尊重陌生人的数据」）。 */
export function DeleteAccount() {
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  async function remove() {
    setBusy(true);
    setFailure(null);
    try {
      await deleteAccount();
      window.location.assign("/login");
    } catch (e) {
      setFailure(toFailure(e));
      setConfirming(false);
      setBusy(false);
    }
  }

  return (
    <SettingsSection title={t.title} description={t.hint}>
      {failure && <FailureNotice failure={failure} />}
      <HStack>
        <Button variant="destructive" label={t.start} onClick={() => setConfirming(true)} />
      </HStack>
      <AlertDialog
        isOpen={confirming}
        onOpenChange={(open) => !busy && setConfirming(open)}
        title={t.confirmTitle}
        description={t.hint}
        actionLabel={t.confirm}
        cancelLabel={copy.common.cancel}
        onAction={remove}
        isActionLoading={busy}
      />
    </SettingsSection>
  );
}
