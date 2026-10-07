"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { FormLayout } from "@astryxdesign/core/FormLayout";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { Selector } from "@astryxdesign/core/Selector";
import { pixel, proportional, Table, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Timestamp } from "@astryxdesign/core/Timestamp";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";
import { FormEvent, useEffect, useState } from "react";

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

interface EntryRow extends Record<string, unknown> {
  id: string;
  entry: PriceEntry;
}

/** 后台拉取目录时，隔多久再读一次单价，看它拉完没有。 */
const POLL_MS = 2000;

/**
 * 「配置」页的单价一节：在线目录的状态和「立即从目录刷新」；预设、后台设定过的和最近用过的模型，
 * 后台设定、目录、预设三种单价并列、标出生效的那一种，可以修改、恢复（回到目录或预设，都没有的就删除）、
 * 新增；最近用过却没有单价的模型单独列出，点一下就能按运行记录里的名字设单价。
 */
export function AdminPrices() {
  const [prices, setPrices] = useState<Prices | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [form, setForm] = useState<PriceForm | null>(null);
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
      setForm(null);
      setNotice(done);
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(null);
    }
  }

  function open(next: PriceForm) {
    setFailure(null);
    setNotice(null);
    setForm(next);
  }

  const columns: TableColumn<EntryRow>[] = [
    {
      key: "model",
      header: t.columns.model,
      width: proportional(2),
      renderCell: ({ entry }) => (
        <VStack gap={0.5}>
          <Text wordBreak="break-word">{entry.model}</Text>
          <Text type="supporting" wordBreak="break-word">
            {entry.provider}
          </Text>
        </VStack>
      ),
    },
    { key: "unit", header: t.columns.unit, width: pixel(72), renderCell: ({ entry }) => unitWord(entry.unit) },
    {
      key: "override",
      header: t.columns.override,
      width: proportional(2),
      renderCell: ({ entry }) => (
        <PriceCell entry={entry} column="override" price={entry.override} note={(p) => t.setOn(p.as_of)} />
      ),
    },
    {
      key: "catalog",
      header: t.columns.catalog,
      width: proportional(2),
      renderCell: ({ entry }) => <PriceCell entry={entry} column="catalog" price={entry.catalog} note={catalogNote(entry)} />,
    },
    {
      key: "preset",
      header: t.columns.preset,
      width: proportional(2),
      renderCell: ({ entry }) => (
        <PriceCell entry={entry} column="preset" price={entry.preset} note={(p) => t.asOf(p.as_of)} />
      ),
    },
    {
      key: "actions",
      header: t.columns.actions,
      width: proportional(1.5),
      renderCell: ({ id, entry }) => (
        <HStack gap={1} wrap="wrap">
          <Button size="sm" variant="ghost" label={t.edit} isDisabled={busy !== null} onClick={() => open(priceFormOf(entry))} />
          {entry.override && (
            <Button
              size="sm"
              variant="ghost"
              label={entry.catalog ? t.restoreTo.catalog : entry.preset ? t.restoreTo.preset : t.remove}
              isLoading={busy === id}
              isDisabled={busy !== null}
              onClick={() => void run(id, () => restorePrice(entry), t.restored)}
            />
          )}
        </HStack>
      ),
    },
  ];

  return (
    <SettingsSection title={t.title} description={t.hint(prices?.preset_as_of ?? null)}>
      {notice && <Banner status="success" title={notice} isDismissable onDismiss={() => setNotice(null)} />}
      {failure && <FailureNotice failure={failure} />}
      {!prices && !failure && (
        <Text as="p" color="secondary" role="status">
          {t.loading}
        </Text>
      )}
      {prices && (
        <HStack gap={2} wrap="wrap" vAlign="center">
          <CatalogLine state={prices.catalog} />
          <Button
            size="sm"
            variant="secondary"
            label={t.catalog.refresh}
            isLoading={busy === "refresh"}
            isDisabled={busy !== null || prices.catalog.fetching}
            onClick={() => void refresh()}
          />
        </HStack>
      )}
      {prices && prices.unpriced.length > 0 && (
        <VStack gap={2}>
          <Heading level={3} style={{ fontSize: "var(--text-body-size)" }}>
            {t.unpriced.title}
          </Heading>
          <Text type="supporting">{t.unpriced.hint}</Text>
          <Table
            data={prices.unpriced.map((u) => ({ id: `${u.provider}|${u.model}|${u.unit}`, ...u }))}
            columns={[
              { key: "service", header: copy.admin.dashboard.cost.service, width: proportional(1), renderCell: (u) => services[u.service] ?? u.service },
              {
                key: "model",
                header: t.columns.model,
                width: proportional(2),
                renderCell: (u) => (
                  <VStack gap={0.5}>
                    <Text wordBreak="break-word">{u.model}</Text>
                    <Text type="supporting" wordBreak="break-word">
                      {u.provider}
                    </Text>
                  </VStack>
                ),
              },
              { key: "unit", header: t.columns.unit, width: pixel(72), renderCell: (u) => unitWord(u.unit) },
              {
                key: "actions",
                header: t.columns.actions,
                width: proportional(1),
                renderCell: (u) => (
                  <Button
                    size="sm"
                    variant="ghost"
                    label={t.priceIt}
                    isDisabled={busy !== null}
                    onClick={() => open(priceFormOf({ ...u, preset: null, catalog: null, override: null }))}
                  />
                ),
              },
            ]}
            idKey="id"
            density="compact"
          />
        </VStack>
      )}
      {prices && (
        <Table
          data={prices.prices.map((entry) => ({ id: `${entry.provider}|${entry.model}|${entry.unit}`, entry }))}
          columns={columns}
          idKey="id"
          density="compact"
        />
      )}
      {prices && !form && (
        <HStack gap={2}>
          <Button label={t.add} onClick={() => open(emptyPriceForm())} isDisabled={busy !== null} />
        </HStack>
      )}
      {form && (
        <PriceEditor
          form={form}
          onChange={setForm}
          busy={busy === "save"}
          onCancel={() => setForm(null)}
          onSave={(change) => void run("save", () => savePrice(change), t.saved)}
        />
      )}
    </SettingsSection>
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

/** 一种单价：价格、附注，生效的那一种标上「生效」。 */
function PriceCell({
  entry,
  column,
  price,
  note,
}: {
  entry: PriceEntry;
  column: "override" | "catalog" | "preset";
  price: Price | null;
  note: (price: Price) => string;
}) {
  if (!price) return <Text color="secondary">{t.none}</Text>;
  return (
    <VStack gap={0.5}>
      <HStack gap={1} wrap="wrap" vAlign="center">
        <Text>{formatPrice(price, entry.unit)}</Text>
        {effectiveColumn(entry) === column && <Token size="sm" color="green" label={t.inEffect} />}
      </HStack>
      <Text type="supporting" wordBreak="break-word">
        {note(price)}
      </Text>
    </VStack>
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

function PriceEditor({
  form,
  onChange,
  busy,
  onCancel,
  onSave,
}: {
  form: PriceForm;
  onChange: (form: PriceForm) => void;
  busy: boolean;
  onCancel: () => void;
  onSave: (change: PriceChange) => void;
}) {
  const result = priceChangeOf(form);
  const problem = "problem" in result ? result.problem : null;
  const set = (field: FormField) => (value: string) => onChange({ ...form, [field]: value });

  function submit(event: FormEvent) {
    event.preventDefault();
    if ("change" in result) onSave(result.change);
  }

  function text(field: "provider" | "model" | "input" | "output") {
    const label = t.fields[field];
    return (
      <TextInput
        label={label}
        description={t.formHints[field]}
        value={form[field]}
        onChange={set(field)}
        isOptional={field === "output"}
        status={problem?.field === field ? { type: "error", message: t.problems[problem.reason](label) } : undefined}
        autoComplete="off"
      />
    );
  }

  return (
    <form onSubmit={submit}>
      <FormLayout>
        <Heading level={3} style={{ fontSize: "var(--text-body-size)" }}>
          {t.formTitle}
        </Heading>
        {text("provider")}
        {text("model")}
        <Selector
          label={t.fields.unit}
          value={form.unit}
          onChange={(value) => set("unit")(String(value))}
          options={UNITS.map((u) => ({ value: u, label: t.units[u] ?? u }))}
        />
        <Selector
          label={t.fields.currency}
          value={form.currency}
          onChange={(value) => set("currency")(String(value))}
          options={CURRENCIES.map((c) => ({ value: c, label: t.currencies[c] ?? c }))}
        />
        {text("input")}
        {text("output")}
        <HStack gap={2}>
          <Button type="submit" label={t.save} isLoading={busy} isDisabled={problem !== null || busy} />
          <Button variant="ghost" label={copy.common.cancel} onClick={onCancel} isDisabled={busy} />
        </HStack>
      </FormLayout>
    </form>
  );
}
