"use client";

import { useEffect, useState } from "react";

import { FailureNotice } from "@/components/app/FailureNotice";
import { PageShell } from "@/components/app/PageShell";
import { SectionHeading } from "@/components/app/SubpageHeader";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { copy } from "@/i18n";
import { toFailure, type Failure } from "@/lib/failure";
import { drawNote, emptyNote, getGiftState, type GiftState } from "@/lib/gifts";
import { cn } from "@/lib/utils";
import { DrawIcon, GiftIcon } from "@/theme/icons";

const t = copy.gifts;

/**
 * 礼物页（DESIGN.md「礼物页」）：导航栏右边整块一栏，内容最宽 `max-w-3xl`、居中，手机和电脑同一个版式。
 * 上面是抽奖台，下面「我的礼物」。好感度和礼物没开放时整页是「礼物暂时没有开放」，「礼物」照样留在导航里。
 */
export function GiftsPage() {
  const [state, setState] = useState<GiftState | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);

  useEffect(() => {
    getGiftState().then(setState, (e) => setFailure(toFailure(e)));
  }, []);

  return (
    <PageShell width="full" isInShell header={<h1 className="text-list-title">{t.title}</h1>}>
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 py-6">
        {failure && <FailureNotice failure={failure} />}
        {state === null ? (
          !failure && <p className="text-body text-muted-foreground">{t.loading}</p>
        ) : !state.open ? (
          <Closed />
        ) : (
          <>
            <DrawDesk draws={state.draws} max={state.max_draws} />
            <SectionHeading>{t.mine}</SectionHeading>
            <Empty>
              <EmptyHeader>
                <EmptyMedia variant="icon">
                  <GiftIcon />
                </EmptyMedia>
                <EmptyTitle>{t.empty.title}</EmptyTitle>
                <EmptyDescription>{emptyNote(state.draws)}</EmptyDescription>
              </EmptyHeader>
            </Empty>
          </>
        )}
      </div>
    </PageShell>
  );
}

/**
 * 抽奖台：`bg-muted` 圆角块，「抽奖 还有 n 次」、7 个小点（攒了几次亮几个）和一句说明；右边「抽一次」，
 * 攒了 2 次以上时旁边多一个「全部抽完」，次数为 0 时「抽一次」不可用。
 */
function DrawDesk({ draws, max }: { draws: number; max: number }) {
  return (
    <section aria-label={t.draw.title} className="flex flex-wrap items-center gap-4 rounded-2xl bg-muted p-5">
      <div className="flex min-w-0 flex-1 flex-col gap-2">
        <p className="flex items-baseline gap-2">
          <span className="text-header">{t.draw.title}</span>
          <span className="text-sm text-muted-foreground tabular-nums">{t.draw.left(draws)}</span>
        </p>
        <span role="img" aria-label={t.draw.label(draws, max)} className="flex gap-1">
          {Array.from({ length: max }, (_, i) => (
            <span key={i} className={cn("size-2 rounded-full", i < draws ? "bg-foreground" : "bg-foreground/15")} />
          ))}
        </span>
        <p className="text-subtitle text-muted-foreground">{drawNote(draws, max)}</p>
      </div>
      {/* 抽奖由下一张票接上，这里先占位。 */}
      <div className="flex gap-2">
        {draws >= 2 && <Button variant="outline">{t.draw.all}</Button>}
        <Button disabled={draws === 0}>
          <DrawIcon data-icon="inline-start" />
          {t.draw.once}
        </Button>
      </div>
    </section>
  );
}

/** 没开放：整页一个 `Empty`。 */
function Closed() {
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <GiftIcon />
        </EmptyMedia>
        <EmptyTitle>{t.closed.title}</EmptyTitle>
        <EmptyDescription>{t.closed.description}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}
