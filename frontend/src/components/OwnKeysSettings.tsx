"use client";

import { InfoIcon } from "lucide-react";
import { FormEvent, useEffect, useId, useState, type ReactNode } from "react";

import { FailureNotice } from "@/components/app/FailureNotice";
import { SettingsSection } from "@/components/app/SettingsSection";
import { Button } from "@/components/ui/button";
import { Field, FieldGroup, FieldLabel, FieldLegend, FieldSet } from "@/components/ui/field";
import { Input } from "@/components/ui/input";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { Spinner } from "@/components/ui/spinner";
import { copy } from "@/i18n";
import { checkOwnLLM, checkOwnSpeechKey, getAccount, getLimitExemption, type LimitExemption } from "@/lib/api";
import { exemptionNote, sayServices } from "@/lib/exemptingKeys";
import { toFailure, type Failure } from "@/lib/failure";
import {
  canKeepOwnKeys,
  forgetOwnKey,
  keepOwnKey,
  last4,
  localOwnKeys,
  LLM_PROTOCOLS,
  ownServices,
  STT_PROVIDERS,
  type LLMProtocol,
  type LocalLLM,
  type LocalOwnKeys,
  type LocalTtsKey,
  type OwnService,
  type SttProvider,
} from "@/lib/localOwnKeys";
import { cn } from "@/lib/utils";

const t = copy.settings.ownKeys;

/**
 * 用户自带、自己付费的密钥。三项都只存在这个浏览器里，按登录的用户分开存；填写时服务器只试调、
 * 不保存。浏览器存不了时如实说，表单停用，不退而存在内存里。
 */
export function OwnKeysSettings() {
  const [userId, setUserId] = useState<string | null>(null);
  /** 这个部署的免限额密钥，和 `userId` 一起从账号读到。 */
  const [exemptingKeys, setExemptingKeys] = useState<OwnService[]>([]);
  const [kept, setKept] = useState<LocalOwnKeys>({});
  const [canKeep, setCanKeep] = useState(true);
  const [failure, setFailure] = useState<Failure | null>(null);
  // 服务器对哪几项服务答的豁免；和现在存的对不上（还没问到）或问失败时，不显示那句说明。
  const [answered, setAnswered] = useState<{ services: string; exemption: LimitExemption } | null>(null);
  const services = ownServices(kept).join(",");

  useEffect(() => {
    if (userId === null) return;
    const own = ownServices(kept);
    let current = true;
    getLimitExemption(own).then(
      (exemption) => {
        if (current) setAnswered({ services: own.join(","), exemption });
      },
      () => {
        if (current) setAnswered(null);
      },
    );
    return () => {
      current = false;
    };
  }, [userId, kept]);

  useEffect(() => {
    getAccount().then(
      (account) => {
        setUserId(account.id);
        setExemptingKeys(account.exempting_keys);
        setKept(localOwnKeys(account.id));
        setCanKeep(canKeepOwnKeys());
      },
      (e) => setFailure(toFailure(e)),
    );
  }, []);

  if (failure && !userId) {
    return (
      <SettingsSection>
        <FailureNotice failure={failure} />
      </SettingsSection>
    );
  }
  if (!userId) return null;

  /** 改了浏览器里存的 key，再按存下的显示：存不下的就是没存。 */
  const change = (keep: () => void) => {
    keep();
    setKept(localOwnKeys(userId));
  };

  return (
    <SettingsSection
      description={
        <>
          {t.summary}
          {/* ⓘ：悬停或点开都弹出其余说明；用 Popover 不用 Tooltip，Tooltip 不响应触摸，也不该装长段文字。
              只此一处，按 shadcn 纪律直接写在这里，不抽成项目组件。 */}
          <Popover>
            <PopoverTrigger
              openOnHover
              render={<Button variant="ghost" size="icon-xs" className="ml-0.5 align-middle" aria-label={t.detailsLabel} />}
            >
              <InfoIcon />
            </PopoverTrigger>
            <PopoverContent align="start">
              <ul className="flex list-disc flex-col gap-1 pl-4">
                {t.details.map((line) => (
                  <li key={line}>{line}</li>
                ))}
              </ul>
            </PopoverContent>
          </Popover>
        </>
      }
    >
      {!canKeep && <FailureNotice failure={{ message: t.cannotKeep, signedOut: false }} />}
      <p className="text-body">{sayServices(t.exempting, exemptingKeys)}</p>
      <p role="status" className="text-body">
        {answered?.services === services && exemptionNote(answered.exemption, exemptingKeys)}
        {t.perCallLimits}
      </p>
      <div className="flex flex-col gap-4">
        <OwnLLMForm
          current={kept.llm}
          disabled={!canKeep}
          onChecked={(llm) => change(() => keepOwnKey(userId, "llm", llm))}
          onDelete={() => change(() => forgetOwnKey(userId, "llm"))}
        />
        <Separator />
        <OwnSpeechKeyForm
          title={t.ttsTitle}
          current={kept.tts}
          disabled={!canKeep}
          onSubmit={async (apiKey) => {
            await checkOwnSpeechKey("tts", apiKey);
            change(() => keepOwnKey(userId, "tts", { api_key: apiKey }));
          }}
          onDelete={() => change(() => forgetOwnKey(userId, "tts"))}
        />
        <Separator />
        <OwnSpeechKeyForm
          title={t.sttTitle}
          current={kept.stt}
          provider={kept.stt?.provider ?? "soniox"}
          disabled={!canKeep}
          onSubmit={async (apiKey, provider = "soniox") => {
            // 百炼的 key 连同试调判断出的地域一起存，通话时随 key 带上。
            const { region } = await checkOwnSpeechKey("stt", apiKey, provider);
            change(() => keepOwnKey(userId, "stt", { api_key: apiKey, provider, ...(region ? { region } : {}) }));
          }}
          onDelete={() => change(() => forgetOwnKey(userId, "stt"))}
        />
      </div>
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
  disabled,
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
  /** 这个浏览器存不了：不能填写、修改。 */
  disabled: boolean;
  onEdit: () => void;
  onDelete: () => void;
  children: ReactNode;
}) {
  return (
    <div className="flex flex-col gap-3">
      <div className="flex flex-col gap-1">
        <h3 className="text-row-name">{title}</h3>
        {hint && <p className="text-body text-muted-foreground">{hint}</p>}
      </div>
      {!editing && (
        <div className="flex flex-wrap items-center gap-2">
          <div className="flex min-w-0 flex-1 flex-col gap-0.5">
            {summary.map((line) => (
              <p key={line} className={cn("text-body break-words", !isSet && "text-muted-foreground")}>
                {line}
              </p>
            ))}
          </div>
          <div className="flex gap-1">
            <Button variant="ghost" size="sm" disabled={disabled} onClick={onEdit}>
              {isSet ? t.edit : t.fill}
            </Button>
            {isSet && (
              <Button variant="ghost" size="sm" aria-label={t.removeLabel(title)} onClick={onDelete}>
                {t.remove}
              </Button>
            )}
          </div>
        </div>
      )}
      {editing && !disabled && children}
    </div>
  );
}

function FormButtons({ busy, canSubmit, onCancel }: { busy: boolean; canSubmit: boolean; onCancel: () => void }) {
  return (
    <div className="flex flex-wrap gap-2">
      <Button type="submit" disabled={!canSubmit || busy}>
        {busy && <Spinner data-icon="inline-start" />}
        {busy ? t.saving : t.save}
      </Button>
      <Button type="button" variant="ghost" onClick={onCancel} disabled={busy}>
        {copy.common.cancel}
      </Button>
    </div>
  );
}

/**
 * 语音合成或语音识别的 key：先让服务器试调一次（它不保存），通过了才存进这个浏览器。语音识别先选服务商
 * 再填 key；改服务商就是换一个 key，同样要填 key、试调。
 */
function OwnSpeechKeyForm({
  title,
  current,
  provider: currentProvider,
  disabled,
  onSubmit,
  onDelete,
}: {
  title: string;
  current: LocalTtsKey | undefined;
  /** 语音识别：已填的 key 所属的服务商，没填时是默认选中的那家。 */
  provider?: SttProvider;
  disabled: boolean;
  /** 试调这把 key（语音识别的连同选的服务商），通过了就存下；不通过时带着服务商的原因失败。 */
  onSubmit: (apiKey: string, provider: SttProvider | undefined) => Promise<void>;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [provider, setProvider] = useState(currentProvider);
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const id = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      await onSubmit(apiKey.trim(), provider);
      setApiKey("");
      setEditing(false);
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }

  function edit() {
    setProvider(currentProvider);
    setEditing(true);
  }

  const summary = current ? [t.last4(last4(current.api_key))] : [t.notSet];
  return (
    <ServiceKey
      title={title}
      summary={current && currentProvider ? [t.sttProviders[currentProvider], ...summary] : summary}
      isSet={!!current}
      editing={editing}
      disabled={disabled}
      onEdit={edit}
      onDelete={onDelete}
    >
      <form onSubmit={submit}>
        <FieldGroup>
          {provider && (
            <FieldSet>
              <FieldLegend variant="label">{t.sttProvider}</FieldLegend>
              <RadioGroup
                value={provider}
                onValueChange={(value) => setProvider(value as SttProvider)}
                className="flex flex-wrap gap-x-6 gap-y-2"
              >
                {STT_PROVIDERS.map((p) => (
                  <Field key={p} orientation="horizontal" className="w-auto">
                    <RadioGroupItem value={p} id={`${id}-${p}`} />
                    <FieldLabel htmlFor={`${id}-${p}`}>{t.sttProviders[p]}</FieldLabel>
                  </Field>
                ))}
              </RadioGroup>
            </FieldSet>
          )}
          <Field>
            <FieldLabel htmlFor={`${id}-key`}>{t.apiKey}</FieldLabel>
            <Input
              id={`${id}-key`}
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              autoComplete="off"
            />
          </Field>
          {failure && <FailureNotice failure={failure} />}
          <FormButtons busy={busy} canSubmit={!!apiKey.trim()} onCancel={() => setEditing(false)} />
        </FieldGroup>
      </form>
    </ServiceKey>
  );
}

/** 自带的 LLM：先让服务器试调一次（它不保存），通过了才存进这个浏览器。 */
function OwnLLMForm({
  current,
  disabled,
  onChecked,
  onDelete,
}: {
  current: LocalLLM | undefined;
  disabled: boolean;
  /** 试调通过的 LLM，地址和模型名按服务器规范化过的。 */
  onChecked: (llm: LocalLLM) => void;
  onDelete: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const [baseUrl, setBaseUrl] = useState(current?.base_url ?? "");
  const [model, setModel] = useState(current?.model ?? "");
  const [protocol, setProtocol] = useState<LLMProtocol>(current?.protocol ?? "chat-completions");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  const id = useId();

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setFailure(null);
    try {
      const llm = { base_url: baseUrl.trim(), api_key: apiKey.trim(), model: model.trim(), protocol };
      onChecked({ ...llm, ...(await checkOwnLLM(llm)) });
      setApiKey("");
      setEditing(false);
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }

  const protocolOptions = LLM_PROTOCOLS.map((p) => ({ value: p, label: t.protocols[p] }));

  return (
    <ServiceKey
      title={t.llmTitle}
      hint={t.llmHint}
      summary={current ? [t.llmCurrent(current.model, current.base_url), t.last4(last4(current.api_key))] : [t.notSet]}
      isSet={!!current}
      editing={editing}
      disabled={disabled}
      onEdit={() => setEditing(true)}
      onDelete={onDelete}
    >
      <form onSubmit={submit}>
        <FieldGroup>
          <Field>
            <FieldLabel htmlFor={`${id}-protocol`}>{t.protocol}</FieldLabel>
            <Select
              items={protocolOptions}
              value={protocol}
              onValueChange={(value) => value && setProtocol(value as LLMProtocol)}
            >
              <SelectTrigger id={`${id}-protocol`} className="w-full">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {protocolOptions.map((option) => (
                  <SelectItem key={option.value} value={option.value}>
                    {option.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </Field>
          <Field>
            <FieldLabel htmlFor={`${id}-base-url`}>{t.baseUrl}</FieldLabel>
            <Input
              id={`${id}-base-url`}
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder="https://api.openai.com/v1"
              autoComplete="off"
            />
          </Field>
          <Field>
            <FieldLabel htmlFor={`${id}-model`}>{t.model}</FieldLabel>
            <Input
              id={`${id}-model`}
              value={model}
              onChange={(event) => setModel(event.target.value)}
              autoComplete="off"
            />
          </Field>
          <Field>
            <FieldLabel htmlFor={`${id}-key`}>{t.apiKey}</FieldLabel>
            <Input
              id={`${id}-key`}
              type="password"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              autoComplete="off"
            />
          </Field>
          {failure && <FailureNotice failure={failure} />}
          <FormButtons
            busy={busy}
            canSubmit={!!baseUrl.trim() && !!model.trim() && !!apiKey.trim()}
            onCancel={() => setEditing(false)}
          />
        </FieldGroup>
      </form>
    </ServiceKey>
  );
}
