"use client";

import type { RefObject } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { copy } from "@/i18n";
import { badgeOf, TIERS, type AffinityStatus, type Heart } from "@/lib/affinity";
import { cn } from "@/lib/utils";
import { AffinityColdIcon, AffinityDistantIcon, AffinityIcon, CooldownIcon } from "@/theme/icons";

const t = copy.conversation.affinity;

/**
 * 页首的好感度标识（DESIGN.md「Buttons」的好感度标识）：电话键右边、更多菜单左边的 ghost 键，
 * 心形（她的颜色）加档名；冷却中换成 muted 的沙漏加解除时刻。点开是说明，container 指回对话子树。
 * 宽度跟着内容走，手机上高度不小于 44px；挤不下时名字截断，不挤压电话键和更多菜单。
 */
export function AffinityBadge({
  status,
  name,
  timeZone,
  subtree,
}: {
  status: AffinityStatus;
  /** 她的名字，冷却中的读屏名字和说明里用。 */
  name: string;
  /** 制作人的时区：解除时刻按它写成今天或明天。 */
  timeZone: string;
  subtree: RefObject<HTMLDivElement | null>;
}) {
  const badge = badgeOf(status, name, new Date(), timeZone);
  const cooling = badge.kind === "cooldown";
  return (
    <Popover>
      <PopoverTrigger
        render={<Button variant="ghost" size="lg" className="min-w-0 shrink max-md:h-11" aria-label={badge.label} />}
      >
        {cooling ? (
          <CooldownIcon aria-hidden className="size-5 text-muted-foreground" />
        ) : (
          <HeartIcon heart={badge.heart} />
        )}
        <span className={cn("truncate tabular-nums", cooling && "text-muted-foreground")}>{badge.text}</span>
      </PopoverTrigger>
      <PopoverContent container={subtree} align="end">
        <div className="flex flex-col gap-0.5">
          <p className="font-medium">{cooling ? t.cooling(name) : t.title(badge.text)}</p>
          <p className="text-muted-foreground">{cooling ? t.coolingNote(badge.until) : t.notes[badge.tier]}</p>
        </div>
        <ol className="flex gap-1" aria-label={t.tiersLabel}>
          {TIERS.map((tier) => {
            const current = !cooling && tier === badge.tier;
            return (
              <li
                key={tier}
                aria-current={current ? "true" : undefined}
                className={cn(
                  "flex-1 rounded-md py-1 text-center text-meta",
                  current ? "bg-foreground text-background" : "bg-muted text-muted-foreground",
                )}
              >
                {t.tiers[tier]}
              </li>
            );
          })}
        </ol>
        <p className="text-meta text-muted-foreground">{t.rule}</p>
      </PopoverContent>
    </Popover>
  );
}

/** 五档的心形，她的颜色：亲近是空心叠一层只露下半的实心，亲密是实心。 */
function HeartIcon({ heart }: { heart: Heart }) {
  const Icon = heart === "off" ? AffinityColdIcon : heart === "crack" ? AffinityDistantIcon : AffinityIcon;
  return (
    <span aria-hidden className="relative flex">
      <Icon className={cn("size-5 text-her-mark", heart === "filled" && "fill-current")} />
      {heart === "half" && (
        <AffinityIcon className="absolute inset-0 size-5 fill-current text-her-mark [clip-path:inset(50%_0_0_0)]" />
      )}
    </span>
  );
}
