"use client";

import { useEffect, useRef } from "react";

import type { Tones } from "@/lib/liveConversation";

type Sounds = { ring: HTMLAudioElement; connect: HTMLAudioElement; hangUp: HTMLAudioElement };

/**
 * 电话本身的声音（GLOSSARY.md「铃声」「接通音」「挂断音」）的 adapter：建好铃声、接通音、挂断音三个 Audio
 * 元素，交出一个 `tones` port，由 LiveConversation 在拨号、接通、结束和离开页面这几处告诉页面响什么。
 * 它们不是角色的声音，「只看文字」和收起通话层都不影响。铃声等麦克风打开才响，已经不在拨打那一下点击里，
 * 但用户刚点过页面（Chrome 认这个），页面又正在用麦克风（Safari 认这个），一般不会被自动播放策略拦下；
 * 万一被拒就算了，不影响通话，也不用等它响满一遍。
 */
export function useCallTones(): Tones {
  const sounds = useRef<Sounds | null>(null);
  // 这一次铃声从什么时候响起（performance.now()）；没在响、或者被拒了是 null。
  const ringSince = useRef<number | null>(null);
  const tones = useRef<Tones | null>(null);
  if (tones.current === null)
    tones.current = {
      ring: () => {
        const s = sounds.current;
        if (!s) return;
        const since = performance.now();
        ringSince.current = since;
        s.ring.currentTime = 0;
        s.ring.play().catch(() => {
          if (ringSince.current === since) ringSince.current = null;
        });
      },
      ringLeft: () => {
        const s = sounds.current;
        const since = ringSince.current;
        if (!s || since === null || !Number.isFinite(s.ring.duration)) return 0;
        const round = s.ring.duration * 1000;
        // 第一遍里按它实际放到哪儿算（开始播放会晚一点）；过了一遍的时长就是响满了。
        return performance.now() - since >= round ? 0 : Math.max(0, round - s.ring.currentTime * 1000);
      },
      connect: () => {
        const s = sounds.current;
        ringSince.current = null;
        if (s) {
          stop(s.ring);
          play(s.connect);
        }
      },
      hangUp: () => {
        const s = sounds.current;
        ringSince.current = null;
        if (s) {
          stop(s.ring);
          play(s.hangUp);
        }
      },
      silence: () => {
        const s = sounds.current;
        ringSince.current = null;
        if (s) stop(s.ring);
      },
    };
  const port = tones.current;

  useEffect(() => {
    const loaded: Sounds = {
      ring: new Audio("/sounds/ringback.mp3"),
      connect: new Audio("/sounds/connect.ogg"),
      hangUp: new Audio("/sounds/hang-up.mp3"),
    };
    loaded.ring.loop = true;
    sounds.current = loaded;
    return () => {
      stop(loaded.ring);
      sounds.current = null;
    };
  }, []);

  return port;
}

function play(audio: HTMLAudioElement): void {
  audio.currentTime = 0;
  audio.play().catch(() => {});
}

function stop(audio: HTMLAudioElement): void {
  audio.pause();
  audio.currentTime = 0;
}
