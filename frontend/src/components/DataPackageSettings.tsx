"use client";

import { useId, useRef, useState, type ChangeEvent } from "react";

import { FailureNotice } from "@/components/app/FailureNotice";
import { useDirectory } from "@/components/conversations/ConversationDirectory";
import { SettingsSection } from "@/components/app/SettingsSection";
import { useSettingsValues } from "@/components/settings/SettingsValues";
import { Alert, AlertTitle } from "@/components/ui/alert";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Spinner } from "@/components/ui/spinner";
import { copy } from "@/i18n";
import { getProfile, importDataPackage, listMemories } from "@/lib/api";
import {
  OFFERED,
  choose,
  chosenCategories,
  exportHref,
  importFailureMessage,
  importSummary,
  isDisabled,
  readManifest,
  selectAll,
  type Category,
  type Choice,
} from "@/lib/dataPackage";
import { toFailure, type Failure } from "@/lib/failure";
import { toDraft } from "@/lib/producerProfile";
import { cn } from "@/lib/utils";
import { SuccessIcon } from "@/theme/icons";

const t = copy.settings.dataPackage;

/**
 * 数据包（GLOSSARY.md「数据包」）：上半导出，勾要带的几类、点「导出」浏览器直接下载；下半导入，选了文件先读开头的
 * manifest.json，按包里有的几类列勾选框，点「导入」把文件原样传上去，完了说一句结果，并刷新受影响的数据。
 */
export function DataPackageSettings() {
  return (
    <>
      <ExportSection />
      <ImportSection />
    </>
  );
}

function ExportSection() {
  const [choice, setChoice] = useState<Choice>(() => selectAll(OFFERED));
  const categories = chosenCategories(choice);

  return (
    <SettingsSection title={t.exportTitle} description={t.exportHint}>
      <Categories offered={OFFERED} choice={choice} onChange={setChoice} />
      <div className="flex flex-col items-start gap-2">
        {categories.length > 0 ? (
          <Button nativeButton={false} render={<a href={exportHref(categories)} download />}>
            {t.export}
          </Button>
        ) : (
          <Button disabled>{t.export}</Button>
        )}
        <p className="text-meta text-muted-foreground">{t.notIncluded}</p>
      </div>
    </SettingsSection>
  );
}

type Picked =
  | { kind: "none" }
  | { kind: "reading"; file: File }
  | { kind: "ready"; file: File; offered: Category[] }
  | { kind: "refused"; file: File; message: string };

function ImportSection() {
  const { profileSaved, memoryCountChanged } = useSettingsValues();
  const { refresh } = useDirectory();
  const input = useRef<HTMLInputElement>(null);
  const [picked, setPicked] = useState<Picked>({ kind: "none" });
  const [choice, setChoice] = useState<Choice>({});
  const [importing, setImporting] = useState(false);
  const [summary, setSummary] = useState<string | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  async function pick(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = ""; // 同一个文件再选一次也算
    if (!file) return;
    setSummary(null);
    setFailure(null);
    setPicked({ kind: "reading", file });
    const reading = await readManifest(file);
    if (reading.kind === "package") {
      setPicked({ kind: "ready", file, offered: reading.categories });
      setChoice(selectAll(reading.categories));
    } else {
      setPicked({ kind: "refused", file, message: t.failures[reading.kind] });
    }
  }

  async function submit() {
    if (picked.kind !== "ready") return;
    setImporting(true);
    setSummary(null);
    setFailure(null);
    try {
      const result = await importDataPackage(picked.file, chosenCategories(choice));
      setSummary(importSummary(result));
      setPicked({ kind: "none" });
      // 导入已经成功了：没刷新到档案、记忆条数、对话列表也不报失败，那几处打开时自己会再读。
      if (result.conversations > 0) refresh();
      if (result.profile) getProfile().then((saved) => profileSaved(toDraft(saved)), () => {});
      if (result.memories > 0) listMemories().then((list) => memoryCountChanged(list.length), () => {});
    } catch (e) {
      setFailure({ ...toFailure(e), message: importFailureMessage(e) });
    } finally {
      setImporting(false);
    }
  }

  return (
    <SettingsSection title={t.importTitle} description={t.importHint}>
      {summary && (
        <Alert role="status">
          <SuccessIcon />
          <AlertTitle>{summary}</AlertTitle>
        </Alert>
      )}
      {failure && <FailureNotice failure={failure} />}
      <div className="flex flex-wrap items-center gap-3">
        <input
          ref={input}
          type="file"
          accept=".zip,application/zip"
          className="sr-only"
          tabIndex={-1}
          aria-hidden
          onChange={pick}
        />
        <Button variant="outline" disabled={importing} onClick={() => input.current?.click()}>
          {t.chooseFile}
        </Button>
        {picked.kind !== "none" && (
          <span className="min-w-0 truncate text-subtitle text-muted-foreground">{picked.file.name}</span>
        )}
      </div>
      {picked.kind === "reading" && <p className="text-body text-muted-foreground">{t.reading}</p>}
      {picked.kind === "refused" && <FailureNotice failure={{ message: picked.message, signedOut: false }} />}
      {picked.kind === "ready" &&
        (picked.offered.length === 0 ? (
          <p className="text-body text-muted-foreground">{t.nothingToChoose}</p>
        ) : (
          <>
            <Categories offered={picked.offered} choice={choice} onChange={setChoice} />
            <div>
              <Button disabled={importing || chosenCategories(choice).length === 0} onClick={submit}>
                {importing && <Spinner data-icon="inline-start" />}
                {importing ? t.importing : t.import}
              </Button>
            </div>
          </>
        ))}
    </SettingsSection>
  );
}

/** 几类的勾选框，按清单的顺序；照片缩进挂在对话下面。 */
function Categories({
  offered,
  choice,
  onChange,
}: {
  offered: readonly Category[];
  choice: Choice;
  onChange: (choice: Choice) => void;
}) {
  const id = useId();
  return (
    <ul className="flex flex-col">
      {offered.map((category) => {
        const disabled = isDisabled(choice, category);
        return (
          <li key={category}>
            <label
              htmlFor={`${id}-${category}`}
              className={cn("flex items-center gap-3 py-1.5", category === "photos" && "pl-7")}
            >
              <Checkbox
                id={`${id}-${category}`}
                checked={Boolean(choice[category]) && !disabled}
                disabled={disabled}
                onCheckedChange={(checked) => onChange(choose(choice, category, checked))}
              />
              <span className="text-body">{t.categories[category]}</span>
            </label>
          </li>
        );
      })}
    </ul>
  );
}
