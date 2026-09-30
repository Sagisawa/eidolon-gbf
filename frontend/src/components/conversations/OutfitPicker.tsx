"use client";

import { BottomSheet } from "@astryxdesign/core/BottomSheet";
import { Button } from "@astryxdesign/core/Button";
import { Card } from "@astryxdesign/core/Card";
import { Dialog, DialogHeader } from "@astryxdesign/core/Dialog";
import { EmptyState } from "@astryxdesign/core/EmptyState";
import { Grid } from "@astryxdesign/core/Grid";
import { Heading } from "@astryxdesign/core/Heading";
import { HStack } from "@astryxdesign/core/HStack";
import { Layout, LayoutContent } from "@astryxdesign/core/Layout";
import { SegmentedControl, SegmentedControlItem } from "@astryxdesign/core/SegmentedControl";
import { Spinner } from "@astryxdesign/core/Spinner";
import { StackItem } from "@astryxdesign/core/Stack";
import { Text } from "@astryxdesign/core/Text";
import { VStack } from "@astryxdesign/core/VStack";
import { useState, type CSSProperties } from "react";

import { copy } from "@/i18n";
import type { Outfit } from "@/lib/api";
import { CALM } from "@/lib/standAnimations";
import { findOutfit, LOOKS, type ListedOutfit, type Look, type OutfitCard } from "@/lib/standOutfit";
import { listRow } from "@/theme/herVars";
import { Ja } from "@/theme/Ja";

import { Stand } from "./stand/Stand";
import type { StandOutfits } from "./useStandOutfits";

const t = copy.conversation.outfits;

type Props = {
  isOpen: boolean;
  onOpenChange: (isOpen: boolean) => void;
  /** 宽屏打开弹窗，窄屏打开底部面板（和对话页同一个断点）。 */
  isWide: boolean;
  isReducedMotion: boolean;
  /** 她的印象色：选中（正在预览）的卡铺她的 paper。 */
  color: string;
  outfits: StandOutfits;
};

/**
 * 换衣装（spec「衣装与换衣装」）：宽屏是弹窗，左边是大预览；窄屏是底部面板，大预览在上面，随列表一起滚动。
 * 列表按衣装清单的顺序排卡片，每张卡有缩略图、卡名和「私服 / 演出」切换。点卡片只是预览，
 * 点「穿这套」才记在这台设备上，下次打电话她就穿这套。
 */
export function OutfitPicker({ isOpen, onOpenChange, isWide, isReducedMotion, color, outfits }: Props) {
  const { cards, worn } = outfits;
  // 还没点过卡片时预览她正在穿的那套；关上时忘掉点过的，下次打开又从正在穿的看起。
  const [pickedId, setPickedId] = useState<string | null>(null);
  const picked = pickedId ?? worn.id;
  // 大预览最近试的那套载入了没有：画面上是不是这一套，由它判断。
  const [tried, setTried] = useState<{ url: string; isLoaded: boolean } | null>(null);
  const openChange = (open: boolean) => {
    if (!open) {
      setPickedId(null);
      setTried(null);
    }
    onOpenChange(open);
  };

  const found = findOutfit(cards ?? [], picked);
  // 清单里找不到（例如清单没读到时正在穿的那套）也照样预览。
  const previewed: Outfit = found?.outfit ?? worn;
  const isWorn = previewed.id === worn.id;
  // 预览没画出这一套（还在载入，或者载入不到）时不能穿：看到的得是要穿的那套。
  const isShown = tried?.url === previewed.url && tried.isLoaded;
  const isBroken = tried?.url === previewed.url && !tried.isLoaded;
  const wear = () => {
    outfits.wear(previewed.id);
    openChange(false);
  };

  const preview = (
    <VStack gap={3} hAlign="center" width="100%">
      <VStack width="100%" style={{ ...stage, height: isWide ? previewHeightWide : previewHeightNarrow }}>
        {/* 关上时卸下，引擎和素材一起释放 */}
        {isOpen && (
          <Stand
            outfits={[previewed]}
            framing="full"
            isPaused={false}
            entrance="fade"
            direction={CALM}
            isReducedMotion={isReducedMotion}
            onTried={(outfit, isLoaded) => setTried({ url: outfit.url, isLoaded })}
          />
        )}
      </VStack>
      <VStack gap={1} hAlign="center">
        <Ja>
          <Text weight="medium" justify="center">
            {found && t.cardName(found.card.name)}
          </Text>
        </Ja>
        <Text type="supporting" color="secondary" justify="center">
          {[found && t.lookNames[found.look], found?.card.type, isWorn && t.wearing, isBroken && t.notLoaded]
            .filter(Boolean)
            .join(t.separator)}
        </Text>
      </VStack>
      <Button label={t.wear} variant="primary" onClick={wear} isDisabled={isWorn || !isShown} />
    </VStack>
  );

  const list =
    cards === null ? (
      <VStack hAlign="center" padding={6}>
        <Spinner size="lg" aria-label={t.loading} />
      </VStack>
    ) : outfits.isListFailed ? (
      <EmptyState
        title={t.loadFailed}
        actions={<Button label={t.retry} variant="secondary" onClick={outfits.reloadList} />}
      />
    ) : (
      <Grid columns={isWide ? { minWidth: 128 } : 3} gap={3}>
        {cards.map((card) => (
          <CardTile key={card.id} card={card} picked={picked} color={color} onPick={setPickedId} />
        ))}
      </Grid>
    );

  if (isWide) {
    return (
      <Dialog isOpen={isOpen} onOpenChange={openChange} width={960} maxHeight="86dvh">
        <Layout
          header={<DialogHeader title={t.title} subtitle={t.hint} onOpenChange={openChange} />}
          content={
            <LayoutContent>
              <HStack gap={6} vAlign="start">
                <VStack width={300} style={{ flexShrink: 0, position: "sticky", top: 0 }}>
                  {preview}
                </VStack>
                <StackItem size="fill" style={{ minWidth: 0 }}>
                  {list}
                </StackItem>
              </HStack>
            </LayoutContent>
          }
        />
      </Dialog>
    );
  }
  return (
    <BottomSheet isOpen={isOpen} onOpenChange={openChange} label={t.title} height="tall">
      <VStack gap={4} padding={4}>
        <VStack gap={1}>
          <Heading level={2}>{t.title}</Heading>
          <Text type="supporting" color="secondary">
            {t.hint}
          </Text>
        </VStack>
        {preview}
        {list}
      </VStack>
    </BottomSheet>
  );
}

/**
 * 一张卡：缩略图、卡名（固定占两行，超出截断，悬停时显示全名）和「私服 / 演出」切换，
 * 只有一套的卡是灰掉的「只有一套」，所有卡片一样高。切换和点缩略图都会预览这一套。
 */
function CardTile({
  card,
  picked,
  color,
  onPick,
}: {
  card: OutfitCard;
  picked: string;
  color: string;
  onPick: (id: string) => void;
}) {
  const looks = LOOKS.filter((look) => card[look]);
  const pickedLook = looks.find((look) => card[look]?.id === picked);
  const [chosen, setChosen] = useState<Look>(looks[0]);
  // 这张卡上的某一套被选中时（例如打开时正在穿的是演出服），切换跟着它。
  const look = pickedLook ?? chosen;
  const outfit = card[look] as ListedOutfit;
  const isPicked = pickedLook !== undefined;
  return (
    <Card padding={1} style={listRow(color, isPicked)}>
      <VStack gap={1} height="100%">
        <VStack
          as="button"
          aria-label={t.preview(card.name)}
          aria-pressed={isPicked}
          onClick={() => onPick(outfit.id)}
          style={thumbnailButton}
        >
          {/* 缩略图同步素材时预先渲染好（400×500），滚到了才下载 */}
          <img src={outfit.thumbnail} alt="" loading="lazy" decoding="async" style={thumbnail} />
        </VStack>
        <StackItem size="fill">
          <Ja>
            <Text type="supporting" maxLines={2} style={twoLines}>
              {card.name}
            </Text>
          </Ja>
        </StackItem>
        {looks.length > 1 ? (
          <SegmentedControl
            label={t.lookLabel(card.name)}
            size="sm"
            layout="fill"
            value={look}
            onChange={(value) => {
              const next = value as Look;
              setChosen(next);
              onPick((card[next] as ListedOutfit).id);
            }}
          >
            {LOOKS.map((value) => (
              <SegmentedControlItem key={value} value={value} label={t.looks[value]} />
            ))}
          </SegmentedControl>
        ) : (
          <SegmentedControl label={t.lookLabel(card.name)} size="sm" layout="fill" value="only" onChange={() => {}} isDisabled>
            <SegmentedControlItem value="only" label={t.only} />
          </SegmentedControl>
        )}
      </VStack>
    </Card>
  );
}

/** 大预览的底：她的 paper，立绘画在上面。 */
const stage: CSSProperties = { borderRadius: "var(--radius-container)", background: "var(--her-paper)", overflow: "hidden" };
const previewHeightWide = "calc(var(--spacing-12) * 8)";
const previewHeightNarrow = "calc(var(--spacing-12) * 4.5)";

/** 缩略图是一个按钮，去掉按钮自带的样式，透出卡片的底。 */
const thumbnailButton: CSSProperties = {
  border: 0,
  padding: 0,
  cursor: "pointer",
  overflow: "hidden",
  borderRadius: "var(--radius-inner)",
  background: "transparent",
};

/** 缩略图 4:5，铺满卡片宽度；还没下载到时也占着同样的位置。 */
const thumbnail: CSSProperties = { display: "block", width: "100%", aspectRatio: "4 / 5", objectFit: "cover" };

/** 卡名固定占两行高，所有卡片一样高。 */
const twoLines: CSSProperties = { height: "calc(var(--text-supporting-size) * var(--text-supporting-leading) * 2)" };
