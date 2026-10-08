"use client";

import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { HStack, Layout, LayoutContent, LayoutFooter, VStack } from "@astryxdesign/core/Layout";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { RadioList, RadioListItem } from "@astryxdesign/core/RadioList";
import { Text } from "@astryxdesign/core/Text";
import { TextArea } from "@astryxdesign/core/TextArea";
import { useEffect, useState } from "react";

import { TouchButton } from "@/components/admin/DashboardParts";
import { FailureNotice } from "@/components/FailureNotice";
import { copy } from "@/i18n";
import { getAdminConfig, isAvailable } from "@/lib/adminConfig";
import {
  limitDraft,
  limitsInput,
  setUserLimits,
  type AdminUserDetails,
  type LimitDraft,
} from "@/lib/adminUsers";
import { toFailure, type Failure } from "@/lib/failure";

const t = copy.admin.users.limitsDialog;

const NOTE_MAX = 500;
const COUNT_MAX = 100_000;

/**
 * 设定或修改一位用户的单独限额：每小时的回合数和通话次数各自选「跟随全站 / 设定次数 / 不限 /
 * 只能用自带密钥」，次数从 1 起；附一句只有管理者看得到的备注。「只能用自带密钥」是单列的一项，
 * 不再让人填 0：全站限额里 0 是不限，同一个数字两处意思相反容易配错。`user` 为 null 时对话框关着；
 * 保存成功后把后端返回的这位用户交给 `onSaved`。
 */
export function UserLimitsDialog({
  user,
  onClose,
  onSaved,
}: {
  user: AdminUserDetails | null;
  onClose: () => void;
  onSaved: (user: AdminUserDetails) => void;
}) {
  const [turns, setTurns] = useState<LimitDraft>(limitDraft(null));
  const [calls, setCalls] = useState<LimitDraft>(limitDraft(null));
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState<Failure | null>(null);
  /** 全站现在的每小时回合数和通话次数（配置页「限额」一项当前生效的值）；读不到时选项只写「跟随全站」。 */
  const [site, setSite] = useState<{ turns: number; calls: number } | null>(null);

  useEffect(() => {
    if (!user) return;
    let current = true;
    getAdminConfig().then(
      (config) => {
        const limits = config.limits;
        if (!current || !isAvailable(limits)) return;
        const { turns_per_hour: turns, calls_per_hour: calls } = limits.effective;
        if (typeof turns === "number" && typeof calls === "number") setSite({ turns, calls });
      },
      () => {},
    );
    return () => {
      current = false;
    };
  }, [user]);

  // Opened afresh: start from what the user has now.
  useEffect(() => {
    if (!user) return;
    setTurns(limitDraft(user.limits?.turns_per_hour ?? null));
    setCalls(limitDraft(user.limits?.calls_per_hour ?? null));
    setNote(user.limits?.note ?? "");
    setFailure(null);
  }, [user]);

  const input = limitsInput(turns, calls);

  function close() {
    if (!busy) onClose();
  }

  async function save() {
    if (!user || !input) return;
    setBusy(true);
    setFailure(null);
    try {
      onSaved(await setUserLimits(user.id, input, note));
    } catch (e) {
      setFailure(toFailure(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Dialog isOpen={user !== null} onOpenChange={(open) => !open && close()} purpose="form" width={520}>
      <Layout
        header={<DialogHeader title={t.title(user?.name ?? "")} onOpenChange={() => close()} />}
        content={
          <LayoutContent>
            <VStack gap={5}>
              <Text as="p">{t.hint}</Text>
              <LimitField label={t.turns} draft={turns} onChange={setTurns} site={site?.turns ?? null} />
              <LimitField label={t.calls} draft={calls} onChange={setCalls} site={site?.calls ?? null} />
              <TextArea
                label={t.note}
                description={t.noteHint}
                isOptional
                value={note}
                onChange={setNote}
                maxLength={NOTE_MAX}
              />
              {!input && (
                <Text type="supporting" color="secondary">
                  {t.needsOne}
                </Text>
              )}
              {failure && <FailureNotice failure={failure} />}
            </VStack>
          </LayoutContent>
        }
        footer={
          <LayoutFooter>
            <HStack gap={2} hAlign="end" wrap="wrap">
              <TouchButton label={copy.common.cancel} variant="secondary" onClick={close} isDisabled={busy} />
              <TouchButton
                label={t.confirm}
                variant="primary"
                onClick={save}
                isLoading={busy}
                isDisabled={!input || note.length > NOTE_MAX}
              />
            </HStack>
          </LayoutFooter>
        }
      />
    </Dialog>
  );
}

/**
 * 一项限额：先选种类，选了「设定次数」就在这一项底下填数字。四个选项竖排：手机宽度上横排放不下。
 */
function LimitField({
  label,
  draft,
  onChange,
  site,
}: {
  label: string;
  draft: LimitDraft;
  onChange: (draft: LimitDraft) => void;
  /** 全站现在的数字，0 是不限；不知道时 null。 */
  site: number | null;
}) {
  const count = (
    <NumberInput
      label={t.count(label)}
      isLabelHidden
      value={draft.count}
      onChange={(n) => onChange({ ...draft, count: n })}
      min={1}
      max={COUNT_MAX}
      isIntegerOnly
      units={t.units}
      width={200}
    />
  );
  return (
    <RadioList
      label={label}
      value={draft.choice}
      onChange={(choice) => onChange({ ...draft, choice: choice as LimitDraft["choice"] })}
    >
      <RadioListItem
        value="default"
        label={site === null ? t.choices.default : t.defaultIs(t.siteCount(site))}
      />
      <RadioListItem
        value="number"
        label={t.choices.number}
        description={draft.choice === "number" ? count : undefined}
      />
      <RadioListItem value="unlimited" label={t.choices.unlimited} />
      <RadioListItem value="own_keys" label={t.choices.ownKeys} description={t.ownKeysHint} />
    </RadioList>
  );
}
