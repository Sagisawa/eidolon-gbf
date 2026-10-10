// 名单准备：后端的角色列表排成光谱。按组合的官方顺序分段，组合里按偶像编号排；
// 新角色只要在配置里填好偶像编号，就自动排进她组合里的正确位置，不用改落地页。

import type { Character } from "@/lib/api";

import { idolColors, type IdolColors } from "./color";

export type RosterEntry = Pick<Character, "id" | "name" | "color" | "idol_id" | "unit" | "unit_order">;

export type SpectrumIdol = {
  id: string;
  name: string;
  idolId: number | null;
  colors: IdolColors;
};

export type SpectrumUnit = {
  /** 组合名；查不到组合的偶像排在最后一段，这一段没有名字。 */
  name: string | null;
  idols: SpectrumIdol[];
};

export type Spectrum = {
  units: SpectrumUnit[];
  /** 整条光谱从头到尾的顺序：各段依次连起来。 */
  idols: SpectrumIdol[];
};

/** 没有编号、没有组合的排在后面；两边都没有时排不出先后（Infinity − Infinity 是 NaN，记成 0），
 * 保持传进来的顺序（sort 是稳定的）。 */
const ascending = (a: number | null, b: number | null) => (a ?? Infinity) - (b ?? Infinity) || 0;

export function prepareSpectrum(characters: RosterEntry[]): Spectrum {
  const sorted = [...characters].sort(
    (a, b) => ascending(a.unit_order, b.unit_order) || ascending(a.idol_id, b.idol_id),
  );
  const units: SpectrumUnit[] = [];
  for (const c of sorted) {
    let unit = units.at(-1);
    if (!unit || unit.name !== c.unit) units.push((unit = { name: c.unit, idols: [] }));
    unit.idols.push({ id: c.id, name: c.name, idolId: c.idol_id, colors: idolColors(c.color) });
  }
  return { units, idols: units.flatMap((u) => u.idols) };
}
