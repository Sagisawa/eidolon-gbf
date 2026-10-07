"use client";

import { Button } from "@astryxdesign/core/Button";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { Pagination } from "@astryxdesign/core/Pagination";
import { Table, pixel, proportional, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Timestamp } from "@astryxdesign/core/Timestamp";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";
import { useCallback, useEffect, useState } from "react";

import { AppLink } from "@/components/AppLink";
import { BanUserDialog } from "@/components/BanUserDialog";
import { FailureNotice } from "@/components/FailureNotice";
import { copy } from "@/i18n";
import {
  USERS_PAGE_SIZE,
  banAction,
  broughtKeys,
  listAdminUsers,
  unbanUser,
  type AdminUser,
  type AdminUserPage,
} from "@/lib/adminUsers";
import { toFailure, type Failure } from "@/lib/failure";
import { PROVIDER_LABELS } from "@/lib/signIn";

const t = copy.admin.users;

/** 输入停下这么久（毫秒）再去搜索，免得每敲一个字就问一次后端。 */
const SEARCH_DELAY = 300;

/**
 * 后台的「用户」页：搜索框、一行一位用户的表格和分页。点名字进入这位用户的详情；
 * 管理者那一行没有封禁按钮。窄屏下表格横向滚动。
 */
export function AdminUserList() {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [result, setResult] = useState<AdminUserPage | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [banning, setBanning] = useState<AdminUser | null>(null);
  const [unbanning, setUnbanning] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setResult(await listAdminUsers(query, page));
      setFailure(null);
    } catch (e) {
      setFailure(toFailure(e));
    }
  }, [query, page]);

  useEffect(() => {
    const timer = setTimeout(load, SEARCH_DELAY);
    return () => clearTimeout(timer);
  }, [load]);

  function search(value: string) {
    setQuery(value);
    setPage(1);
  }

  async function unban(user: AdminUser) {
    setUnbanning(user.id);
    try {
      await unbanUser(user.id);
      await load();
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setUnbanning(null);
    }
  }

  const columns: TableColumn<AdminUser>[] = [
    {
      key: "name",
      header: t.columns.user,
      width: proportional(2),
      renderCell: (user) => (
        <VStack gap={0.5}>
          <AppLink href={`/admin/users/${user.id}`} isStandalone>
            {user.name}
          </AppLink>
          {user.is_admin && (
            <HStack>
              <Token label={t.admin} size="sm" color="blue" />
            </HStack>
          )}
        </VStack>
      ),
    },
    {
      key: "sign_in_methods",
      header: t.columns.signInMethods,
      width: proportional(3),
      renderCell: (user) => <SignInMethods user={user} />,
    },
    {
      key: "created_at",
      header: t.columns.createdAt,
      width: pixel(140),
      renderCell: (user) => <Timestamp value={user.created_at} format="date" />,
    },
    {
      key: "last_active_at",
      header: t.columns.lastActive,
      width: pixel(140),
      renderCell: (user) =>
        user.last_active_at ? (
          <Timestamp value={user.last_active_at} format="auto" />
        ) : (
          <Text color="secondary">{t.never}</Text>
        ),
    },
    {
      key: "banned",
      header: t.columns.status,
      width: pixel(100),
      renderCell: (user) => <BanStatus banned={user.banned} />,
    },
    {
      key: "own_keys",
      header: t.columns.ownKeys,
      width: proportional(1),
      renderCell: (user) => <OwnKeys user={user} />,
    },
    {
      key: "id",
      header: t.columns.actions,
      width: pixel(120),
      renderCell: (user) => {
        const action = banAction(user);
        if (action === "ban") {
          return <Button label={t.ban} variant="secondary" size="sm" onClick={() => setBanning(user)} />;
        }
        if (action === "unban") {
          return (
            <Button
              label={t.unban}
              variant="secondary"
              size="sm"
              onClick={() => unban(user)}
              isLoading={unbanning === user.id}
            />
          );
        }
        return null;
      },
    },
  ];

  return (
    <VStack gap={6}>
      <VStack gap={2}>
        <Heading level={1} style={{ fontSize: "var(--text-large-size)" }}>
          {copy.admin.pages.users}
        </Heading>
        <Text as="p" color="secondary">
          {t.intro}
        </Text>
      </VStack>

      <VStack gap={3}>
        <TextInput
          label={t.search}
          isLabelHidden
          placeholder={t.searchPlaceholder}
          value={query}
          onChange={search}
          hasClear
          width="100%"
        />
        {result && (
          <Text type="supporting" color="secondary">
            {t.total(result.total)}
          </Text>
        )}
      </VStack>

      {failure && <FailureNotice failure={failure} />}

      {result && result.users.length === 0 && <EmptyState title={t.empty} description={t.emptyHint} />}

      {result && result.users.length > 0 && (
        <VStack gap={4}>
          <Table
            data={result.users}
            columns={columns}
            idKey="id"
            density="compact"
            verticalAlign="top"
            rowIndexStart={(page - 1) * USERS_PAGE_SIZE + 1}
            rowCount={result.total}
          />
          {result.total > USERS_PAGE_SIZE && (
            <Pagination
              label={t.pagination}
              page={page}
              onChange={setPage}
              totalItems={result.total}
              pageSize={USERS_PAGE_SIZE}
              variant="compact"
              size="sm"
            />
          )}
        </VStack>
      )}

      <BanUserDialog
        user={banning}
        onClose={() => setBanning(null)}
        onBanned={() => {
          setBanning(null);
          load();
        }}
      />
    </VStack>
  );
}

/** 每个登录方式一行：提供方和显示名，下面是邮箱。 */
export function SignInMethods({ user }: { user: AdminUser }) {
  if (user.sign_in_methods.length === 0) return <Text color="secondary">{t.noSignInMethods}</Text>;
  return (
    <VStack gap={1}>
      {user.sign_in_methods.map((method) => (
        <VStack key={method.provider} gap={0}>
          <Text>
            {PROVIDER_LABELS[method.provider]} {method.display_name}
          </Text>
          {method.email && (
            <Text type="supporting" color="secondary">
              {method.email}
            </Text>
          )}
        </VStack>
      ))}
    </VStack>
  );
}

export function BanStatus({ banned }: { banned: boolean }) {
  return banned ? <Token label={t.banned} size="sm" color="red" /> : <Text color="secondary">{t.active}</Text>;
}

/** 自带了哪几项服务的密钥（只说有没有）。 */
export function OwnKeys({ user }: { user: AdminUser }) {
  const services = broughtKeys(user.own_keys);
  if (services.length === 0) return <Text color="secondary">{t.noOwnKeys}</Text>;
  return <Text>{services.map((s) => t.services[s]).join("、")}</Text>;
}
