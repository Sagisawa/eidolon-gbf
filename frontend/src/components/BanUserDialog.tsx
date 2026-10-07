"use client";

import { Button } from "@astryxdesign/core/Button";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { HStack, Layout, LayoutContent, LayoutFooter, VStack } from "@astryxdesign/core/Layout";
import { Text } from "@astryxdesign/core/Text";
import { TextArea } from "@astryxdesign/core/TextArea";
import { useState } from "react";

import { FailureNotice } from "@/components/FailureNotice";
import { copy } from "@/i18n";
import { banUser, type AdminUserDetails } from "@/lib/adminUsers";
import { toFailure, type Failure } from "@/lib/failure";

const t = copy.admin.users.banDialog;

const NOTE_MAX = 500;

/**
 * 封禁一位用户：说明后果，可以写一句只有管理者看得到的备注，再确认。
 * `user` 为 null 时对话框关着；封禁成功后把后端返回的这位用户交给 `onBanned`。
 */
export function BanUserDialog({
  user,
  onClose,
  onBanned,
}: {
  user: { id: string; name: string } | null;
  onClose: () => void;
  onBanned: (user: AdminUserDetails) => void;
}) {
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  function close() {
    if (busy) return;
    setNote("");
    setFailure(null);
    onClose();
  }

  async function confirm() {
    if (!user) return;
    setBusy(true);
    setFailure(null);
    try {
      const banned = await banUser(user.id, note);
      setNote("");
      onBanned(banned);
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog isOpen={user !== null} onOpenChange={(open) => !open && close()} purpose="form" width={480}>
      <Layout
        header={<DialogHeader title={t.title(user?.name ?? "")} onOpenChange={() => close()} />}
        content={
          <LayoutContent>
            <VStack gap={4}>
              <Text as="p">{t.hint}</Text>
              <TextArea
                label={t.note}
                description={t.noteHint}
                isOptional
                value={note}
                onChange={setNote}
                maxLength={NOTE_MAX}
              />
              {failure && <FailureNotice failure={failure} />}
            </VStack>
          </LayoutContent>
        }
        footer={
          <LayoutFooter>
            <HStack gap={2} hAlign="end" wrap="wrap">
              <Button label={copy.common.cancel} variant="secondary" onClick={close} isDisabled={busy} />
              <Button
                label={t.confirm}
                variant="destructive"
                onClick={confirm}
                isLoading={busy}
                isDisabled={note.length > NOTE_MAX}
              />
            </HStack>
          </LayoutFooter>
        }
      />
    </Dialog>
  );
}
