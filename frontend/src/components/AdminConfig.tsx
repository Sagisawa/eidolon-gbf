"use client";

import { Banner } from "@astryxdesign/core/Banner";
import { Button } from "@astryxdesign/core/Button";
import { FormLayout } from "@astryxdesign/core/FormLayout";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { Selector } from "@astryxdesign/core/Selector";
import { StatusDot } from "@astryxdesign/core/StatusDot";
import { proportional, Table, type TableColumn } from "@astryxdesign/core/Table";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";
import { FormEvent, useEffect, useState } from "react";

import { FailureNotice } from "@/components/FailureNotice";
import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import {
  getAdminConfig,
  llmChange,
  llmForm,
  llmRows,
  restoreChatLLM,
  saveChatLLM,
  statusDisplay,
  type AdminConfig as Config,
  type FieldRow,
  type LLMField,
  type LLMForm,
} from "@/lib/adminConfig";
import type { LLMProtocol } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";

const t = copy.admin.config;

const PROTOCOLS: LLMProtocol[] = ["chat-completions", "responses", "anthropic"];

/** 后台的「配置」页：每一项列出 .env 的值、当前生效的值和状态，可以修改、恢复。 */
export function AdminConfig() {
  const [config, setConfig] = useState<Config | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    getAdminConfig().then(setConfig, (e) => setFailure(toFailure(e)));
  }, []);

  return (
    <VStack gap={2}>
      <Heading level={1} style={{ fontSize: "var(--text-large-size)" }}>
        {copy.admin.pages.config}
      </Heading>
      <Text as="p" color="secondary">
        {t.intro}
      </Text>
      {failure && !config && <FailureNotice failure={failure} />}
      {!failure && !config && (
        <Text as="p" color="secondary" role="status">
          {t.loading}
        </Text>
      )}
      {config && <ChatLLMConfig config={config} onChange={setConfig} />}
    </VStack>
  );
}

/** 一个值在表里的样子：key 只有末 4 位，max_tokens 没设时是接口类型的默认值。 */
function shown(field: LLMField, value: FieldRow["env"]): string {
  if (value === null) return field === "max_tokens" ? t.defaultMaxTokens : t.none;
  if (field === "api_key") return t.last4(String(value));
  if (field === "protocol") return t.protocols[value as LLMProtocol] ?? String(value);
  return String(value);
}

const COLUMNS: TableColumn<FieldRow>[] = [
  { key: "field", header: t.columns.field, width: proportional(1), renderCell: (row) => t.fields[row.field] },
  { key: "env", header: t.columns.env, width: proportional(2), renderCell: (row) => shown(row.field, row.env) },
  {
    key: "effective",
    header: t.columns.effective,
    width: proportional(2),
    renderCell: (row) => shown(row.field, row.effective),
  },
  {
    key: "override",
    header: t.columns.override,
    width: proportional(2),
    renderCell: (row) =>
      row.overridden ? (
        <HStack gap={2} vAlign="center" wrap="wrap">
          <Text wordBreak="break-word">{shown(row.field, row.override)}</Text>
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

/**
 * 扮演角色的 LLM：状态、三列对照（.env、当前生效、后台覆盖），修改表单和恢复按钮。
 * 保存时后端先试调，试不通照原话显示原因、不保存。
 */
function ChatLLMConfig({ config, onChange }: { config: Config; onChange: (config: Config) => void }) {
  const item = config.chat_llm;
  const display = statusDisplay(item);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<LLMForm>(() => llmForm(item.effective));
  const [busy, setBusy] = useState<"save" | "restore" | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const change = llmChange(form, config.keys_editable);

  function edit() {
    setForm(llmForm(item.effective));
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
    if (change) void run("save", () => saveChatLLM(change), t.saved);
  }

  const set = (field: keyof LLMForm) => (value: string) => setForm((f) => ({ ...f, [field]: value }));

  return (
    <SettingsSection title={t.chatLLM.title} description={t.chatLLM.hint}>
      <HStack gap={2} vAlign="center" wrap="wrap">
        <StatusDot variant={display.variant} label={t.status[item.status]} />
        <Text>{t.status[item.status]}</Text>
      </HStack>
      {display.failure && <Banner status="warning" title={t.status.failed} description={t.failed(display.failure)} />}
      {notice && <Banner status="success" title={notice} isDismissable onDismiss={() => setNotice(null)} />}
      {failure && <FailureNotice failure={failure} />}
      <Table data={llmRows(item)} columns={COLUMNS} idKey="field" density="compact" />
      {!editing && (
        <HStack gap={2} wrap="wrap">
          <Button label={t.edit} onClick={edit} isDisabled={busy !== null} />
          {display.canRestore && (
            <Button
              variant="ghost"
              label={t.restore}
              isLoading={busy === "restore"}
              isDisabled={busy !== null}
              onClick={() => void run("restore", restoreChatLLM, t.restored)}
            />
          )}
        </HStack>
      )}
      {editing && (
        <form onSubmit={submit}>
          <FormLayout>
            <Selector
              label={t.fields.protocol}
              value={form.protocol}
              onChange={(value) => setForm((f) => ({ ...f, protocol: value as LLMProtocol }))}
              options={PROTOCOLS.map((p) => ({ value: p, label: t.protocols[p] }))}
            />
            <TextInput label={t.fields.base_url} value={form.base_url} onChange={set("base_url")} autoComplete="off" />
            <TextInput label={t.fields.model} value={form.model} onChange={set("model")} autoComplete="off" />
            <TextInput
              label={t.fields.max_tokens}
              description={t.maxTokensHint}
              value={form.max_tokens}
              onChange={set("max_tokens")}
              autoComplete="off"
            />
            <TextInput
              type="password"
              label={t.fields.api_key}
              description={config.keys_editable ? t.apiKeyHint : t.keysReadOnly}
              value={form.api_key}
              onChange={set("api_key")}
              isDisabled={!config.keys_editable}
              autoComplete="off"
            />
            <HStack gap={2}>
              <Button
                type="submit"
                label={busy === "save" ? t.saving : t.save}
                isLoading={busy === "save"}
                isDisabled={!change || busy !== null}
              />
              <Button variant="ghost" label={copy.common.cancel} onClick={() => setEditing(false)} isDisabled={busy !== null} />
            </HStack>
          </FormLayout>
        </form>
      )}
    </SettingsSection>
  );
}
