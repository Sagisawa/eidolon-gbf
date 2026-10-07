"use client";

import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Button } from "@astryxdesign/core/Button";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Text } from "@astryxdesign/core/Text";
import { Timestamp } from "@astryxdesign/core/Timestamp";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { BanStatus, OwnKeys } from "@/components/AdminUserList";
import { AppLink } from "@/components/AppLink";
import { BanUserDialog } from "@/components/BanUserDialog";
import { FailureNotice } from "@/components/FailureNotice";
import { copy } from "@/i18n";
import {
  banAction,
  deleteUser,
  getAdminUser,
  unbanUser,
  type AdminUserDetails as Details,
} from "@/lib/adminUsers";
import { toFailure, type Failure } from "@/lib/failure";
import { PROVIDER_LABELS } from "@/lib/signIn";

const t = copy.admin.users;

/**
 * 一位用户的详情：登录方式（含邮箱和填进管理者名单用的标识）、注册和最后活跃的时间、
 * 自带密钥的有无、封禁的时间和备注，以及封禁 / 解除封禁和删除（二次确认，删完回到列表）。
 * 不含任何对话、记忆和制作人档案。
 */
export function AdminUserDetails({ id }: { id: string }) {
  const [user, setUser] = useState<Details | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [banning, setBanning] = useState(false);
  const [unbanning, setUnbanning] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const router = useRouter();

  useEffect(() => {
    getAdminUser(id).then(setUser, (e) => setFailure(toFailure(e)));
  }, [id]);

  async function unban() {
    setUnbanning(true);
    setFailure(null);
    try {
      setUser(await unbanUser(id));
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setUnbanning(false);
    }
  }

  async function remove() {
    setDeleting(true);
    setFailure(null);
    try {
      await deleteUser(id);
      router.replace("/admin/users");
    } catch (e) {
      setFailure(toFailure(e));
      setConfirmingDelete(false);
      setDeleting(false);
    }
  }

  const action = user && banAction(user);

  return (
    <VStack gap={6}>
      <HStack>
        <AppLink href="/admin/users" isStandalone>
          {t.backToList}
        </AppLink>
      </HStack>

      {failure && <FailureNotice failure={failure} />}

      {!user && !failure && <Spinner size="lg" aria-label={t.loading} />}

      {user && (
        <VStack gap={6}>
          <VStack gap={2}>
            <Heading level={1} style={{ fontSize: "var(--text-large-size)" }}>
              {user.name}
            </Heading>
            <HStack gap={2} vAlign="center" wrap="wrap">
              <BanStatus banned={user.banned} />
              {user.is_admin && <Token label={t.admin} size="sm" color="blue" />}
            </HStack>
          </VStack>

          <MetadataList label={{ position: "top" }}>
            <MetadataListItem label={t.details.signInMethods}>
              {user.sign_in_methods.length === 0 ? (
                <Text color="secondary">{t.noSignInMethods}</Text>
              ) : (
                <VStack gap={2}>
                  {user.sign_in_methods.map((method) => (
                    <VStack key={method.provider} gap={0}>
                      <Text>
                        {PROVIDER_LABELS[method.provider]} {method.display_name}
                      </Text>
                      <Text type="supporting" color="secondary">
                        {t.details.email}：{method.email ?? t.details.noEmail}
                      </Text>
                      <Text type="supporting" color="secondary">
                        {t.details.identifier}：{method.provider}:{method.subject}
                      </Text>
                    </VStack>
                  ))}
                </VStack>
              )}
            </MetadataListItem>
            <MetadataListItem label={t.details.id}>
              <Text type="code">{user.id}</Text>
            </MetadataListItem>
            <MetadataListItem label={t.details.createdAt}>
              <Timestamp value={user.created_at} format="date_time" type="body" />
            </MetadataListItem>
            <MetadataListItem label={t.details.lastActive}>
              {user.last_active_at ? (
                <Timestamp value={user.last_active_at} format="date_time" type="body" />
              ) : (
                <Text color="secondary">{t.never}</Text>
              )}
            </MetadataListItem>
            <MetadataListItem label={t.details.ownKeys}>
              <OwnKeys user={user} />
            </MetadataListItem>
            {user.banned_at && (
              <MetadataListItem label={t.details.bannedAt}>
                <Timestamp value={user.banned_at} format="date_time" type="body" />
              </MetadataListItem>
            )}
            {user.banned && (
              <MetadataListItem label={t.details.banNote}>
                {user.ban_note ? (
                  <Text>{user.ban_note}</Text>
                ) : (
                  <Text color="secondary">{t.details.noNote}</Text>
                )}
              </MetadataListItem>
            )}
          </MetadataList>

          <HStack gap={2} wrap="wrap">
            {action === "ban" && (
              <Button label={t.ban} variant="destructive" onClick={() => setBanning(true)} />
            )}
            {action === "unban" && (
              <Button label={t.unban} variant="secondary" onClick={unban} isLoading={unbanning} />
            )}
            {action !== null && (
              <Button label={t.delete} variant="destructive" onClick={() => setConfirmingDelete(true)} />
            )}
            {action === null && <Text color="secondary">{t.adminCannotBeBanned}</Text>}
          </HStack>
        </VStack>
      )}

      {user && (
        <AlertDialog
          isOpen={confirmingDelete}
          onOpenChange={(open) => !deleting && setConfirmingDelete(open)}
          title={t.deleteDialog.title(user.name)}
          description={`${t.deleteDialog.hint}${user.banned ? t.deleteDialog.banned : t.deleteDialog.notBanned}`}
          actionLabel={t.deleteDialog.confirm}
          cancelLabel={copy.common.cancel}
          onAction={remove}
          isActionLoading={deleting}
          width={480}
        />
      )}

      <BanUserDialog
        user={banning && user ? user : null}
        onClose={() => setBanning(false)}
        onBanned={(banned) => {
          setBanning(false);
          setUser(banned);
        }}
      />
    </VStack>
  );
}
