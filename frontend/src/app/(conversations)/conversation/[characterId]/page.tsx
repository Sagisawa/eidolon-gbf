"use client";

import { Button } from "@astryxdesign/core/Button";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Spinner } from "@astryxdesign/core/Spinner";
import { VStack } from "@astryxdesign/core/VStack";
import { useParams, useRouter } from "next/navigation";

import { useDirectory, useWide } from "@/components/conversations/ConversationDirectory";
import { ConversationView } from "@/components/conversations/ConversationView";
import { copy } from "@/i18n";

/** 和一位角色的对话。宽屏时在双栏外壳的右栏，窄屏时占满一页、页首带返回键。 */
export default function ConversationPage() {
  const { characterId } = useParams<{ characterId: string }>();
  const router = useRouter();
  const wide = useWide();
  const { characters, failure } = useDirectory();
  const character = characters?.find((c) => c.id === characterId);
  const back = () => router.push("/");

  if (character) {
    // 换角色时整页重来：上一位的对话（和通话）就此结束。
    return <ConversationView key={character.id} character={character} onBack={wide ? undefined : back} />;
  }
  return (
    <VStack height="100%" hAlign="center" vAlign="center" padding={6}>
      {characters === null && !failure ? (
        <Spinner size="lg" aria-label={copy.conversation.loading} />
      ) : (
        <EmptyState
          title={failure ? copy.conversation.loadFailed : copy.conversation.notFound}
          description={failure?.message}
          actions={<Button label={copy.conversation.backToList} variant="secondary" onClick={back} />}
        />
      )}
    </VStack>
  );
}
