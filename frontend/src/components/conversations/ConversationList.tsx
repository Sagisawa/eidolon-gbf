"use client";

import { Avatar } from "@astryxdesign/core/Avatar";
import { Button } from "@astryxdesign/core/Button";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { MoreMenu } from "@astryxdesign/core/MoreMenu";
import { Skeleton } from "@astryxdesign/core/Skeleton";
import { StackItem } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { SignInButton } from "@/components/FailureNotice";
import { copy } from "@/i18n";
import type { Character } from "@/lib/api";
import { showTime } from "@/lib/callTime";
import { dayOf, previewOf, type Preview } from "@/lib/conversationList";
import { listRow } from "@/theme/herVars";

import { useDirectory, type CallInList } from "./ConversationDirectory";
import { useCallTime } from "./useCallTime";

const t = copy.conversationList;

/**
 * 首页的消息列表（DESIGN.md「Conversation list」）：每位角色一行，头像带她的 mark 描边，
 * 下面是最新一次对话的最后一句，右边是时间；选中行铺她的 paper。宽屏时在左栏，窄屏时占满一页。
 */
export function ConversationList({ selectedId }: { selectedId: string | null }) {
  const router = useRouter();
  const { characters, latest, failure, reload, call, leave } = useDirectory();
  const now = useMinute();

  return (
    <VStack height="100%" style={{ background: "var(--color-background-body)" }}>
      <HStack
        as="header"
        vAlign="center"
        gap={3}
        paddingInline={4}
        paddingBlock={3}
        style={{ borderBottom: "var(--border-width) solid var(--color-border)" }}
      >
        <StackItem size="fill">
          <Heading level={1} style={{ fontSize: "var(--text-large-size)" }}>
            {t.title}
          </Heading>
        </StackItem>
        <MoreMenu
          label={t.menu}
          alignment="end"
          items={[
            { label: t.memories, onClick: () => leave(() => router.push("/memories")) },
            { label: t.settings, onClick: () => leave(() => router.push("/settings")) },
          ]}
        />
      </HStack>

      <StackItem size="fill" isScrollable style={{ padding: "var(--spacing-2)" }}>
        {failure ? (
          <EmptyState
            title={t.loadFailed}
            description={failure.message}
            actions={
              failure.signedOut ? (
                <SignInButton />
              ) : (
                <Button label={t.retry} variant="secondary" onClick={reload} />
              )
            }
            isCompact
          />
        ) : characters === null ? (
          <Loading />
        ) : (
          <List aria-label={t.title}>
            {characters.map((c) => (
              <Row
                key={c.id}
                character={c}
                preview={previewOf(latest[c.id])}
                call={call?.characterId === c.id ? call : null}
                isSelected={c.id === selectedId}
                now={now}
                onSelect={() => {
                  if (c.id === selectedId) return;
                  leave(() => router.push(`/conversation/${c.id}`));
                }}
              />
            ))}
          </List>
        )}
      </StackItem>

      <Text as="p" type="supporting" color="secondary" style={{ padding: "var(--spacing-4)" }}>
        {t.disclaimer}
      </Text>
    </VStack>
  );
}

function Row({
  character,
  preview,
  call,
  isSelected,
  now,
  onSelect,
}: {
  character: Character;
  preview: Preview | null;
  call: CallInList;
  isSelected: boolean;
  now: Date;
  onSelect: () => void;
}) {
  const time = useCallTime(call?.state);
  const description = call
    ? time
      ? copy.call.listConnected(showTime(time))
      : copy.call.dialing
    : !preview
      ? t.neverTalked
      : preview.from === "you"
        ? t.you(preview.text)
        : preview.from === "her"
          ? preview.text
          : t.nothingSaidYet;
  return (
    <ListItem
      label={character.name}
      description={description}
      isSelected={isSelected}
      onClick={onSelect}
      style={listRow(character.color, isSelected)}
      startContent={
        <Avatar
          src={character.avatar_url ?? undefined}
          name={character.name}
          size="lg"
          tooltip={false}
          style={{ boxShadow: "0 0 0 var(--spacing-0-5) var(--her-mark)" }}
        />
      }
      endContent={
        preview && !call ? (
          <Text type="supporting" color="secondary" hasTabularNumbers>
            {listTime(new Date(preview.at), now)}
          </Text>
        ) : undefined
      }
    />
  );
}

/** 列表里的时间：今天写时刻（和气泡下的时间一样写成 8:49），昨天写「昨天」，今年写月日，更早写年月日。 */
function listTime(at: Date, now: Date): string {
  const two = (n: number) => String(n).padStart(2, "0");
  switch (dayOf(at, now)) {
    case "today":
      return `${at.getHours()}:${two(at.getMinutes())}`;
    case "yesterday":
      return t.yesterday;
    case "thisYear":
      return t.monthDay(String(at.getMonth() + 1), String(at.getDate()));
    case "earlier":
      return t.fullDate(String(at.getFullYear()), String(at.getMonth() + 1), String(at.getDate()));
  }
}

/** 现在的时间，每分钟更新一次，过了午夜「今天」「昨天」会跟着变。 */
function useMinute(): Date {
  const [now, setNow] = useState(() => new Date());
  useEffect(() => {
    const timer = setInterval(() => setNow(new Date()), 60_000);
    return () => clearInterval(timer);
  }, []);
  return now;
}

function Loading() {
  return (
    <VStack gap={4} padding={4} aria-label={t.loading} aria-busy>
      {[0, 1].map((i) => (
        <HStack key={i} gap={3} vAlign="center">
          <Skeleton width="var(--spacing-12)" height="var(--spacing-12)" radius="rounded" index={i} />
          <StackItem size="fill">
            <VStack gap={2}>
              <Skeleton width="40%" height="var(--spacing-4)" index={i} />
              <Skeleton width="70%" height="var(--spacing-3)" index={i} />
            </VStack>
          </StackItem>
        </HStack>
      ))}
    </VStack>
  );
}
