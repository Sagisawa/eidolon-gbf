"use client";

import { useEffect, useRef } from "react";

import { callTones } from "@/lib/callTones";
import type { CallState } from "@/lib/liveConversation";

type Sounds = { ring: HTMLAudioElement; connect: HTMLAudioElement; hangUp: HTMLAudioElement };

/**
 * 电话本身的声音（CONTEXT.md「铃声」「接通音」「挂断音」）：跟着通话状态的切换响铃、停铃、播一次提示音，
 * 怎么切换对应什么声音见 callTones。它们不是角色的声音，「只看文字」和收起通话层都不影响；离开这一页时铃声跟着停。
 * 播放由用户点下拨打引起，一般不会被自动播放策略拦下；万一被拒就算了，不影响通话。
 */
export function useCallTones(phase: CallState["phase"]): void {
  const sounds = useRef<Sounds | null>(null);
  const last = useRef(phase);

  useEffect(() => {
    const ring = new Audio("/sounds/ringback.mp3");
    ring.loop = true;
    const loaded = { ring, connect: new Audio("/sounds/connect.ogg"), hangUp: new Audio("/sounds/hang-up.mp3") };
    sounds.current = loaded;
    return () => {
      stop(loaded.ring);
      sounds.current = null;
    };
  }, []);

  useEffect(() => {
    const from = last.current;
    last.current = phase;
    const loaded = sounds.current;
    if (!loaded) return;
    const { ring, once } = callTones(from, phase);
    if (ring === "start") play(loaded.ring);
    if (ring === "stop") stop(loaded.ring);
    if (once === "connect") play(loaded.connect);
    if (once === "hang-up") play(loaded.hangUp);
  }, [phase]);
}

function play(audio: HTMLAudioElement): void {
  audio.currentTime = 0;
  audio.play().catch(() => {});
}

function stop(audio: HTMLAudioElement): void {
  audio.pause();
  audio.currentTime = 0;
}
