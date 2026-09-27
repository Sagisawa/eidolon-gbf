// 记忆页：每条记忆都标注来源角色（CONTEXT.md「来源角色」）。

import type { Character, Memory } from "@/lib/api";

/** 这条记忆的来源角色；她已经不在配置里（或角色列表还没取到）时为 null。 */
export function sourceCharacter(memory: Memory, characters: readonly Character[]): Character | null {
  return characters.find((c) => c.id === memory.source_character_id) ?? null;
}
