import { Avatar } from "@astryxdesign/core/Avatar";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { MoreMenu } from "@astryxdesign/core/MoreMenu";
import { StackItem } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";

import { imageColorScale } from "@/lib/imageColor";

import { clock } from "./call";
import { ld } from "./herVars";
import type { Character, Message } from "./data";

type Props = {
  characters: Character[];
  conversations: Record<string, Message[]>;
  selectedId: string | null;
  /** 正在通话的角色和已通话秒数。 */
  call: { characterId: string; elapsed: number; connected: boolean } | null;
  onSelect: (id: string) => void;
  onNavigate: (to: "settings" | "memories") => void;
};

/** 选中行：铺她的纸色，次要字也换成在纸色上校验过的颜色。 */
export function selectedRow(color: string): React.CSSProperties {
  const s = imageColorScale(color);
  return { background: ld(s.paper), "--color-text-secondary": ld(s.paperMuted) } as React.CSSProperties;
}

export function ConversationList({ characters, conversations, selectedId, call, onSelect, onNavigate }: Props) {
  return (
    <VStack height="100%">
      <HStack as="header" vAlign="center" paddingInline={4} paddingBlock={3} gap={3}>
        <StackItem size="fill">
          <Heading level={1} style={{ fontSize: "var(--text-large-size)" }}>
            对话
          </Heading>
        </StackItem>
        <MoreMenu
          label="更多操作"
          alignment="end"
          items={[
            { label: "记忆", onClick: () => onNavigate("memories") },
            { label: "设置", onClick: () => onNavigate("settings") },
          ]}
        />
      </HStack>
      <StackItem size="fill" isScrollable>
        <List>
          {characters.map((c) => {
            const last = conversations[c.id]?.at(-1);
            const inCall = call?.characterId === c.id;
            const description = inCall
              ? call.connected
                ? `通话中 ${clock(call.elapsed)}`
                : "正在呼叫…"
              : last
                ? last.from === "her"
                  ? last.zh
                  : `你：${last.text}`
                : "还没有对话";
            return (
              <ListItem
                key={c.id}
                label={c.name}
                description={description}
                isSelected={c.id === selectedId}
                onClick={() => onSelect(c.id)}
                style={c.id === selectedId ? selectedRow(c.color) : undefined}
                startContent={
                  <Avatar
                    src={c.avatar}
                    name={c.name}
                    size="lg"
                    tooltip={false}
                    style={{ boxShadow: `0 0 0 var(--spacing-0-5) ${ld(imageColorScale(c.color).mark)}` }}
                  />
                }
                endContent={
                  last && !inCall ? (
                    <Text type="supporting" color="secondary">
                      {last.time}
                    </Text>
                  ) : undefined
                }
              />
            );
          })}
        </List>
      </StackItem>
      <Text type="supporting" color="secondary" style={{ padding: "var(--spacing-4)" }}>
        非官方粉丝作品，与版权方无关；角色由 AI 扮演。
      </Text>
    </VStack>
  );
}
