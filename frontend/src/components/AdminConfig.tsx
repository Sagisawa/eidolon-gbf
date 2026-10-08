"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { FormLayout } from "@astryxdesign/core/FormLayout";
import { HStack } from "@astryxdesign/core/HStack";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { Selector } from "@astryxdesign/core/Selector";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { proportional, Table, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";
import { FormEvent, Fragment, useEffect, useRef, useState } from "react";

import { AdminPage } from "@/components/admin/AdminPage";
import { RowList, TOUCH_LINK, TouchButton, useTouch, useWide } from "@/components/admin/DashboardParts";
import { OpenFormProvider, useOpenForm } from "@/components/admin/OpenForm";
import { AdminPrices } from "@/components/AdminPrices";
import { AppLink } from "@/components/AppLink";
import { FailureNotice } from "@/components/FailureNotice";
import { PROSE_WIDTH, SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import {
  changeOf,
  formOf,
  getAdminConfig,
  isAvailable,
  ITEM_SPECS,
  ITEMS,
  readOnlyValue,
  restoreItem,
  rows,
  saveItem,
  statusDisplay,
  type AdminConfig as Config,
  type ConfigItem,
  type FieldRow,
  type FieldSpec,
  type Form,
  type ItemName,
  type ReadOnlyItem,
} from "@/lib/adminConfig";
import type { LLMProtocol } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

const t = copy.admin.config;

/**
 * 后台的「配置」页：页首一排页内链接；每一项列出状态和当前生效的值（有后台覆盖时对照 .env 和覆盖的值），
 * 可以修改、恢复；然后是各模型的单价；最后是只能查看的项。
 */
export function AdminConfig() {
  const [config, setConfig] = useState<Config | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    getAdminConfig().then(setConfig, (e) => setFailure(toFailure(e)));
  }, []);

  return (
    <AdminPage width="narrow" title={copy.admin.pages.config} intro={t.intro}>
      <OpenFormProvider>
        {failure && !config && <FailureNotice failure={failure} />}
        {!failure && !config && (
          <Text as="p" color="secondary" role="status">
            {t.loading}
          </Text>
        )}
        {config && <ConfigNav />}
        {config &&
          ITEMS.map((name) => <ItemSection key={name} name={name} config={config} onChange={setConfig} />)}
        {config && <AdminPrices />}
        {config && <ReadOnlySection items={config.read_only} />}
      </OpenFormProvider>
    </AdminPage>
  );
}

/** 页内一节的锚点，页首的导航跳到这里。 */
function anchor(section: ItemName | "prices" | "read_only"): string {
  return `config-${section}`;
}

/** 触屏上链接各自撑到 44px 高，行与行之间不再另加间距（不然折成几行时太松），只在行内隔开。 */
const NAV_LINK_TOUCH = { ...TOUCH_LINK, marginInlineEnd: "var(--spacing-4)" };

/** 页首的页内导航：一项一个链接，配置项多、页面长，想改限额不用滚过前面六项。 */
function ConfigNav() {
  const touch = useTouch();
  const links: { section: ItemName | "prices" | "read_only"; label: string }[] = [
    ...ITEMS.map((name) => ({ section: name, label: t.items[name].title })),
    { section: "prices", label: copy.admin.prices.title },
    { section: "read_only", label: t.readOnly.title },
  ];
  return (
    <HStack as="nav" aria-label={t.nav} gap={touch ? 0 : 4} wrap="wrap" paddingBlockStart={2}>
      {links.map(({ section, label }) => (
        <AppLink key={section} href={`#${anchor(section)}`} isStandalone style={touch ? NAV_LINK_TOUCH : undefined}>
          {label}
        </AppLink>
      ))}
    </HStack>
  );
}

/**
 * 一项的各个值。没有后台覆盖时 .env 的值就是当前生效的值，三列对照只会重复一遍，所以只列「项：当前值」；
 * 有覆盖时才展开 .env、当前生效、后台覆盖三列，看得出改了哪里、是否生效。
 */
function Values({ name, rows: fieldRows }: { name: ItemName; rows: FieldRow[] }) {
  if (fieldRows.some((row) => row.overridden)) {
    return <Table data={fieldRows} columns={columns(name)} idKey="field" density="compact" />;
  }
  return (
    <MetadataList columns="multi">
      {fieldRows.map((row) => (
        <MetadataListItem key={row.field} label={t.fields[row.field] ?? row.field}>
          <Text wordBreak="break-word">{shown(name, row.field, row.effective)}</Text>
        </MetadataListItem>
      ))}
    </MetadataList>
  );
}

/** 一个值在表里的样子：key 只有末 4 位，max_tokens 没设时是接口类型的默认值，服务和地域用中文名，限额的 0 是不限。 */
function shown(name: ItemName, field: string, value: FieldRow["env"]): string {
  if (value === null) return field === "max_tokens" ? t.defaultMaxTokens : t.none;
  if (ITEM_SPECS[name].secrets.includes(field)) return t.last4(String(value));
  if (field === "protocol") return t.protocols[value as LLMProtocol] ?? String(value);
  if (field === "provider") return t.providers[String(value)] ?? String(value);
  if (field === "region") return t.regions[String(value)] ?? String(value);
  if (name === "limits" && value === 0) return t.unlimited;
  return String(value);
}

function columns(name: ItemName): TableColumn<FieldRow>[] {
  return [
    { key: "field", header: t.columns.field, width: proportional(1), renderCell: (row) => t.fields[row.field] ?? row.field },
    { key: "env", header: t.columns.env, width: proportional(2), renderCell: (row) => shown(name, row.field, row.env) },
    {
      key: "effective",
      header: t.columns.effective,
      width: proportional(2),
      renderCell: (row) => shown(name, row.field, row.effective),
    },
    {
      key: "override",
      header: t.columns.override,
      width: proportional(2),
      renderCell: (row) =>
        row.overridden ? (
          <HStack gap={2} vAlign="center" wrap="wrap">
            <Text wordBreak="break-word">{shown(name, row.field, row.override)}</Text>
            <Token
              size="sm"
              color={row.inEffect ? "blue" : "orange"}
              label={row.inEffect ? t.inEffect : t.notInEffect}
            />
          </HStack>
        ) : (
          t.none
        ),
    },
  ];
}

/** 表单里一个字段的说明：key 留空不改，其余按字段给出取值范围。 */
function fieldHint(name: ItemName, spec: FieldSpec, keysEditable: boolean): string | undefined {
  if (spec.kind === "secret") {
    if (!keysEditable) return t.keysReadOnly;
    return name === "stt" ? t.formHints.stt_api_key : name === "judge" ? t.formHints.judge_api_key : t.apiKeyHint;
  }
  if (spec.kind === "maxTokens") return t.maxTokensHint;
  if (spec.kind === "probability") return t.formHints.probability;
  if (spec.kind === "limit") return t.formHints.limit;
  if (name === "judge" && spec.name === "model") return t.formHints.judge_model;
  return t.formHints[spec.name];
}

function optionLabel(field: string, option: string): string {
  return field === "protocol" ? (t.protocols[option as LLMProtocol] ?? option) : (t.providers[option] ?? option);
}

/**
 * 一项配置：状态、三列对照（.env、当前生效、后台覆盖），修改表单和恢复按钮。
 * 保存时后端先试调（阈值不用），试不通照原话显示原因、不保存。
 */
function ItemSection({ name, config, onChange }: { name: ItemName; config: Config; onChange: (config: Config) => void }) {
  const item = config[name];
  const title = t.items[name].title;
  if (!isAvailable(item)) {
    return (
      <SettingsSection id={anchor(name)} title={title} description={t.items[name].hint}>
        <Text as="p" color="secondary" style={{ maxWidth: PROSE_WIDTH }}>
          {t.unavailable(item.unavailable)}
        </Text>
      </SettingsSection>
    );
  }
  return <AvailableItem name={name} item={item} keysEditable={config.keys_editable} onChange={onChange} />;
}

function AvailableItem({
  name,
  item,
  keysEditable,
  onChange,
}: {
  name: ItemName;
  item: ConfigItem;
  keysEditable: boolean;
  onChange: (config: Config) => void;
}) {
  const spec = ITEM_SPECS[name];
  const display = statusDisplay(item);
  // 同一时间只开一个表单：点了别的「修改」，这一项的表单就收起（见 OpenForm）。
  const [editing, setEditing] = useOpenForm(name);
  /** 是自己关的（取消、保存成功），不是因为别的表单打开而收起：只有这时才把焦点还给「修改」。 */
  const closedHere = useRef(false);
  const [form, setForm] = useState<Form>(() => formOf(spec, item.effective));
  const [busy, setBusy] = useState<"save" | "restore" | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const result = changeOf(spec, form, keysEditable);
  const problem = "problem" in result ? result.problem : null;
  const fieldRows = rows(item, spec);
  const formRef = useRef<HTMLFormElement>(null);

  // 打开表单时焦点移到第一个能填的框（按钮被表单替换掉，焦点不移就落回页首）。
  const actionsRef = useRef<HTMLDivElement>(null);
  const wasEditing = useRef(false);
  useEffect(() => {
    if (editing) formRef.current?.querySelector<HTMLElement>("input:not([disabled]), button:not([disabled])")?.focus();
    // 关掉表单（取消或保存）后焦点回到「修改」：它随表单关闭重新挂上，原来的那个元素已经不在了。
    else if (wasEditing.current && closedHere.current) actionsRef.current?.querySelector<HTMLElement>("button")?.focus();
    wasEditing.current = editing;
    closedHere.current = false;
  }, [editing]);

  function edit() {
    setForm(formOf(spec, item.effective));
    setFailure(null);
    setNotice(null);
    setEditing(true);
  }

  async function run(action: "save" | "restore", request: () => Promise<Config>, done: string) {
    setBusy(action);
    setFailure(null);
    setNotice(null);
    try {
      onChange(await request());
      closedHere.current = true;
      setEditing(false);
      setNotice(done);
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(null);
    }
  }

  function submit(event: FormEvent) {
    event.preventDefault();
    if ("change" in result) void run("save", () => saveItem(name, result.change), t.saved);
  }

  const set = (field: string) => (value: string) => setForm((f) => ({ ...f, [field]: value }));

  return (
    <SettingsSection id={anchor(name)} title={t.items[name].title} description={t.items[name].hint}>
      {display.variant && (
        <HStack gap={2} vAlign="center" wrap="wrap">
          <StatusDot variant={display.variant} label={t.status[item.status]} />
          <Text>{t.status[item.status]}</Text>
        </HStack>
      )}
      {item.follows_chat && (
        <Text as="p" color="secondary" style={{ maxWidth: PROSE_WIDTH }}>
          {t.followsChat}
        </Text>
      )}
      {item.model && (
        <Text as="p" color="secondary" style={{ maxWidth: PROSE_WIDTH }}>
          {t.forModel(item.model)}
        </Text>
      )}
      {display.failure && <Banner status="warning" title={t.status.failed} description={t.failed(display.failure)} />}
      {notice && <Banner status="success" title={notice} isDismissable onDismiss={() => setNotice(null)} />}
      {failure && <FailureNotice failure={failure} />}
      {/* 修改时表单里已经填着当前的值：没有覆盖时上面那份「项：当前值」只是重复，收起；有覆盖时三列对照还有用，留着。 */}
      {(!editing || fieldRows.some((row) => row.overridden)) && <Values name={name} rows={fieldRows} />}
      {!editing && (
        <HStack ref={actionsRef} gap={2} wrap="wrap">
          <TouchButton label={copy.admin.actionOn(t.edit, t.items[name].title)} onClick={edit} isDisabled={busy !== null}>
            {t.edit}
          </TouchButton>
          {display.canRestore && (
            <TouchButton
              variant="ghost"
              label={t.restore}
              isLoading={busy === "restore"}
              isDisabled={busy !== null}
              onClick={() => void run("restore", () => restoreItem(name), t.restored)}
            />
          )}
        </HStack>
      )}
      {editing && (
        <form ref={formRef} onSubmit={submit}>
          <FormLayout>
            {spec.form.map((field) => {
              const label = t.fields[field.name] ?? field.name;
              if (field.kind === "select") {
                return (
                  <Selector
                    key={field.name}
                    label={label}
                    value={form[field.name]}
                    onChange={(value) => set(field.name)(String(value))}
                    options={(field.options ?? []).map((o) => ({ value: o, label: optionLabel(field.name, o) }))}
                  />
                );
              }
              const secret = field.kind === "secret";
              return (
                <TextInput
                  key={field.name}
                  type={secret ? "password" : "text"}
                  label={label}
                  description={fieldHint(name, field, keysEditable)}
                  value={form[field.name]}
                  onChange={set(field.name)}
                  isDisabled={secret && !keysEditable}
                  isOptional={field.kind === "optionalText"}
                  status={
                    problem?.field === field.name
                      ? { type: "error", message: t.problems[problem.reason](label) }
                      : undefined
                  }
                  autoComplete="off"
                />
              );
            })}
            <HStack gap={2}>
              <TouchButton
                type="submit"
                variant="primary"
                label={busy === "save" ? t.saving : t.save}
                isLoading={busy === "save"}
                isDisabled={problem !== null || busy !== null}
              />
              <TouchButton variant="ghost" label={copy.common.cancel} onClick={() => {
                  closedHere.current = true;
                  setEditing(false);
                }}
                isDisabled={busy !== null}
              />
            </HStack>
          </FormLayout>
        </form>
      )}
    </SettingsSection>
  );
}

/** 「EIDOLON_SECRET_KEY」这类名字窄列里放不下时只在下划线后折行，不从词中间断开。 */
function BreakAtUnderscores({ text }: { text: string }) {
  const parts = text.split("_");
  return (
    <Text>
      {parts.map((part, i) => (
        <Fragment key={i}>
          {part}
          {i < parts.length - 1 && (
            <>
              _<wbr />
            </>
          )}
        </Fragment>
      ))}
    </Text>
  );
}

const READ_ONLY_COLUMNS: TableColumn<ReadOnlyItem>[] = [
  {
    key: "name",
    header: t.readOnly.columns.name,
    width: proportional(1),
    renderCell: (row) => <BreakAtUnderscores text={t.readOnly.names[row.name] ?? row.name} />,
  },
  {
    key: "value",
    header: t.readOnly.columns.value,
    width: proportional(2),
    renderCell: (row) => <Text wordBreak="break-word">{readOnlyValue(row.value, { ...t.readOnly, none: t.none })}</Text>,
  },
  { key: "why", header: t.readOnly.columns.why, width: proportional(3), renderCell: (row) => row.why },
];

/** 只能查看的项：当前的值（密钥只说设没设）和为什么不能在后台改。 */
function ReadOnlySection({ items }: { items: ReadOnlyItem[] }) {
  const wide = useWide();
  return (
    <SettingsSection id={anchor("read_only")} title={t.readOnly.title} description={t.readOnly.hint}>
      {wide ? (
        <Table data={items} columns={READ_ONLY_COLUMNS} idKey="name" density="compact" />
      ) : (
        <RowList
          rows={items.map((row) => ({
            id: row.name,
            label: t.readOnly.names[row.name] ?? row.name,
            description: (
              <VStack gap={0.5}>
                <Text type="supporting" color="primary" wordBreak="break-word">
                  {readOnlyValue(row.value, { ...t.readOnly, none: t.none })}
                </Text>
                <Text type="supporting">{row.why}</Text>
              </VStack>
            ),
          }))}
        />
      )}
    </SettingsSection>
  );
}
