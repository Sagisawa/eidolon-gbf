"use client";

import { usePathname } from "next/navigation";
import { useSyncExternalStore, type ReactNode } from "react";

import { CallBar } from "@/components/conversations/CallBar";
import { LiveCallLayer } from "@/components/conversations/CallLayer";
import { useDirectory, useWide } from "@/components/conversations/ConversationDirectory";
import { useFocusBack } from "@/components/conversations/useFocusBack";
import { useStandOutfits } from "@/components/conversations/useStandOutfits";
import type { Character } from "@/lib/api";
import { NOT_OPEN, type LiveConversation } from "@/lib/liveConversation";
import { showsShellCallBar } from "@/lib/navShell";
import { settingsHref } from "@/lib/settingsTab";
import { herVars } from "@/theme/herVars";

const notOpen = () => NOT_OPEN;
const noSubscription = () => () => {};

/**
 * 导航外壳的页框（DESIGN.md「Call layer」，ADR-0018）：通话由外壳持有，不在她的对话页上时由这里画。
 * - 通话中、通话层收着、当前页不是她的对话页（外壳的去处规则，lib/navShell）：最顶上一条带她名字的通话条，
 *   横跨整宽、在页首之上；点了在当前页展开通话层。她的对话页上没有这一条，那里页首下面有自己的。
 * - 通话层在当前页展开：手机上铺满整屏，电脑上盖住内容区；展开时底下的页面都 inert。收起后还在原来的页面。
 * 下面的页面占满通话条以外的那一块（PageShell 的 `isInShell`）。
 */
export function NavShell({ children }: { children: ReactNode }) {
  const pathname = usePathname();
  const { held, isHeldShown, call, characters } = useDirectory();
  const snapshot = useSyncExternalStore(held?.subscribe ?? noSubscription, held?.snapshot ?? notOpen, notOpen);
  const character = held && !isHeldShown ? characters?.find((c) => c.id === held.characterId) : undefined;
  const layer = character ? snapshot.layer : null;
  const isCovered = layer !== null && !layer.collapsed;
  const barShown = call !== null && layer?.collapsed === true && showsShellCallBar(pathname, call.characterId);
  const focus = useFocusBack({ layerOpen: isCovered, noteShown: barShown });

  return (
    <div className="flex h-dvh flex-col">
      {barShown && character && held && (
        <div style={herVars(character.color)} className="shrink-0">
          <CallBar ref={focus.note} call={call.state} name={character.name} onExpand={() => held.expand()} />
        </div>
      )}
      <div className="relative min-h-0 flex-1">
        <div inert={isCovered} className="h-full">
          {children}
        </div>
        {character && held && <HeldLayer live={held} character={character} layerRef={focus.layer} />}
      </div>
    </div>
  );
}

/** 当前页上的通话层：注入她的颜色，盖住内容区（手机上铺满整屏）。 */
function HeldLayer({
  live,
  character,
  layerRef,
}: {
  live: LiveConversation;
  character: Character;
  layerRef: ReturnType<typeof useFocusBack>["layer"];
}) {
  const { go } = useDirectory();
  const outfits = useStandOutfits(character);
  const isFullScreen = !useWide();
  return (
    <div style={herVars(character.color)} className="contents">
      <LiveCallLayer
        live={live}
        character={character}
        standOutfits={outfits?.toTry ?? []}
        layerRef={layerRef}
        isFullScreen={isFullScreen}
        onOwnKeys={() => go(settingsHref("own-keys"))}
      />
    </div>
  );
}
