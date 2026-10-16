"use client";

import NextLink from "next/link";
import { useEffect, useState, type ReactNode } from "react";

import { FailureNotice } from "@/components/app/FailureNotice";
import { MarkedAvatar } from "@/components/app/MarkedAvatar";
import { useDirectory } from "@/components/conversations/ConversationDirectory";
import { Heatmap } from "@/components/stats/Heatmap";
import { HourChart } from "@/components/stats/HourChart";
import { Button } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Tabs, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { copy } from "@/i18n";
import { getStats, type Character } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { FIRST_LEVEL } from "@/lib/navShell";
import { mostTalked, portrait, STATS_RANGES, statsSections, type Stats, type StatsRange } from "@/lib/stats";
import { cn } from "@/lib/utils";
import { herVars } from "@/theme/herVars";

const t = copy.settings.stats;

const CONVERSATIONS = FIRST_LEVEL.conversations;

/**
 * 设置「统计」（GLOSSARY.md「统计」，DESIGN.md「统计页」）。上半部分不随时间跨度变，从上到下是一句话画像、
 * 认识天数和连续来访三个数、过去一年的热力图；下半部分顶上是「近 30 天 / 近一年 / 全部」，默认全部，下面是总数、聊得最多、
 * 分时段图和礼物。哪一块没数据就不显示；一个回合、一次送礼都没有时整页只有一句话和去对话列表的按钮。
 * 每次打开都重新读，删掉历史对话后回来就是新的数；换跨度时重新读整份，新的到之前眼前的数留着、变淡，页面不跳不空。
 */
export function StatsSettings() {
  const [range, setRange] = useState<StatsRange>("all");
  const [stats, setStats] = useState<Stats | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const { guard, characters, failure: directoryFailure } = useDirectory();

  useEffect(() => {
    let current = true;
    getStats(range).then(
      (got) => {
        if (!current) return;
        setStats(got);
        setFailure(null);
      },
      (e) => current && setFailure(toFailure(e)),
    );
    return () => {
      current = false;
    };
  }, [range]);

  // 排行和礼物要角色的名字和颜色：角色还没到时整页当作读取中，免得那几行晚一步冒出来、页面跳一下。
  if (!stats || characters === null) {
    const shownFailure = stats ? directoryFailure : failure;
    if (shownFailure) return <FailureNotice failure={shownFailure} />;
    return <p className="text-body text-muted-foreground">{copy.settings.loading}</p>;
  }

  const shown = statsSections(stats);
  if (shown.isEmpty) {
    return (
      <Empty>
        <EmptyHeader>
          <EmptyTitle>{t.empty}</EmptyTitle>
        </EmptyHeader>
        <EmptyContent>
          <Button
            variant="outline"
            nativeButton={false}
            render={<NextLink href={CONVERSATIONS} onClick={guard(CONVERSATIONS)} />}
          >
            {t.toConversations}
          </Button>
        </EmptyContent>
      </Empty>
    );
  }

  const byId = new Map(characters.map((c) => [c.id, c]));
  /** 眼前的下半部分是上一个跨度的：换了以后新的还没到，或者没取到。 */
  const otherRange = stats.range.span !== range;
  const { gifts } = stats.range;
  const giftee = gifts.most && byId.get(gifts.most.character_id);

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-4">
        {shown.portrait && <p className="text-header">{portrait(stats.all_hours)}</p>}
        <dl className="grid grid-cols-3 gap-3">
          <Figure label={t.daysKnown} value={stats.days_known} unit={t.days} />
          {shown.visits && (
            <>
              <Figure label={t.currentVisits} value={stats.visits.current} unit={t.days} />
              <Figure label={t.longestVisits} value={stats.visits.longest} unit={t.days} />
            </>
          )}
        </dl>
      </div>
      {shown.heatmap && (
        <section className="flex flex-col gap-2">
          <h2 className="text-header">{t.heatmap}</h2>
          <Heatmap heatmap={stats.heatmap} />
        </section>
      )}
      <div className="flex flex-col gap-4">
        <Tabs value={range} onValueChange={(value) => setRange(value as StatsRange)}>
          <TabsList aria-label={t.rangeLabel}>
            {STATS_RANGES.map((r) => (
              <TabsTrigger key={r} value={r}>
                {t.ranges[r]}
              </TabsTrigger>
            ))}
          </TabsList>
        </Tabs>
        {failure && <FailureNotice failure={failure} />}
        <div
          aria-busy={otherRange}
          className={cn("flex flex-col gap-8 transition-opacity duration-200", otherRange && "opacity-45")}
        >
          {shown.totals && (
            <dl className="grid grid-cols-3 gap-3">
              <Figure label={t.turns} value={stats.range.turns} />
              <Figure label={t.giftsGiven} value={gifts.given} />
            </dl>
          )}
          {shown.mostTalked && (
            <section className="flex flex-col gap-3">
              <h2 className="text-header">{t.mostTalked}</h2>
              <ol className="flex flex-col gap-3">
                {mostTalked(stats.range.characters).map((ranked) => {
                  const character = byId.get(ranked.character_id);
                  if (!character) return null;
                  return (
                    <li key={ranked.character_id} style={herVars(character.color)} className="flex items-center gap-3">
                      <MarkedAvatar name={character.name} src={character.avatar_url} size="sm" />
                      <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                        <div className="flex items-baseline justify-between gap-2">
                          <span className="truncate text-sm font-medium">{character.name}</span>
                          <span className="shrink-0 text-subtitle text-muted-foreground tabular-nums">
                            {t.talked(ranked.turns, ranked.days_known)}
                          </span>
                        </div>
                        <div className="h-2 rounded-full bg-muted">
                          <div className="h-full rounded-full bg-her-bar" style={{ width: `${ranked.share * 100}%` }} />
                        </div>
                      </div>
                    </li>
                  );
                })}
              </ol>
            </section>
          )}
          {shown.hours && (
            <section className="flex flex-col gap-2">
              <h2 className="text-header">{t.hours}</h2>
              <HourChart hours={stats.range.by_hour} />
            </section>
          )}
          {shown.gifts && (
            <section className="flex flex-col gap-3">
              <h2 className="text-header">{t.gifts}</h2>
              <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3">
                {gifts.most && giftee && (
                  <FigureOf label={t.mostGiven}>
                    <Giftee character={giftee} given={gifts.most.given} />
                  </FigureOf>
                )}
                <Figure label={t.likedGiven} value={gifts.liked} unit={t.timesUnit} />
              </dl>
            </section>
          )}
        </div>
      </div>
    </div>
  );
}

/** 一个数：上面 Subtitle 字号 muted 的标签，下面 1.5rem 的数，后面跟单位。 */
function Figure({ label, value, unit }: { label: string; value: number; unit?: string }) {
  return (
    <FigureOf label={label}>
      <span className="text-2xl font-semibold tabular-nums">{value}</span>
      {unit && <span className="text-subtitle text-muted-foreground">{unit}</span>}
    </FigureOf>
  );
}

function FigureOf({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <dt className="text-subtitle text-muted-foreground">{label}</dt>
      <dd className="flex min-w-0 items-baseline gap-1">{children}</dd>
    </div>
  );
}

/** 送得最多的那位：头像、名字和送了几次。 */
function Giftee({ character, given }: { character: Character; given: number }) {
  return (
    <span className="flex min-w-0 items-center gap-2 self-center">
      <MarkedAvatar name={character.name} src={character.avatar_url} size="sm" />
      <span className="truncate text-sm font-medium">{character.name}</span>
      <span className="shrink-0 text-subtitle text-muted-foreground tabular-nums">{t.times(given)}</span>
    </span>
  );
}
