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
import { VStack } from "@astryxdesign/core/VStack";
import { FormEvent, useEffect, useState } from "react";

import { FailureNotice } from "@/components/FailureNotice";
import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import {
  CURRENCIES,
  emptyPriceForm,
  formatPrice,
  getPrices,
  priceChangeOf,
  priceFormOf,
  type PriceChange,
  type PriceEntry,
  type PriceForm,
  type Prices,
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

/**
 * 「配置」页的单价一节：列出所有预设和后台设定的单价，可以修改、恢复成预设（没有预设的就删除）、
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
      key: "preset",
      header: t.columns.preset,
      width: proportional(2),
      renderCell: ({ entry }) =>
        entry.preset ? (
          <VStack gap={0.5}>
            <Text>{formatPrice(entry.preset, entry.unit)}</Text>
            <Text type="supporting">{t.asOf(entry.preset.as_of)}</Text>
          </VStack>
        ) : (
          t.none
        ),
    },
    {
      key: "override",
      header: t.columns.override,
      width: proportional(2),
      renderCell: ({ entry }) =>
        entry.override ? (
          <VStack gap={0.5}>
            <Text>{formatPrice(entry.override, entry.unit)}</Text>
            <Text type="supporting">{t.setOn(entry.override.as_of)}</Text>
          </VStack>
        ) : (
          t.none
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
              label={entry.preset ? t.restore : t.remove}
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
                    onClick={() => open(priceFormOf({ ...u, preset: null, override: null }))}
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
