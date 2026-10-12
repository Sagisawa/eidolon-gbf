"use client";

import { useEffect, useState } from "react";

import { AnnouncementBody } from "@/components/app/AnnouncementBody";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogFooter, DialogHeader, DialogTitle, DialogTrigger } from "@/components/ui/dialog";
import { Empty, EmptyHeader, EmptyTitle } from "@/components/ui/empty";
import { Separator } from "@/components/ui/separator";
import { copy } from "@/i18n";
import {
  keepReadUpTo,
  listAnnouncements,
  newestPublished,
  readUpTo,
  unread,
  type Announcement,
} from "@/lib/announcements";
import { AnnouncementsBellIcon } from "@/theme/icons";

const t = copy.conversationList;

/**
 * 对话列表页首的铃铛和它打开的公告弹窗（GLOSSARY.md「公告」「未读公告」，DESIGN.md「Conversation list」）。
 * 有未读时铃铛右上角一个小圆点。弹窗列出最近的公告，最新的在上面；「关闭」、Esc、点外面只收起，「已读」把列表里的
 * 都记成读过（只记在这台设备上，按用户分开）再收起。列表载入时拉一次，切回这个标签页时再拉一次；拉不到就保持上一次的。
 * `userId` 还在载入时为 null，这时不知道读过什么，不显示点。
 */
export function Announcements({ userId }: { userId: string | null }) {
  const [announcements, setAnnouncements] = useState<Announcement[] | null>(null);
  const [isOpen, setOpen] = useState(false);
  // 每次渲染现读：点「已读」记下之后收起弹窗，这次渲染就读到新的。
  const readAt = userId ? readUpTo(userId) : null;
  const unreadIds = userId && announcements ? unread(announcements, readAt) : new Set<string>();
  const hasUnread = unreadIds.size > 0;

  useEffect(() => {
    let cancelled = false;
    const load = () =>
      listAnnouncements().then(
        (all) => !cancelled && setAnnouncements(all),
        () => {}, // 公告不是要紧的事，拉不到时保持上一次的
      );
    const onVisible = () => {
      if (document.visibilityState === "visible") load();
    };
    load();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      cancelled = true;
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  const markRead = () => {
    const upTo = announcements && newestPublished(announcements);
    if (userId && upTo) keepReadUpTo(userId, upTo);
    setOpen(false);
  };

  return (
    <Dialog open={isOpen} onOpenChange={setOpen}>
      <DialogTrigger
        render={
          <Button
            variant="ghost"
            size="icon-lg"
            aria-label={hasUnread ? t.announcementsUnread : t.announcements}
            className="relative"
          />
        }
      >
        <AnnouncementsBellIcon />
        {hasUnread && <span aria-hidden className="absolute top-1.5 right-1.5 size-1.5 rounded-full bg-foreground" />}
      </DialogTrigger>
      <DialogContent showCloseButton={false} className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle>{t.announcements}</DialogTitle>
        </DialogHeader>
        {announcements && announcements.length > 0 ? (
          <ul className="-mx-4 max-h-[70dvh] overflow-y-auto px-4">
            {announcements.map((a, i) => (
              <li key={a.id}>
                {i > 0 && <Separator className="my-4" />}
                <p className="mb-2 flex items-center gap-2 text-meta text-muted-foreground tabular-nums">
                  {publishedOn(a.published_at)}
                  {unreadIds.has(a.id) && <Badge variant="secondary">{t.unreadAnnouncement}</Badge>}
                </p>
                <AnnouncementBody body={a.body} />
              </li>
            ))}
          </ul>
        ) : (
          <Empty>
            <EmptyHeader>
              <EmptyTitle>{t.noAnnouncements}</EmptyTitle>
            </EmptyHeader>
          </Empty>
        )}
        {/* 两种屏宽都是右对齐的一行，不像默认那样在窄屏竖着排。 */}
        <DialogFooter className="flex-row justify-end">
          <Button variant="ghost" onClick={() => setOpen(false)}>
            {copy.common.close}
          </Button>
          <Button disabled={!hasUnread} onClick={markRead}>
            {t.markAnnouncementsRead}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

/** 发布的那一天，按这台设备的时区，和对话列表更早的日期写法一样。 */
function publishedOn(at: string): string {
  const day = new Date(at);
  return t.fullDate(String(day.getFullYear()), String(day.getMonth() + 1), String(day.getDate()));
}
