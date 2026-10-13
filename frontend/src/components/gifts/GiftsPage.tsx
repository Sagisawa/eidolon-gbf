"use client";

import { useEffect, useMemo, useState } from "react";

import { FailureNotice } from "@/components/app/FailureNotice";
import { PageShell } from "@/components/app/PageShell";
import { SectionHeading } from "@/components/app/SubpageHeader";
import { DrawDialog, type Drawing } from "@/components/gifts/DrawDialog";
import { MyGifts } from "@/components/gifts/MyGifts";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { copy } from "@/i18n";
import { ApiError } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { drawGifts, drawNote, emptyNote, getGiftCatalog, getGiftState, type GiftInfo, type GiftState } from "@/lib/gifts";
import { cn } from "@/lib/utils";
import { DrawIcon, GiftIcon } from "@/theme/icons";

const t = copy.gifts;

/** 礼物盒揭晓前跳多久，和 `animate-hop` 一样长。 */
const OPENING_MS = 900;

/**
 * 礼物页（DESIGN.md「礼物页」）：导航栏右边整块一栏，内容最宽 `max-w-3xl`、居中，手机和电脑同一个版式。
 * 上面是抽奖台，下面「我的礼物」。好感度和礼物没开放时整页是「礼物暂时没有开放」，「礼物」照样留在导航里；
 * 抽奖时才知道没开放（收到「没开放」的 409）也切成这样。
 */
export function GiftsPage() {
  const [state, setState] = useState<GiftState | null>(null);
  const [catalog, setCatalog] = useState<GiftInfo[] | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [drawing, setDrawing] = useState<Drawing | null>(null);
  const isReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)", false);
  const giftsById = useMemo(() => new Map((catalog ?? []).map((g) => [g.id, g])), [catalog]);

  useEffect(() => {
    Promise.all([getGiftState(), getGiftCatalog()]).then(
      ([s, c]) => {
        setState(s);
        setCatalog(c);
      },
      (e) => setFailure(toFailure(e)),
    );
  }, []);

  async function draw(all: boolean) {
    setFailure(null);
    setDrawing({ all, result: null });
    try {
      const [result] = await Promise.all([
        drawGifts(all),
        new Promise((resolve) => setTimeout(resolve, isReducedMotion ? 0 : OPENING_MS)),
      ]);
      setDrawing({ all, result });
      setState((s) => s && { ...s, draws: result.draws });
      getGiftState().then(setState, (e) => setFailure(toFailure(e)));
    } catch (e) {
      setDrawing(null);
      if (e instanceof ApiError && e.giftsClosed) setState((s) => s && { ...s, open: false });
      else setFailure(toFailure(e));
    }
  }

  return (
    <PageShell width="full" isInShell header={<h1 className="text-list-title">{t.title}</h1>}>
      <div className="mx-auto flex w-full max-w-3xl flex-1 flex-col gap-4 px-4 py-6">
        {failure && <FailureNotice failure={failure} />}
        {state === null || catalog === null ? (
          !failure && <p className="text-body text-muted-foreground">{t.loading}</p>
        ) : !state.open ? (
          <GiftsEmpty title={t.closed.title} description={t.closed.description} />
        ) : (
          <>
            <DrawDesk draws={state.draws} max={state.max_draws} isDrawing={drawing !== null} onDraw={draw} />
            {state.backpack.length > 0 ? (
              <MyGifts backpack={state.backpack} catalog={catalog} />
            ) : (
              <>
                <SectionHeading>{t.mine}</SectionHeading>
                <GiftsEmpty title={t.empty.title} description={emptyNote(state.draws)} />
              </>
            )}
          </>
        )}
      </div>
      <DrawDialog drawing={drawing} catalog={giftsById} onAgain={() => draw(false)} onClose={() => setDrawing(null)} />
    </PageShell>
  );
}

/**
 * 抽奖台：`bg-muted` 圆角块，「抽奖 还有 n 次」、7 个小点（攒了几次亮几个）和一句说明；右边「抽一次」，
 * 攒了 2 次以上时旁边多一个「全部抽完」，次数为 0 时「抽一次」不可用。
 */
function DrawDesk({
  draws,
  max,
  isDrawing,
  onDraw,
}: {
  draws: number;
  max: number;
  isDrawing: boolean;
  onDraw: (all: boolean) => void;
}) {
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
      <div className="flex gap-2">
        {draws >= 2 && (
          <Button variant="outline" disabled={isDrawing} onClick={() => onDraw(true)}>
            {t.draw.all}
          </Button>
        )}
        <Button disabled={draws === 0 || isDrawing} onClick={() => onDraw(false)}>
          <DrawIcon data-icon="inline-start" />
          {t.draw.once}
        </Button>
      </div>
    </section>
  );
}

/** 礼物图标加一句标题和说明的 `Empty`：「还没有礼物」，以及没开放时的整页。 */
function GiftsEmpty({ title, description }: { title: string; description: string }) {
  return (
    <Empty>
      <EmptyHeader>
        <EmptyMedia variant="icon">
          <GiftIcon />
        </EmptyMedia>
        <EmptyTitle>{title}</EmptyTitle>
        <EmptyDescription>{description}</EmptyDescription>
      </EmptyHeader>
    </Empty>
  );
}
