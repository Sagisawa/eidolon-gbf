"use client";

import { AlertDialog } from "@astryxdesign/core/AlertDialog";
import { Button } from "@astryxdesign/core/Button";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { IconButton } from "@astryxdesign/core/IconButton";
import { HStack } from "@astryxdesign/core/HStack";
import { List, ListItem } from "@astryxdesign/core/List";
import { Text } from "@astryxdesign/core/Text";
import { Token } from "@astryxdesign/core/Token";
import { VStack } from "@astryxdesign/core/VStack";
import { useEffect, useRef, useState } from "react";

import { FailureNotice } from "@/components/FailureNotice";
import { MarkedAvatar } from "@/components/MarkedAvatar";
import { PageShell } from "@/components/PageShell";
import { SubpageHeader } from "@/components/SubpageHeader";
import { copy } from "@/i18n";
import {
  ApiError,
  clearMemories,
  deleteMemory,
  listCharacters,
  listMemories,
  type Character,
  type Memory,
} from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { sourceCharacter, supersededMark } from "@/lib/memories";
import { TrashIcon } from "@/theme/icons";

const t = copy.memories;

/** 所有角色共用的、关于用户的记忆：只能删，不能改。每条都标出来源角色；被取代的原地列出，淡一些并标出来。 */
export default function MemoriesPage() {
  const [memories, setMemories] = useState<Memory[] | null>(null);
  const [characters, setCharacters] = useState<Character[]>([]);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [deleting, setDeleting] = useState<Set<number>>(new Set());
  const [confirmingDelete, setConfirmingDelete] = useState<Memory | null>(null);
  const [confirmingClear, setConfirmingClear] = useState(false);
  const [clearing, setClearing] = useState(false);
  // 只用最后一次重新取到的列表：连着删几条时，先发出的那次晚到，会把后删的又列出来。
  const refetches = useRef(0);

  useEffect(() => {
    listMemories().then(setMemories, (e) => setFailure(toFailure(e)));
    // 只用来给来源角色配头像和她的颜色；取不到时照样列出记忆。
    listCharacters().then(setCharacters, () => {});
  }, []);

  const forget = (id: number) => setMemories((list) => list?.filter((m) => m.id !== id) ?? null);

  async function remove(memory: Memory) {
    const id = memory.id;
    setConfirmingDelete(null);
    setDeleting((ids) => new Set(ids).add(id));
    setFailure(null);
    try {
      await deleteMemory(id);
      forget(id);
      // 删掉的是取代别的记忆的那条时，被它取代的会恢复，重新取一次才看得到；取不到时照旧列着。
      const refetch = ++refetches.current;
      listMemories().then((list) => refetch === refetches.current && setMemories(list), () => {});
    } catch (e) {
      if (e instanceof ApiError && e.status === 404) forget(id); // 已经删掉了
      else setFailure(toFailure(e));
    } finally {
      setDeleting((ids) => {
        const rest = new Set(ids);
        rest.delete(id);
        return rest;
      });
    }
  }

  async function clear() {
    setClearing(true);
    setFailure(null);
    try {
      await clearMemories();
      setMemories([]);
      setConfirmingClear(false);
    } catch (e) {
      setFailure(toFailure(e));
      setConfirmingClear(false);
    } finally {
      setClearing(false);
    }
  }

  const hasMemories = !!memories && memories.length > 0;

  return (
    <PageShell
      contentWidth={640}
      padding={4}
      header={
        <SubpageHeader
          title={t.title}
          backHref="/settings"
          end={
            hasMemories && (
              <Button
                variant="ghost"
                size="sm"
                label={t.clear}
                onClick={() => setConfirmingClear(true)}
                isDisabled={clearing}
              />
            )
          }
        />
      }
    >
      <VStack gap={4} paddingBlock={4}>
        <Text as="p" color="secondary">
          {t.intro}
        </Text>

        {failure && <FailureNotice failure={failure} />}

        {memories === null ? (
          !failure && <Text color="secondary">{t.loading}</Text>
        ) : memories.length === 0 ? (
          <EmptyState title={t.empty} />
        ) : (
          <List hasDividers density="spacious">
            {memories.map((memory) => {
              const source = sourceCharacter(memory, characters);
              const name = memory.source_character_name ?? t.goneCharacter;
              const created = new Date(memory.created_at);
              const mark = supersededMark(memory);
              return (
                <ListItem
                  key={memory.id}
                  startContent={
                    <MarkedAvatar name={name} src={source?.avatar_url} color={source?.color} size="sm" />
                  }
                  label={
                    <Text wordBreak="break-word" color={mark ? "secondary" : undefined}>
                      {memory.text}
                    </Text>
                  }
                  description={
                    <HStack gap={2} align="center" wrap="wrap">
                      {mark && <Token label={mark} size="sm" color="gray" />}
                      <Text type="supporting">
                        {t.toldTo(name)} · {t.date(created.getFullYear(), created.getMonth() + 1, created.getDate())}
                      </Text>
                    </HStack>
                  }
                  endContent={
                    <IconButton
                      variant="ghost"
                      size="sm"
                      icon={<TrashIcon />}
                      label={t.removeLabel(memory.text)}
                      tooltip={t.remove}
                      isLoading={deleting.has(memory.id)}
                      isDisabled={clearing}
                      onClick={() => setConfirmingDelete(memory)}
                    />
                  }
                />
              );
            })}
          </List>
        )}
      </VStack>

      <AlertDialog
        isOpen={confirmingDelete !== null}
        onOpenChange={(open) => !open && setConfirmingDelete(null)}
        title={t.removeTitle}
        description={confirmingDelete ? t.removeDescription(confirmingDelete.text) : ""}
        actionLabel={t.remove}
        cancelLabel={copy.common.cancel}
        onAction={() => confirmingDelete && remove(confirmingDelete)}
      />
      <AlertDialog
        isOpen={confirmingClear}
        onOpenChange={(open) => !clearing && setConfirmingClear(open)}
        title={t.clearTitle}
        description={t.clearDescription(memories?.length ?? 0)}
        actionLabel={t.clearConfirm}
        cancelLabel={copy.common.cancel}
        onAction={clear}
        isActionLoading={clearing}
      />
    </PageShell>
  );
}
