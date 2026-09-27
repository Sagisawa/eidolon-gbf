"use client";

import { Button } from "@astryxdesign/core/Button";
import { Divider } from "@astryxdesign/core/Divider";
import { FormLayout } from "@astryxdesign/core/FormLayout";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { Selector } from "@astryxdesign/core/Selector";
import { StackItem } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { TextInput } from "@astryxdesign/core/TextInput";
import { VStack } from "@astryxdesign/core/VStack";
import { FormEvent, useEffect, useState, type ReactNode } from "react";

import { FailureNotice } from "@/components/FailureNotice";
import { SettingsSection } from "@/components/SettingsSection";
import { copy } from "@/i18n";
import {
  deleteOwnKey,
  getOwnKeys,
  saveOwnLLM,
  saveOwnSpeechKey,
  type LLMProtocol,
  type OwnKeys,
  type OwnService,
} from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { limitExemption } from "@/lib/ownKeys";

const t = copy.settings.ownKeys;

const EXEMPTION_NOTES = { all: t.exemptAll, turns: t.exemptTurns, none: t.exemptNone } as const;

/** 用户自带、自己付费的密钥；部署者没有开放时整节不显示。 */
export function OwnKeysSettings() {
  const [keys, setKeys] = useState<OwnKeys | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    getOwnKeys().then(setKeys, (e) => setFailure(toFailure(e)));
  }, []);

  async function remove(service: OwnService) {
    setFailure(null);
    try {
      await deleteOwnKey(service);
      setKeys(await getOwnKeys());
    } catch (e) {
      setFailure(toFailure(e));
    }
  }

  if (failure && !keys) {
    return (
      <SettingsSection title={t.title}>
        <FailureNotice failure={failure} />
      </SettingsSection>
    );
  }
  if (!keys?.available) return null;

  const reload = async () => setKeys(await getOwnKeys());

  return (
    <SettingsSection title={t.title} description={t.hint}>
      <Text as="p" role="status">
        {EXEMPTION_NOTES[limitExemption(keys.exempt)]}
        {t.perCallLimits}
      </Text>
      {failure && <FailureNotice failure={failure} />}
      <VStack gap={4}>
        <OwnLLMForm current={keys.keys.llm} protocols={keys.protocols} onSaved={reload} onDelete={() => remove("llm")} />
        <Divider />
        <OwnSpeechKeyForm
          service="tts"
          title={t.ttsTitle}
          current={keys.keys.tts}
          onSaved={reload}
          onDelete={() => remove("tts")}
        />
        <Divider />
        <OwnSpeechKeyForm
          service="stt"
          title={t.sttTitle}
          current={keys.keys.stt}
          onSaved={reload}
          onDelete={() => remove("stt")}
        />
      </VStack>
    </SettingsSection>
  );
}

/**
 * 一项服务：标题；填过的只显示末 4 位和修改、删除；没填的一行说明加「填写」，点开才是表单，
 * 页面保持安静（PRODUCT.md「角色在前，系统在后」）。
 */
function ServiceKey({
  title,
  hint,
  summary,
  isSet,
  editing,
  onEdit,
  onDelete,
  children,
}: {
  title: string;
  hint?: string;
  /** 一行一句：填过的是末 4 位等，没填的是一句说明。 */
  summary: string[];
  isSet: boolean;
  editing: boolean;
  onEdit: () => void;
  onDelete: () => void;
  children: ReactNode;
}) {
  return (
    <VStack gap={3}>
      <VStack gap={1}>
        <Heading level={3} style={{ fontSize: "var(--text-body-size)" }}>
          {title}
        </Heading>
        {hint && <Text color="secondary">{hint}</Text>}
      </VStack>
      {!editing && (
        <HStack gap={2} vAlign="center" wrap="wrap">
          <StackItem size="fill">
            <VStack gap={0.5}>
              {summary.map((line) => (
                <Text key={line} color={isSet ? "primary" : "secondary"} wordBreak="break-word">
                  {line}
                </Text>
              ))}
            </VStack>
          </StackItem>
          <HStack gap={1}>
            <Button variant="ghost" size="sm" label={isSet ? t.edit : t.fill} onClick={onEdit} />
            {isSet && (
              <Button variant="ghost" size="sm" label={t.removeLabel(title)} onClick={onDelete}>
                {t.remove}
              </Button>
            )}
          </HStack>
        </HStack>
      )}
      {editing && children}
    </VStack>
  );
}

function FormButtons({ busy, canSubmit, onCancel }: { busy: boolean; canSubmit: boolean; onCancel: () => void }) {
  return (
    <HStack gap={2}>
      <Button type="submit" label={busy ? t.saving : t.save} isDisabled={!canSubmit} isLoading={busy} />
      <Button variant="ghost" label={copy.common.cancel} onClick={onCancel} isDisabled={busy} />
    </HStack>
  );
}

function OwnSpeechKeyForm({
  service,
  title,
  current,
  onSaved,
  onDelete,
}: {
  service: "tts" | "stt";
  title: string;
  current: OwnKeys["keys"]["tts"];
  onSaved: () => Promise<void>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      await saveOwnSpeechKey(service, apiKey.trim());
      setApiKey("");
      setEditing(false);
      await onSaved();
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ServiceKey
      title={title}
      summary={current ? [t.last4(current.last4)] : [t.notSet]}
      isSet={!!current}
      editing={editing}
      onEdit={() => setEditing(true)}
      onDelete={onDelete}
    >
      <form onSubmit={submit}>
        <FormLayout>
          <TextInput
            type="password"
            label={t.apiKey}
            value={apiKey}
            onChange={setApiKey}
            autoComplete="off"
          />
          {failure && <FailureNotice failure={failure} />}
          <FormButtons busy={busy} canSubmit={!!apiKey.trim()} onCancel={() => setEditing(false)} />
        </FormLayout>
      </form>
    </ServiceKey>
  );
}

function OwnLLMForm({
  current,
  protocols,
  onSaved,
  onDelete,
}: {
  current: OwnKeys["keys"]["llm"];
  protocols: LLMProtocol[];
  onSaved: () => Promise<void>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [baseUrl, setBaseUrl] = useState(current?.base_url ?? "");
  const [model, setModel] = useState(current?.model ?? "");
  const [protocol, setProtocol] = useState<LLMProtocol>(current?.protocol ?? "chat-completions");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      await saveOwnLLM({ base_url: baseUrl.trim(), api_key: apiKey.trim(), model: model.trim(), protocol });
      setApiKey("");
      setEditing(false);
      await onSaved();
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <ServiceKey
      title={t.llmTitle}
      hint={t.llmHint}
      summary={current ? [t.llmCurrent(current.model, current.base_url), t.last4(current.last4)] : [t.notSet]}
      isSet={!!current}
      editing={editing}
      onEdit={() => setEditing(true)}
      onDelete={onDelete}
    >
      <form onSubmit={submit}>
        <FormLayout>
          <Selector
            label={t.protocol}
            value={protocol}
            onChange={(value) => setProtocol(value as LLMProtocol)}
            options={protocols.map((p) => ({ value: p, label: t.protocols[p] }))}
          />
          <TextInput
            label={t.baseUrl}
            value={baseUrl}
            onChange={setBaseUrl}
            placeholder="https://api.openai.com/v1"
            autoComplete="off"
          />
          <TextInput label={t.model} value={model} onChange={setModel} autoComplete="off" />
          <TextInput type="password" label={t.apiKey} value={apiKey} onChange={setApiKey} autoComplete="off" />
          {failure && <FailureNotice failure={failure} />}
          <FormButtons
            busy={busy}
            canSubmit={!!baseUrl.trim() && !!model.trim() && !!apiKey.trim()}
            onCancel={() => setEditing(false)}
          />
        </FormLayout>
      </form>
    </ServiceKey>
  );
}
