"use client";

import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { HStack, Layout, LayoutContent, LayoutFooter, VStack } from "@astryxdesign/core/Layout";
import { NumberInput } from "@astryxdesign/core/NumberInput";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Text } from "@astryxdesign/core/Text";
import { TextArea } from "@astryxdesign/core/TextArea";
import { useEffect, useState } from "react";

import { TouchButton, useTouch } from "@/components/admin/DashboardParts";
import { FailureNotice } from "@/components/FailureNotice";
import { copy } from "@/i18n";
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
 * 设定或修改一位用户的单独限额：每小时的回合数和通话次数各自选「跟随全站 / 设定次数 / 不限」，
 * 次数填 0 即只能用自带密钥；附一句只有管理者看得到的备注。`user` 为 null 时对话框关着；
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
              <LimitField label={t.turns} draft={turns} onChange={setTurns} />
              <LimitField label={t.calls} draft={calls} onChange={setCalls} />
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

/** 一项限额：先选种类，选了「设定次数」再填数字。 */
function LimitField({
  label,
  draft,
  onChange,
}: {
  label: string;
  draft: LimitDraft;
  onChange: (draft: LimitDraft) => void;
}) {
  const touch = useTouch();
  return (
    <VStack gap={2}>
      <Text type="label">{label}</Text>
      <SegmentedControl
        label={label}
        value={draft.choice}
        onChange={(choice) => onChange({ ...draft, choice: choice as LimitDraft["choice"] })}
        size={touch ? "lg" : "sm"}
      >
        <SegmentedControlItem value="default" label={t.choices.default} />
        <SegmentedControlItem value="number" label={t.choices.number} />
        <SegmentedControlItem value="unlimited" label={t.choices.unlimited} />
      </SegmentedControl>
      {draft.choice === "number" && (
        <NumberInput
          label={t.count(label)}
          description={t.countHint}
          value={draft.count}
          onChange={(count) => onChange({ ...draft, count })}
          min={0}
          max={COUNT_MAX}
          isIntegerOnly
          units={t.units}
          width={240}
        />
      )}
    </VStack>
  );
}
