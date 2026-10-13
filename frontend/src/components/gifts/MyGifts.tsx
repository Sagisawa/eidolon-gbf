"use client";

import { useState } from "react";

import { SectionHeading } from "@/components/app/SubpageHeader";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { copy } from "@/i18n";
import { GIFT_FILTERS, shownGifts, type GiftFilter, type GiftInfo, type Held, type Owned } from "@/lib/gifts";
import { DrinkIcon, FlowerIcon, FoodIcon, TrinketIcon } from "@/theme/icons";

const t = copy.gifts;

const FILTER_ICONS = { food: FoodIcon, drink: DrinkIcon, flower: FlowerIcon, trinket: TrinketIcon };

/**
 * 我的礼物（DESIGN.md「礼物页」）：标题右边是类别筛选（`ToggleGroup`），下面是插画网格（手机 3 列，更宽 4、5 列）。
 * 网格里不透露哪位角色喜欢什么。背包是空的时候由页面放「还没有礼物」，这里不出。
 */
export function MyGifts({ backpack, catalog }: { backpack: Owned[]; catalog: GiftInfo[] }) {
  const [filter, setFilter] = useState<GiftFilter>("all");
  const held = shownGifts(backpack, catalog, filter);
  return (
    <section aria-labelledby="my-gifts" className="flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <SectionHeading id="my-gifts">{t.mine}</SectionHeading>
        <ToggleGroup
          aria-label={t.filters.label}
          size="sm"
          spacing={0}
          value={[filter]}
          onValueChange={(value: unknown[]) => {
            const next = value[0] as GiftFilter | undefined;
            if (next) setFilter(next);
          }}
        >
          {GIFT_FILTERS.map((f) => {
            const Icon = f === "all" ? null : FILTER_ICONS[f];
            return (
              <ToggleGroupItem key={f} value={f}>
                {Icon && <Icon data-icon="inline-start" />}
                {t.filters[f]}
              </ToggleGroupItem>
            );
          })}
        </ToggleGroup>
      </div>
      {held.length === 0 ? (
        <p className="py-8 text-center text-body text-muted-foreground">{t.noneOfKind}</p>
      ) : (
        <ul className="grid grid-cols-3 gap-3 sm:grid-cols-4 md:grid-cols-5">
          {held.map((h) => (
            <HeldGift key={h.gift.id} held={h} />
          ))}
        </ul>
      )}
    </section>
  );
}

/** 网格里的一格：插画方块（多于 1 件时右下角「×n」）、礼物名、稀有度。读屏读名字、件数和稀有度。 */
function HeldGift({ held: { gift, count } }: { held: Held }) {
  const rarity = t.rarity[gift.rarity];
  return (
    <li className="flex flex-col gap-1">
      <span className="sr-only">{t.held(gift.name, count, rarity)}</span>
      <div aria-hidden className="relative aspect-square rounded-2xl bg-muted">
        <img src={`/gifts/${gift.id}.webp`} alt="" loading="lazy" decoding="async" className="size-full object-contain p-2" />
        {count > 1 && (
          <span className="absolute right-2 bottom-1.5 text-meta font-medium tabular-nums">{t.count(count)}</span>
        )}
      </div>
      <p aria-hidden className="truncate text-sm">
        {gift.name}
      </p>
      <p aria-hidden className="text-meta text-muted-foreground">
        {rarity}
      </p>
    </li>
  );
}
