// 设置页里编辑制作人档案用的草稿：空白表示这一项沿用默认（CONTEXT.md「制作人档案」），
// 保存时存成 null 交回后端。

import type { Gender, ProducerProfile } from "@/lib/api";

/** 和后端的 MAX_FORM_OF_ADDRESS_LENGTH 一致，按字数（Python 的 len）计算。 */
export const MAX_FORM_OF_ADDRESS = 20;

export type Draft = { formOfAddress: string; gender: Gender | ""; timezone: string };

export function toDraft(profile: ProducerProfile): Draft {
  return {
    formOfAddress: profile.form_of_address ?? "",
    gender: profile.gender ?? "",
    timezone: profile.timezone ?? "",
  };
}

export function fromDraft(draft: Draft): ProducerProfile {
  return {
    form_of_address: draft.formOfAddress.trim() || null,
    gender: draft.gender || null,
    timezone: draft.timezone || null,
  };
}

/** 两份草稿存下去是否一样（称呼两端的空白保存时会去掉，不算改动）。 */
export function sameDraft(a: Draft, b: Draft): boolean {
  return (
    a.formOfAddress.trim() === b.formOfAddress.trim() &&
    a.gender === b.gender &&
    a.timezone === b.timezone
  );
}

/** 称呼最多 MAX_FORM_OF_ADDRESS 个字；按字截，不会把一个字切成两半。 */
export function clampFormOfAddress(value: string): string {
  const chars = Array.from(value);
  return chars.length > MAX_FORM_OF_ADDRESS ? chars.slice(0, MAX_FORM_OF_ADDRESS).join("") : value;
}
