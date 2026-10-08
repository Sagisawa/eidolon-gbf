"use client";

import { EmptyState } from "@astryxdesign/core/EmptyState";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { Pagination } from "@astryxdesign/core/Pagination";
import { Selector } from "@astryxdesign/core/Selector";
import { Table, pixel, proportional, useTableSortable, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Timestamp } from "@astryxdesign/core/Timestamp";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";
import { useCallback, useEffect, useState } from "react";

import { AdminPage } from "@/components/admin/AdminPage";
import { TouchButton, useWide } from "@/components/admin/DashboardParts";
import { AppLink } from "@/components/AppLink";
import { BanUserDialog } from "@/components/BanUserDialog";
import { FailureNotice } from "@/components/FailureNotice";
import { copy } from "@/i18n";
import {
  USER_SORTS,
  USERS_PAGE_SIZE,
  banAction,
  broughtKeys,
  describeLimit,
  listAdminUsers,
  sortState,
  unbanUser,
  userSort,
  type AdminUser,
  type AdminUserPage,
  type UserSort,
} from "@/lib/adminUsers";
import { formatCount } from "@/lib/dashboard";
import { toFailure, type Failure } from "@/lib/failure";
import { PROVIDER_LABELS } from "@/lib/signIn";

const t = copy.admin.users;

/** 输入停下这么久（毫秒）再去搜索，免得每敲一个字就问一次后端。 */
const SEARCH_DELAY = 300;

/**
 * 后台的「用户」页：搜索框、一行一位用户和分页。点名字进入这位用户的详情；管理者那一行没有封禁按钮。
 * 宽屏是表格：用户（登录方式在副行）、24 小时用量、最后活跃、状态（封禁、自带密钥、单独限额合在一格）、
 * 操作，一屏放得下，不用横向滚动；点「24 小时回合」「24 小时通话」的表头按它从多到少排（后端排好再分页），
 * 再点一次恢复按注册时间。窄屏（平板竖屏，或手机上外出处理刷量）换成列表行：名字、24 小时用量、状态，封禁键在行尾，
 * 排序改用搜索框下的选择框。
 */
export function AdminUserList() {
  const [query, setQuery] = useState("");
  const [page, setPage] = useState(1);
  const [sort, setSort] = useState<UserSort>("newest");
  const [result, setResult] = useState<AdminUserPage | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [banning, setBanning] = useState<AdminUser | null>(null);
  const [unbanning, setUnbanning] = useState<string | null>(null);
  const isWide = useWide("table-wide");

  const load = useCallback(async () => {
    try {
      setResult(await listAdminUsers(query, page, sort));
      setFailure(null);
    } catch (e) {
      setFailure(toFailure(e));
    }
  }, [query, page, sort]);

  const sortPlugin = useTableSortable<AdminUser>({
    sort: sortState(sort),
    onSortChange: (state) => {
      setSort(userSort(state));
      setPage(1);
    },
  });

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

  /** 一行的操作：封禁或解除封禁；管理者没有。 */
  function rowAction(user: AdminUser) {
    const action = banAction(user);
    if (action === "ban") {
      return (
        <TouchButton label={copy.admin.actionOn(t.ban, user.name)} variant="ghost" size="sm" onClick={() => setBanning(user)}>
          {t.ban}
        </TouchButton>
      );
    }
    if (action === "unban") {
      return (
        <TouchButton
          label={copy.admin.actionOn(t.unban, user.name)}
          variant="ghost"
          size="sm"
          onClick={() => unban(user)}
          isLoading={unbanning === user.id}
        >
          {t.unban}
        </TouchButton>
      );
    }
    return null;
  }

  const columns: TableColumn<AdminUser>[] = [
    {
      key: "name",
      header: t.columns.user,
      width: proportional(3),
      renderCell: (user) => (
        <VStack gap={0.5}>
          <HStack gap={2} vAlign="center" wrap="wrap">
            <AppLink href={`/admin/users/${user.id}`} isStandalone>
              {user.name}
            </AppLink>
            {user.is_admin && <Token label={t.admin} size="sm" color="blue" />}
          </HStack>
          <SignInSummary user={user} />
        </VStack>
      ),
    },
    {
      key: "turns",
      header: t.columns.turns24h,
      width: pixel(112),
      align: "end",
      sortable: true,
      renderCell: (user) => <Text hasTabularNumbers>{formatCount(user.usage_24h.turns)}</Text>,
    },
    {
      key: "calls",
      header: t.columns.calls24h,
      width: pixel(112),
      align: "end",
      sortable: true,
      renderCell: (user) => <Text hasTabularNumbers>{formatCount(user.usage_24h.calls)}</Text>,
    },
    {
      key: "last_active_at",
      header: t.columns.lastActive,
      width: pixel(144),
      renderCell: (user) => <LastActive user={user} />,
    },
    {
      key: "banned",
      header: t.columns.status,
      width: proportional(2),
      renderCell: (user) => <StatusTokens user={user} />,
    },
    {
      key: "id",
      header: t.columns.actions,
      width: pixel(104),
      renderCell: rowAction,
    },
  ];

  return (
    <AdminPage width="wide" title={copy.admin.pages.users} intro={t.intro}>
      <VStack gap={6} paddingBlockStart={4}>
        <VStack gap={3}>
          <TextInput
            label={t.search}
            isLabelHidden
            placeholder={t.searchPlaceholder}
            value={query}
            onChange={search}
            hasClear
            width={isWide ? "calc(var(--spacing-8) * 12)" : "100%"}
          />
          {!isWide && (
            <Selector
              label={t.sort.label}
              value={sort}
              onChange={(value) => {
                setSort(value as UserSort);
                setPage(1);
              }}
              options={USER_SORTS.map((value) => ({ value, label: t.sort[value] }))}
            />
          )}
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
            {isWide ? (
              <Table
                data={result.users}
                columns={columns}
                idKey="id"
                density="compact"
                verticalAlign="top"
                rowIndexStart={(page - 1) * USERS_PAGE_SIZE + 1}
                rowCount={result.total}
                plugins={{ sort: sortPlugin }}
              />
            ) : (
              <List hasDividers>
                {result.users.map((user) => (
                  <ListItem
                    key={user.id}
                    label={user.name}
                    href={`/admin/users/${user.id}`}
                    description={
                      <VStack gap={1}>
                        <Text type="supporting" hasTabularNumbers>
                          {t.usage24h(formatCount(user.usage_24h.turns), formatCount(user.usage_24h.calls))}
                        </Text>
                        <StatusTokens user={user} withAdmin />
                      </VStack>
                    }
                    endContent={rowAction(user)}
                  />
                ))}
              </List>
            )}
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
    </AdminPage>
  );
}

/** 登录方式缩成一行副字：「Google z@…」，多种用「·」隔开；没有时照说。 */
function SignInSummary({ user }: { user: AdminUser }) {
  if (user.sign_in_methods.length === 0) {
    return <Text type="supporting">{t.noSignInMethods}</Text>;
  }
  return (
    <Text type="supporting" wordBreak="break-word">
      {user.sign_in_methods
        .map((method) => `${PROVIDER_LABELS[method.provider]} ${method.email ?? method.display_name}`)
        .join(" · ")}
    </Text>
  );
}

function LastActive({ user }: { user: AdminUser }) {
  return user.last_active_at ? (
    <Timestamp value={user.last_active_at} format="auto" />
  ) : (
    <Text color="secondary">{t.never}</Text>
  );
}

/** 状态一格：封禁与否，再加上有才显示的自带密钥和单独限额。窄屏的行里名字只能是纯文字，管理者标签
 * 也放进这里（`withAdmin`）；宽屏上它跟在名字后面。 */
function StatusTokens({ user, withAdmin = false }: { user: AdminUser; withAdmin?: boolean }) {
  const keys = broughtKeys(user.own_keys);
  return (
    <HStack gap={1.5} vAlign="center" wrap="wrap">
      {withAdmin && user.is_admin && <Token label={t.admin} size="sm" color="blue" />}
      <BanStatus banned={user.banned} />
      {keys.length > 0 && (
        <Token size="sm" color="gray" label={t.ownKeysToken(keys.map((k) => t.services[k]).join("、"))} />
      )}
      {user.limits && (
        <Token
          size="sm"
          color="gray"
          label={t.limitsToken(
            t.limits.summary(describeLimit(user.limits.turns_per_hour), describeLimit(user.limits.calls_per_hour)),
          )}
        />
      )}
    </HStack>
  );
}

export function BanStatus({ banned }: { banned: boolean }) {
  return banned ? <Token label={t.banned} size="sm" color="red" /> : <Text color="secondary">{t.active}</Text>;
}

/** 单独限额：没有时「跟随全站」，有时列出回合和通话各自的数字（没设的一项跟随全站）。 */
export function UserLimits({ user }: { user: AdminUser }) {
  if (!user.limits) return <Text color="secondary">{t.limits.default}</Text>;
  return (
    <Text>
      {t.limits.summary(describeLimit(user.limits.turns_per_hour), describeLimit(user.limits.calls_per_hour))}
    </Text>
  );
}

/** 自带了哪几项服务的密钥（只说有没有）。 */
export function OwnKeys({ user }: { user: AdminUser }) {
  const services = broughtKeys(user.own_keys);
  if (services.length === 0) return <Text color="secondary">{t.noOwnKeys}</Text>;
  return <Text>{services.map((s) => t.services[s]).join("、")}</Text>;
}
