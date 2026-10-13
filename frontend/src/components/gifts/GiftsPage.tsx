"use client";

import { useEffect, useMemo, useState } from "react";

import { FailureNotice } from "@/components/app/FailureNotice";
import { PageShell } from "@/components/app/PageShell";
import { SectionHeading } from "@/components/app/SubpageHeader";
import { useDirectory, useWide } from "@/components/conversations/ConversationDirectory";
import { useProducerTimezone } from "@/components/conversations/useProducerTimezone";
import { DrawDialog, type Drawing } from "@/components/gifts/DrawDialog";
import { GivenToast, type GivenNotice } from "@/components/gifts/GivenToast";
import { GivePanel, type Giving } from "@/components/gifts/GivePanel";
import { MyGifts } from "@/components/gifts/MyGifts";
import { Button } from "@/components/ui/button";
import { Empty, EmptyDescription, EmptyHeader, EmptyMedia, EmptyTitle } from "@/components/ui/empty";
import { useMediaQuery } from "@/hooks/useMediaQuery";
import { copy } from "@/i18n";
import { ApiError } from "@/lib/api";
import { arrange } from "@/lib/conversationList";
import { toFailure, type Failure } from "@/lib/failure";
import {
  drawGifts,
  drawNote,
  emptyNote,
  getGiftCatalog,
  getGiftState,
  giveGift,
  givenNote,
  type DrawResult,
  type GiftInfo,
  type GiftState,
  type Given,
} from "@/lib/gifts";
import { cn } from "@/lib/utils";
import { DrawIcon, GiftIcon } from "@/theme/icons";

const t = copy.gifts;

/** 礼物盒揭晓前跳多久，和 `animate-hop` 一样长。 */
const OPENING_MS = 900;

/** 送出后的提示留多久。 */
const NOTICE_MS = 8000;

/**
 * 礼物页（DESIGN.md「礼物页」）：导航栏右边整块一栏，内容最宽 `max-w-3xl`、居中，手机和电脑同一个版式。
 * 上面是抽奖台，下面「我的礼物」；点一件（或单抽结果上的「送给谁…」）拉出送礼面板，送出后面板收起、底部出提示，
 * 页面不跳走。好感度和礼物没开放时整页是「礼物暂时没有开放」，「礼物」照样留在导航里；
 * 抽奖或送礼时才知道没开放（收到「没开放」的 409）也切成这样。
 */
export function GiftsPage() {
  const [state, setState] = useState<GiftState | null>(null);
  const [catalog, setCatalog] = useState<GiftInfo[] | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const [drawing, setDrawing] = useState<Drawing | null>(null);
  // 收起面板时留着上一次送的，收起的动画里内容不消失。
  const [giving, setGiving] = useState<Giving | null>(null);
  const [isGiveOpen, setGiveOpen] = useState(false);
  const [isSending, setSending] = useState(false);
  const [notice, setNotice] = useState<GivenNotice | null>(null);
  const isReducedMotion = useMediaQuery("(prefers-reduced-motion: reduce)", false);
  const isWide = useWide();
  const timeZone = useProducerTimezone();
  const { characters, latest, preferences, go, refresh } = useDirectory();
  const giftsById = useMemo(() => new Map((catalog ?? []).map((g) => [g.id, g])), [catalog]);
  // 送给谁：所有角色（隐藏了的也在），顺序和对话列表一样。
  const recipients = useMemo(() => {
    const all = characters ?? [];
    return arrange(all, latest, { preferences, keep: all.map((c) => c.id) }).rows.map((row) => row.character);
  }, [characters, latest, preferences]);
  const statuses = useMemo(() => new Map((state?.characters ?? []).map((c) => [c.id, c])), [state]);

  useEffect(() => {
    if (!notice) return;
    const timer = setTimeout(() => setNotice(null), NOTICE_MS);
    return () => clearTimeout(timer);
  }, [notice]);

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
      // 先按抽到的把背包补上，「送给谁…」马上打开时件数就是对的；随后再整个读一遍。
      setState((s) => s && withDrawn(s, result, catalog ?? []));
      getGiftState().then(setState, (e) => setFailure(toFailure(e)));
    } catch (e) {
      setDrawing(null);
      failed(e);
    }
  }

  /** 收到「没开放」的 409 时整页切成未开放，别的失败在页上方说。 */
  function failed(e: unknown) {
    if (e instanceof ApiError && e.giftsClosed) setState((s) => s && { ...s, open: false });
    else setFailure(toFailure(e));
  }

  /** 拉出这件的送礼面板；还有几件按背包里的算。 */
  function startGiving(gift: GiftInfo) {
    const left = state?.backpack.find((b) => b.gift_id === gift.id)?.count ?? 0;
    setDrawing(null);
    setGiving({ gift, left, to: null });
    setGiveOpen(true);
  }

  async function send() {
    const to = recipients.find((c) => c.id === giving?.to);
    if (!giving || !to) return;
    setFailure(null);
    setSending(true);
    try {
      const given = await giveGift(to.id, giving.gift.id, null);
      setGiveOpen(false);
      setState((s) => s && afterGiving(s, giving.gift.id, to.id, given));
      setNotice({
        key: Date.now(),
        character: to,
        note: givenNote(given, to.name, new Date(), timeZone),
      });
      refresh();
    } catch (e) {
      setGiveOpen(false);
      failed(e);
      // 另一个标签页可能刚送掉了最后一件：重新读一遍背包。
      getGiftState().then(setState, () => {});
    } finally {
      setSending(false);
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
              <MyGifts backpack={state.backpack} catalog={catalog} onGive={(held) => startGiving(held.gift)} />
            ) : (
              <>
                <SectionHeading>{t.mine}</SectionHeading>
                <GiftsEmpty title={t.empty.title} description={emptyNote(state.draws)} />
              </>
            )}
          </>
        )}
      </div>
      <DrawDialog
        drawing={drawing}
        catalog={giftsById}
        onGive={startGiving}
        onAgain={() => draw(false)}
        onClose={() => setDrawing(null)}
      />
      <GivePanel
        giving={giving}
        isOpen={isGiveOpen}
        isWide={isWide}
        isSending={isSending}
        characters={recipients}
        statuses={statuses}
        onChoose={(to) => setGiving((g) => g && { ...g, to })}
        onSend={send}
        onClose={() => setGiveOpen(false)}
      />
      {/* 「去对话」去她的对话页，那里打开的就是记录放进的那段；通话中去别的角色时先问会不会挂断。 */}
      <GivenToast notice={notice} onGo={(n) => go(`/conversation/${encodeURIComponent(n.character.id)}`)} />
    </PageShell>
  );
}

/** 抽完以后的礼物状态：剩下的次数，抽到的礼物叠进背包（按目录的顺序），重置卡另计。 */
function withDrawn(state: GiftState, result: DrawResult, catalog: GiftInfo[]): GiftState {
  const counts = new Map(state.backpack.map((b) => [b.gift_id, b.count]));
  let cards = state.reset_cards;
  for (const d of result.drawn) {
    if (d.kind === "gift") counts.set(d.gift_id, (counts.get(d.gift_id) ?? 0) + 1);
    else cards += 1;
  }
  const backpack = catalog.flatMap((g) => {
    const count = counts.get(g.id);
    return count ? [{ gift_id: g.id, count }] : [];
  });
  return { ...state, draws: result.draws, backpack, reset_cards: cards };
}

/** 送出一件以后的礼物状态：这件按接口给的件数（送完的不再列），她的好感度换成现在的。 */
function afterGiving(state: GiftState, giftId: string, characterId: string, given: Given): GiftState {
  return {
    ...state,
    backpack: state.backpack
      .map((b) => (b.gift_id === giftId ? { ...b, count: given.left } : b))
      .filter((b) => b.count > 0),
    characters: state.characters.map((c) => (c.id === characterId ? { id: c.id, ...given.affinity } : c)),
  };
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
