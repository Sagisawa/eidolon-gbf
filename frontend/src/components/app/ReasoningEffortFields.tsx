import { Field, FieldDescription, FieldError, FieldLabel } from "@/components/ui/field";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { copy } from "@/i18n";
import { EFFORT_ITEMS, effortChoices, effortLabel } from "@/lib/reasoningEffort";

// 一个模型的思考强度和额外请求参数（GLOSSARY.md「思考强度」）：后台的模型和设置页的自带 LLM 共用这两个字段。
// 取值怎么校验由各自的表单决定，这里只显示传进来的问题。

/** 一项思考强度的下拉框，`choice` 是表单里的值（`EFFORT_UNSET` 或一档）。Anthropic 接口没有「极低」，不列（ADR-0019）。 */
export function EffortField({
  id,
  label,
  hint,
  protocol,
  choice,
  onChoose,
  problem,
}: {
  id: string;
  label: string;
  hint?: string;
  protocol: string;
  choice: string;
  onChoose: (choice: string) => void;
  /** 选的这档填不了时说什么。 */
  problem?: string;
}) {
  return (
    <Field data-invalid={problem ? true : undefined}>
      <FieldLabel htmlFor={id}>{label}</FieldLabel>
      <Select items={EFFORT_ITEMS} value={choice} onValueChange={(value) => value && onChoose(String(value))}>
        <SelectTrigger id={id} className="w-full" aria-invalid={problem ? true : undefined}>
          <SelectValue />
        </SelectTrigger>
        <SelectContent>
          {effortChoices(protocol).map((value) => (
            <SelectItem key={value} value={value}>
              {effortLabel(value)}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
      {hint && <FieldDescription>{hint}</FieldDescription>}
      {problem && <FieldError>{problem}</FieldError>}
    </Field>
  );
}

/** 额外请求参数的多行框：一段 JSON，留空是不设置。 */
export function ExtraBodyField({
  id,
  label,
  hint,
  text,
  onChange,
  problem,
}: {
  id: string;
  label: string;
  hint?: string;
  text: string;
  onChange: (text: string) => void;
  /** 填的不是 JSON 对象时说什么。 */
  problem?: string;
}) {
  return (
    <Field data-invalid={problem ? true : undefined}>
      <FieldLabel htmlFor={id}>
        {label}
        <span className="font-normal text-muted-foreground">{copy.common.optional}</span>
      </FieldLabel>
      <Textarea
        id={id}
        value={text}
        onChange={(event) => onChange(event.target.value)}
        aria-invalid={problem ? true : undefined}
        placeholder='{"enable_thinking": false}'
        spellCheck={false}
        autoComplete="off"
        rows={4}
      />
      {hint && <FieldDescription>{hint}</FieldDescription>}
      {problem && <FieldError>{problem}</FieldError>}
    </Field>
  );
}
