"use client";

import NextLink from "next/link";
import { useEffect, useState } from "react";

import { FailureNotice } from "@/components/app/FailureNotice";
import { useDirectory } from "@/components/conversations/ConversationDirectory";
import { Heatmap } from "@/components/stats/Heatmap";
import { Button } from "@/components/ui/button";
import { Empty, EmptyContent, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { copy } from "@/i18n";
import { getStats } from "@/lib/api";
import { toFailure, type Failure } from "@/lib/failure";
import { portrait, statsSections, type Stats } from "@/lib/stats";

const t = copy.settings.stats;

const CONVERSATIONS = "/conversations";

/**
 * 设置「统计」（GLOSSARY.md「统计」，DESIGN.md「统计页」）：上半部分不随时间跨度变，从上到下是一句话画像、
 * 认识天数和连续来访三个数、过去一年的热力图。哪一块没数据就不显示；一个回合、一次送礼都没有时整页只有一句话和去对话列表的按钮。
 * 每次打开都重新读，删掉历史对话后回来就是新的数。
 */
export function StatsSettings() {
  const [stats, setStats] = useState<Stats | null>(null);
  const [failure, setFailure] = useState<Failure | null>(null);
  const { guard } = useDirectory();

  useEffect(() => {
    getStats().then(setStats, (e) => setFailure(toFailure(e)));
  }, []);

  if (failure) return <FailureNotice failure={failure} />;
  if (!stats) return <p className="text-body text-muted-foreground">{t.loading}</p>;

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

  const figures = [
    { label: t.daysKnown, days: stats.days_known },
    ...(shown.visits
      ? [
          { label: t.currentVisits, days: stats.visits.current },
          { label: t.longestVisits, days: stats.visits.longest },
        ]
      : []),
  ];

  return (
    <div className="flex flex-col gap-8">
      <div className="flex flex-col gap-4">
        {shown.portrait && <p className="text-header">{portrait(stats.hours)}</p>}
        <dl className="grid grid-cols-3 gap-3">
          {figures.map(({ label, days }) => (
            <div key={label} className="flex flex-col gap-1">
              <dt className="text-subtitle text-muted-foreground">{label}</dt>
              <dd className="flex items-baseline gap-1">
                <span className="text-2xl font-semibold tabular-nums">{days}</span>
                <span className="text-subtitle text-muted-foreground">{t.days}</span>
              </dd>
            </div>
          ))}
        </dl>
      </div>
      {shown.heatmap && (
        <section className="flex flex-col gap-2">
          <h2 className="text-header">{t.heatmap}</h2>
          <Heatmap heatmap={stats.heatmap} />
        </section>
      )}
    </div>
  );
}
