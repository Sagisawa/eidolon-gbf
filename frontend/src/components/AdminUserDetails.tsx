"use client";

import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Button } from "@astryxdesign/core/Button";
import { HStack } from "@astryxdesign/core/HStack";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { Spinner } from "@astryxdesign/core/Spinner";
import { Table, pixel, proportional, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { Timestamp } from "@astryxdesign/core/Timestamp";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { AdminPage } from "@/components/admin/AdminPage";
import { RowList, useWide } from "@/components/admin/DashboardParts";
import { BanStatus, OwnKeys, UserLimits } from "@/components/AdminUserList";
import { AppLink } from "@/components/AppLink";
import { BanUserDialog } from "@/components/BanUserDialog";
import { FailureNotice } from "@/components/FailureNotice";
import { SettingsSection } from "@/components/SettingsSection";
import { UserLimitsDialog } from "@/components/UserLimitsDialog";
import { copy } from "@/i18n";
import {
  USAGE_RANGES,
  banAction,
  describeCount,
  deleteUser,
  getAdminUser,
  takeOffUserLimits,
  unbanUser,
  usageRows,
  type AdminUserDetails as Details,
  type AdminUserUsage,
  type KeyedCount,
  type UsageRow,
} from "@/lib/adminUsers";
import { toFailure, type Failure } from "@/lib/failure";
import { PROVIDER_LABELS } from "@/lib/signIn";

const t = copy.admin.users;

/**
 * 一位用户的详情：登录方式（含邮箱和填进管理者名单用的标识）、注册和最后活跃的时间、
 * 自带密钥的有无、单独限额（设定、修改、取消）、封禁的时间和备注、近期用量，以及封禁 / 解除封禁
 * 和删除（二次确认，删完回到列表）。
 * 不含任何对话、记忆和制作人档案。
 */
export function AdminUserDetails({ id }: { id: string }) {
  const [user, setUser] = useState<Details | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [banning, setBanning] = useState(false);
  const [unbanning, setUnbanning] = useState(false);
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [editingLimits, setEditingLimits] = useState(false);
  const [takingOffLimits, setTakingOffLimits] = useState(false);
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

  async function takeOffLimits() {
    setTakingOffLimits(true);
    setFailure(null);
    try {
      setUser(await takeOffUserLimits(id));
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setTakingOffLimits(false);
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
  const back = (
    <HStack>
      <AppLink href="/admin/users" isStandalone>
        {t.backToList}
      </AppLink>
    </HStack>
  );

  if (!user) {
    return (
      <VStack gap={6}>
        {back}
        {failure && <FailureNotice failure={failure} />}
        {!failure && <Spinner size="lg" aria-label={t.loading} />}
      </VStack>
    );
  }

  return (
    <AdminPage
      width="narrow"
      above={back}
      title={user.name}
      meta={
        <HStack gap={2} vAlign="center" wrap="wrap">
          <BanStatus banned={user.banned} />
          {user.is_admin && <Token label={t.admin} size="sm" color="blue" />}
        </HStack>
      }
      end={
        action === "ban" ? (
          <Button label={t.ban} variant="destructive" onClick={() => setBanning(true)} />
        ) : action === "unban" ? (
          <Button label={t.unban} variant="secondary" onClick={unban} isLoading={unbanning} />
        ) : (
          <Text color="secondary">{t.adminCannotBeBanned}</Text>
        )
      }
    >
      {failure && <FailureNotice failure={failure} />}

      <SettingsSection title={t.details.title}>
        <MetadataList columns="multi">
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
          <MetadataListItem label={t.limits.title}>
            <VStack gap={2}>
              <UserLimits user={user} />
              {user.limits?.note && (
                <Text type="supporting" color="secondary">
                  {user.limits.note}
                </Text>
              )}
              {user.limits && (
                <HStack gap={1} vAlign="center">
                  <Text type="supporting" color="secondary">
                    {t.limits.updatedAt}
                  </Text>
                  <Timestamp value={user.limits.updated_at} format="date_time" type="supporting" />
                </HStack>
              )}
              <HStack gap={2} wrap="wrap">
                <Button
                  label={user.limits ? t.limits.edit : t.limits.set}
                  variant="secondary"
                  size="sm"
                  onClick={() => setEditingLimits(true)}
                />
                {user.limits && (
                  <Button
                    label={t.limits.takeOff}
                    variant="secondary"
                    size="sm"
                    onClick={takeOffLimits}
                    isLoading={takingOffLimits}
                  />
                )}
              </HStack>
            </VStack>
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
      </SettingsSection>

      <RecentUsage usage={user.usage} />

      {action !== null && (
        <SettingsSection title={t.delete} description={t.deleteSection.hint}>
          <HStack>
            <Button label={t.delete} variant="destructive" onClick={() => setConfirmingDelete(true)} />
          </HStack>
        </SettingsSection>
      )}

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

      <UserLimitsDialog
        user={editingLimits ? user : null}
        onClose={() => setEditingLimits(false)}
        onSaved={(saved) => {
          setEditingLimits(false);
          setUser(saved);
        }}
      />

      <BanUserDialog
        user={banning ? user : null}
        onClose={() => setBanning(false)}
        onBanned={(banned) => {
          setBanning(false);
          setUser(banned);
        }}
      />
    </AdminPage>
  );
}

/** 近期用量：回合、通话、被拒绝各一行，最近 24 小时、7 天、30 天各一列；每格是总数，下面分出部署者的 key 和自带密钥。 */
function RecentUsage({ usage }: { usage: AdminUserUsage }) {
  const u = t.usage;
  const wide = useWide();
  if (!wide) {
    return (
      <SettingsSection title={u.title} description={u.hint}>
        <RowList
          rows={usageRows(usage).map((row) => ({
            id: row.what,
            label: row.label,
            description: USAGE_RANGES.map((range) => `${u.ranges[range]} ${describeCount(row[range]).total}`).join(" · "),
          }))}
        />
      </SettingsSection>
    );
  }
  const columns: TableColumn<UsageRow>[] = [
    { key: "label", header: "", width: pixel(80), renderCell: (row) => <Text weight="semibold">{row.label}</Text> },
    ...USAGE_RANGES.map(
      (range): TableColumn<UsageRow> => ({
        key: range,
        header: u.ranges[range],
        width: proportional(1),
        renderCell: (row) => <Count count={row[range]} />,
      }),
    ),
  ];
  return (
    <SettingsSection title={u.title} description={u.hint}>
      <Table data={usageRows(usage)} columns={columns} idKey="what" density="compact" verticalAlign="top" />
    </SettingsSection>
  );
}

function Count({ count }: { count: KeyedCount }) {
  const { total, split } = describeCount(count);
  return (
    <VStack gap={0}>
      <Text>{total}</Text>
      {split && (
        <Text type="supporting" color="secondary">
          {split}
        </Text>
      )}
    </VStack>
  );
}
