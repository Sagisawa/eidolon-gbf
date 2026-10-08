"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { FormLayout } from "@astryxdesign/core/FormLayout";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { MetadataList, MetadataListItem } from "@astryxdesign/core/MetadataList";
import { Selector } from "@astryxdesign/core/Selector";
import { pixel, proportional, Table, useTableRowExpansion, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Timestamp } from "@astryxdesign/core/Timestamp";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";
import { FormEvent, type ReactNode, useEffect, useRef, useState } from "react";

import { TouchButton, useWide } from "@/components/admin/DashboardParts";
import { useOpenForm } from "@/components/admin/OpenForm";
import { useSubmitCheck } from "@/components/admin/useSubmitCheck";
import { FailureNotice } from "@/components/FailureNotice";
import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import {
  catalogStatus,
  type CatalogState,
  CURRENCIES,
  effectiveColumn,
  emptyPriceForm,
  formatPrice,
  getPrices,
  matchText,
  type Price,
  priceChangeOf,
  priceFormOf,
  type PriceChange,
  type PriceEntry,
  type PriceForm,
  type Prices,
  refreshCatalog,
  restorePrice,
  savePrice,
  UNITS,
  unitWord,
} from "@/lib/adminPrices";
import { toFailure, type Failure } from "@/lib/failure";

const t = copy.admin.prices;
const services = copy.admin.dashboard.health.services;

type FormField = keyof PriceForm;

type FormMode = { kind: "add" } | { kind: "edit"; entry: PriceEntry } | { kind: "price" };

interface EntryRow extends Record<string, unknown> {
  id: string;
  entry: PriceEntry;
}

/** 后台拉取目录时，隔多久再读一次单价，看它拉完没有。 */
const POLL_MS = 2000;

/** 单价表默认只列这么多行，其余点「显示全部」或筛选后才列出：预设和目录加起来有几十个模型。 */
const FOLDED_ROWS = 12;

/**
 * 「配置」页的单价一节：最近用过却没有单价的模型放在最上面（待办：一条提醒，每个模型一行，点一下就能
 * 按运行记录里的名字设单价）；在线目录的状态和「立即从目录刷新」；预设、后台设定过的和最近用过的模型，
 * 每行只列生效的单价和它来自哪一种，后台设定、目录、预设三种并列的对照在「修改」时列出；可以修改、
 * 恢复（回到目录或预设，都没有的就删除）、新增。
 */
export function AdminPrices() {
  const [prices, setPrices] = useState<Prices | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [form, setForm] = useState<PriceForm | null>(null);
  // 配置页同一时间只开一个表单：别的配置项打开表单时，这里的收起（见 OpenForm）。
  const [isOpen, setOpen] = useOpenForm("prices");
  /** 是自己关的（取消、保存成功），不是被别的表单挤掉：只有这时才把焦点还回去。 */
  const closedHere = useRef(false);
  /** 表单在做什么：新增，修改一条（列出它的三种单价作参考），或给未设单价的模型设单价。后两种的提供方、
   * 模型和单位是定的，不能改：改了就成了另一条。 */
  const [mode, setMode] = useState<FormMode>({ kind: "add" });
  /** 每打开一次表单加一，用来把表单滚进视野、把焦点移进去；不跟着输入变。 */
  const [opened, setOpened] = useState(0);
  const editorRef = useRef<HTMLDivElement>(null);
  /** 打开表单的那个按钮；关掉表单（取消或保存）后焦点回到它，它不在了（「新增单价」随表单隐藏）就回到「新增单价」。 */
  const returnTo = useRef<HTMLElement | null>(null);
  const addRef = useRef<HTMLDivElement>(null);
  const [query, setQuery] = useState("");
  const [showAll, setShowAll] = useState(false);
  const wide = useWide();
  const [busy, setBusy] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  useEffect(() => {
    getPrices().then(setPrices, (e) => setFailure(toFailure(e)));
  }, []);

  const fetching = prices?.catalog.fetching ?? false;
  useEffect(() => {
    if (!fetching) return;
    const timer = setTimeout(() => getPrices().then(setPrices, (e) => setFailure(toFailure(e))), POLL_MS);
    return () => clearTimeout(timer);
  }, [fetching, prices]);

  async function refresh() {
    setBusy("refresh");
    setFailure(null);
    setNotice(null);
    try {
      const next = await refreshCatalog();
      setPrices(next);
      const status = catalogStatus(next.catalog);
      if (status === "fresh") setNotice(t.catalog.refreshed);
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(null);
    }
  }

  async function run(id: string, request: () => Promise<Prices>, done: string) {
    setBusy(id);
    setFailure(null);
    setNotice(null);
    try {
      setPrices(await request());
      close(id === "save");
      setNotice(done);
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(null);
    }
  }

  /** 收起表单；`returnFocus` 时（取消、保存成功）焦点回到打开它的按钮。 */
  function close(returnFocus: boolean) {
    closedHere.current = returnFocus;
    setForm(null);
    setOpen(false);
  }

  // 别的配置项打开了表单：这里的收起，焦点留在那边。
  useEffect(() => {
    if (!isOpen && form !== null) setForm(null);
  }, [isOpen, form]);

  function open(next: PriceForm, nextMode: FormMode) {
    const from = document.activeElement;
    returnTo.current = from instanceof HTMLElement ? from : null;
    setFailure(null);
    setNotice(null);
    setForm(next);
    setMode(nextMode);
    setOpened((n) => n + 1);
    setOpen(true);
  }

  // 打开表单时把它滚进视野，焦点移到第一个能填的框。
  useEffect(() => {
    const editor = editorRef.current;
    if (opened === 0 || !editor) return;
    editor.scrollIntoView({ block: "nearest", behavior: "smooth" });
    editor.querySelector<HTMLInputElement>("input:not([disabled])")?.focus({ preventScroll: true });
  }, [opened]);

  const formOpen = form !== null;
  useEffect(() => {
    if (formOpen || opened === 0 || !closedHere.current) return;
    closedHere.current = false;
    const back = returnTo.current?.isConnected ? returnTo.current : addRef.current?.querySelector<HTMLElement>("button");
    back?.focus();
    returnTo.current = null;
    // 只在表单关上的那一刻跑，`opened` 不算触发条件。
  }, [formOpen]);

  /** 一条单价的操作：修改，有后台设定时还能恢复（回到目录或预设，都没有的就删除）。 */
  function entryActions(id: string, entry: PriceEntry) {
    const restoreWord = entry.catalog ? t.restoreTo.catalog : entry.preset ? t.restoreTo.preset : t.remove;
    return (
      <HStack gap={1} wrap="wrap">
        <TouchButton
          size="sm"
          variant="ghost"
          label={t.formTitle.edit(entry.model)}
          isDisabled={busy !== null}
          onClick={() => open(priceFormOf(entry), { kind: "edit", entry })}
        >
          {t.edit}
        </TouchButton>
        {entry.override && (
          <TouchButton
            size="sm"
            variant="ghost"
            label={copy.admin.actionOn(restoreWord, entry.model)}
            isLoading={busy === id}
            isDisabled={busy !== null}
            onClick={() => void run(id, () => restorePrice(entry), t.restored)}
          >
            {restoreWord}
          </TouchButton>
        )}
      </HStack>
    );
  }

  const matching = (prices?.prices ?? [])
    .map((entry) => ({ id: keyOf(entry), entry }))
    .filter(({ entry }) => matches(entry, query));
  const folded = query === "" && !showAll && matching.length > FOLDED_ROWS;
  const listed = folded ? matching.slice(0, FOLDED_ROWS) : matching;

  const columns: TableColumn<EntryRow>[] = [
    {
      key: "model",
      header: t.columns.model,
      width: proportional(2),
      renderCell: ({ entry }) => <ModelName entry={entry} />,
    },
    { key: "unit", header: t.columns.unit, width: pixel(72), renderCell: ({ entry }) => unitWord(entry.unit) },
    {
      key: "effective",
      header: t.columns.effective,
      width: proportional(3),
      renderCell: ({ entry }) => <EffectivePrice entry={entry} />,
    },
    {
      key: "actions",
      header: t.columns.actions,
      width: proportional(1.5),
      renderCell: ({ id, entry }) => entryActions(id, entry),
    },
  ];

  const editor = form && (
    <VStack ref={editorRef} gap={4} maxWidth="calc(var(--spacing-8) * 20)" paddingBlock={2}>
      <VStack gap={1}>
        <Heading level={3} style={{ fontSize: "var(--text-body-size)" }} wordBreak="break-word">
          {mode.kind === "add" ? t.formTitle.add : t.formTitle[mode.kind](form.model)}
        </Heading>
        {mode.kind !== "add" && (
          <Text type="supporting" wordBreak="break-word">
            {t.formKey(form.provider, unitWord(form.unit))}
          </Text>
        )}
      </VStack>
      {mode.kind === "edit" && <PriceReference entry={mode.entry} />}
      <PriceEditor
        key={opened}
        form={form}
        isKeyFixed={mode.kind !== "add"}
        onChange={setForm}
        busy={busy === "save"}
        onCancel={() => close(true)}
        onSave={(change) => void run("save", () => savePrice(change), t.saved)}
      />
    </VStack>
  );

  // 表单放在哪：修改时就地展开在那一行下面（宽屏是表格的展开行，窄屏把列表在那一项后面断开）；
  // 设单价时在「未设单价」列表下面；新增时在最下面。
  const editingId = form && mode.kind === "edit" ? keyOf(mode.entry) : null;
  const editingAt = editingId === null ? -1 : listed.findIndex(({ id }) => id === editingId);
  const expansion = useTableRowExpansion<EntryRow>({
    expandedKeys: new Set(editingId ? [editingId] : []),
    onToggle: () => close(true),
    getRowKey: (row) => row.id,
    renderExpanded: () => editor,
    getIsItemExpandable: (row) => row.id === editingId,
  });

  return (
    <SettingsSection id="config-prices" title={t.title} description={t.hint(prices?.preset_as_of ?? null)}>
      {notice && <Banner status="success" title={notice} isDismissable onDismiss={() => setNotice(null)} />}
      {failure && <FailureNotice failure={failure} />}
      {!prices && !failure && (
        <Text as="p" color="secondary" role="status">
          {t.loading}
        </Text>
      )}
      {prices && prices.unpriced.length > 0 && (
        <VStack gap={2}>
          <Banner status="warning" title={t.unpriced.title} description={t.unpriced.hint} />
          <List hasDividers density="compact">
            {prices.unpriced.map((u) => (
              <ListItem
                key={`${u.provider}|${u.model}|${u.unit}`}
                label={u.model}
                description={`${services[u.service] ?? u.service} · ${u.provider} · ${unitWord(u.unit)}`}
                endContent={
                  <TouchButton
                    size="sm"
                    variant="ghost"
                    label={t.formTitle.price(u.model)}
                    isDisabled={busy !== null}
                    onClick={() => open(priceFormOf({ ...u, preset: null, catalog: null, override: null }), { kind: "price" })}
                  >
                    {t.priceIt}
                  </TouchButton>
                }
              />
            ))}
          </List>
          {mode.kind === "price" && editor}
        </VStack>
      )}
      {prices && (
        <HStack gap={2} wrap="wrap" vAlign="center">
          <CatalogLine state={prices.catalog} />
          <TouchButton
            size="sm"
            variant="secondary"
            label={t.catalog.refresh}
            isLoading={busy === "refresh"}
            isDisabled={busy !== null || prices.catalog.fetching}
            onClick={() => void refresh()}
          />
        </HStack>
      )}
      {prices && (
        <VStack gap={3}>
          <TextInput
            label={t.filter}
            isLabelHidden
            placeholder={t.filter}
            value={query}
            onChange={setQuery}
            hasClear
            width={wide ? "calc(var(--spacing-8) * 10)" : "100%"}
          />
          {listed.length === 0 ? (
            <Text color="secondary">{t.noMatch}</Text>
          ) : wide ? (
            <Table data={listed} columns={columns} idKey="id" density="compact" plugins={{ expansion }} />
          ) : (
            <VStack gap={2}>
              <EntryList rows={editingAt < 0 ? listed : listed.slice(0, editingAt + 1)} actions={entryActions} />
              {editingAt >= 0 && editor}
              {editingAt >= 0 && <EntryList rows={listed.slice(editingAt + 1)} actions={entryActions} />}
            </VStack>
          )}
          {query === "" && matching.length > FOLDED_ROWS && (
            <HStack>
              <TouchButton
                size="sm"
                variant="ghost"
                label={showAll ? t.fold : t.showAll(matching.length)}
                onClick={() => setShowAll(!showAll)}
              />
            </HStack>
          )}
        </VStack>
      )}
      {prices && !form && (
        <HStack ref={addRef} gap={2}>
          <TouchButton label={t.add} onClick={() => open(emptyPriceForm(), { kind: "add" })} isDisabled={busy !== null} />
        </HStack>
      )}
      {mode.kind === "add" && editor}
    </SettingsSection>
  );
}

/** 一条单价的键：提供方、模型、计费单位。 */
function keyOf(entry: PriceEntry): string {
  return `${entry.provider}|${entry.model}|${entry.unit}`;
}

/** 窄屏上代替单价表的列表：模型名，副行是提供方、单位和生效单价，行尾是操作。 */
function EntryList({ rows, actions }: { rows: EntryRow[]; actions: (id: string, entry: PriceEntry) => ReactNode }) {
  if (rows.length === 0) return null;
  return (
    <List hasDividers density="compact">
      {rows.map(({ id, entry }) => (
        <ListItem
          key={id}
          label={entry.model}
          description={
            <VStack gap={0.5}>
              <Text type="supporting" wordBreak="break-word">{`${entry.provider} · ${unitWord(entry.unit)}`}</Text>
              <EffectivePrice entry={entry} />
            </VStack>
          }
          endContent={actions(id, entry)}
        />
      ))}
    </List>
  );
}

/** 目录一列的附注：拉取日期，按原厂价格估算的写明对应哪个模型，目录里名字不同的也写明。 */
function catalogNote(entry: PriceEntry) {
  return (price: Price) => {
    const match = matchText(price);
    if (match && price.source === "catalog_upstream") return t.upstream(match);
    if (match && price.match?.model !== entry.model) return `${t.fetchedOn(price.as_of)} · ${t.listedAs(match)}`;
    return t.fetchedOn(price.as_of);
  };
}

/** 筛选：模型名或提供方里含有这几个字（不分大小写）。 */
function matches(entry: PriceEntry, query: string): boolean {
  const q = query.trim().toLowerCase();
  return q === "" || entry.model.toLowerCase().includes(q) || entry.provider.toLowerCase().includes(q);
}

/** 模型名，提供方小一号跟在同一行，放不下时折到下一行。 */
function ModelName({ entry }: { entry: PriceEntry }) {
  return (
    <HStack gap={1.5} wrap="wrap" vAlign="center">
      <Text wordBreak="break-word">{entry.model}</Text>
      <Text type="supporting" wordBreak="break-word">
        {entry.provider}
      </Text>
    </HStack>
  );
}

const COLUMNS = ["override", "catalog", "preset"] as const;

/** 一种单价的附注：后台设定的日期、目录的拉取日期和对应的模型、预设的整理日期。 */
function noteOf(entry: PriceEntry, column: (typeof COLUMNS)[number], price: Price): string {
  if (column === "override") return t.setOn(price.as_of);
  if (column === "preset") return t.asOf(price.as_of);
  return catalogNote(entry)(price);
}

/**
 * 生效的单价：价格和它来自哪一种（后台设定、目录、预设）。附注只留有新信息的：后台设定的日期，目录里
 * 按原厂价格估算或名字不同时对应哪个模型；目录的拉取日期在表格上方、预设的整理日期在这一节的说明里，
 * 每行重复一遍只是噪音，修改时的对照里才逐条列出。另外两种单价也只在修改时列出。
 */
function EffectivePrice({ entry }: { entry: PriceEntry }) {
  const column = effectiveColumn(entry);
  const price = column && entry[column];
  if (!column || !price) return <Text color="secondary">{t.none}</Text>;
  const full = noteOf(entry, column, price);
  const note = column === "override" || (column === "catalog" && full !== t.fetchedOn(price.as_of)) ? full : null;
  return (
    <VStack gap={0.5}>
      <HStack gap={1.5} wrap="wrap" vAlign="center">
        <Text>{formatPrice(price, entry.unit)}</Text>
        <Token size="sm" color={column === "override" ? "blue" : "gray"} label={t.columns[column]} />
      </HStack>
      {note && (
        <Text type="supporting" wordBreak="break-word">
          {note}
        </Text>
      )}
    </VStack>
  );
}

/** 修改时作参考：这条的三种单价，生效的那一种标上「生效」。 */
function PriceReference({ entry }: { entry: PriceEntry }) {
  const column = effectiveColumn(entry);
  return (
    <MetadataList columns="multi">
      {COLUMNS.map((c) => {
        const price = entry[c];
        return (
          <MetadataListItem key={c} label={t.columns[c]}>
            {price ? (
              <VStack gap={0.5}>
                <HStack gap={1} wrap="wrap" vAlign="center">
                  <Text>{formatPrice(price, entry.unit)}</Text>
                  {column === c && <Token size="sm" color="green" label={t.inEffect} />}
                </HStack>
                <Text type="supporting" wordBreak="break-word">
                  {noteOf(entry, c, price)}
                </Text>
              </VStack>
            ) : (
              <Text color="secondary">{t.none}</Text>
            )}
          </MetadataListItem>
        );
      })}
    </MetadataList>
  );
}

/** 在线目录的状态：拉取时间，或者正在拉取、从没拉取成功、最近一次拉取失败的原因。 */
function CatalogLine({ state }: { state: CatalogState }) {
  const status = catalogStatus(state);
  if (status === "fetching" || status === "never") {
    return (
      <Text color="secondary" role="status">
        {status === "fetching" ? t.catalog.fetching : t.catalog.never}
      </Text>
    );
  }
  if (status === "unreachable") return <Text color="secondary">{t.catalog.unreachable(state.error ?? "")}</Text>;
  return (
    <VStack gap={0.5}>
      <Text color="secondary">
        {t.catalog.fresh} <Timestamp value={state.fetched_at ?? ""} format="date_time" />
      </Text>
      {status === "kept" && (
        <Text type="supporting" wordBreak="break-word">
          {t.catalog.kept(state.error ?? "")}（{t.catalog.failedAt} <Timestamp value={state.failed_at ?? ""} format="date_time" />）
        </Text>
      )}
    </VStack>
  );
}

/** 单价表单。`isKeyFixed` 时（修改一条、给未设单价的模型设单价）提供方、模型和单位写在标题里，
 * 这里不列：只填单价和币种。 */
function PriceEditor({
  form,
  isKeyFixed,
  onChange,
  busy,
  onCancel,
  onSave,
}: {
  form: PriceForm;
  isKeyFixed: boolean;
  onChange: (form: PriceForm) => void;
  busy: boolean;
  onCancel: () => void;
  onSave: (change: PriceChange) => void;
}) {
  const result = priceChangeOf(form);
  // 刚打开的空表单不先报「不能为空」：点过一次保存才标出所有不对的项（见 useSubmitCheck）。
  // 每次打开表单换 key，重新开始。
  const check = useSubmitCheck<HTMLFormElement>();
  const set = (field: FormField) => (value: string) => onChange({ ...form, [field]: value });
  const problemOf = (field: FormField) =>
    check.shown && "problems" in result ? (result.problems.find((p) => p.field === field) ?? null) : null;

  function submit(event: FormEvent) {
    event.preventDefault();
    if ("change" in result) onSave(result.change);
    else check.refuse();
  }

  function text(field: "provider" | "model" | "input" | "output") {
    const label = t.fields[field];
    const problem = problemOf(field);
    return (
      <TextInput
        label={label}
        description={t.formHints[field]}
        value={form[field]}
        onChange={set(field)}
        isOptional={field === "output"}
        status={problem ? { type: "error", message: t.problems[problem.reason](label) } : undefined}
        autoComplete="off"
      />
    );
  }

  return (
    <form ref={check.ref} onSubmit={submit} noValidate>
      <FormLayout>
        {!isKeyFixed && text("provider")}
        {!isKeyFixed && text("model")}
        {!isKeyFixed && (
          <Selector
            label={t.fields.unit}
            value={form.unit}
            onChange={(value) => set("unit")(String(value))}
            options={UNITS.map((u) => ({ value: u, label: t.units[u] ?? u }))}
          />
        )}
        <Selector
          label={t.fields.currency}
          value={form.currency}
          onChange={(value) => set("currency")(String(value))}
          options={CURRENCIES.map((c) => ({ value: c, label: t.currencies[c] ?? c }))}
        />
        {text("input")}
        {text("output")}
        <HStack gap={2}>
          <TouchButton type="submit" variant="primary" label={t.save} isLoading={busy} isDisabled={busy} />
          <TouchButton variant="ghost" label={copy.common.cancel} onClick={onCancel} isDisabled={busy} />
        </HStack>
      </FormLayout>
    </form>
  );
}
