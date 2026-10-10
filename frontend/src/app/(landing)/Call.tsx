"use client";

import { useEffect, useRef, useState, type CSSProperties } from "react";

import { interactionStore, useInteraction } from "./interactionStore";
import { ANSWER_MS, callSounds, type Call as CallState } from "./model/interaction";
import { stageStore, useLayout, useStage } from "./stageStore";
import { StandSlot } from "./StandSlot";
import type { Speaker } from "./Voice";

export type CallCopy = {
  title: string;
  body: string;
  ringing: string;
  connected: string;
  answer: string;
  holdHint: string;
  hello: { ja: string; zh: string };
};

/** 手指松开以后这么久之内来的 click 是这次触摸带出来的，不算一次点击。 */
const TOUCH_CLICK_MS = 800;

/**
 * 第 4 幕「来电」：全屏是她（极深底色、立绘、竖排的名字），画面跟着铃声的节奏振动、发光，滚动经过时
 * 只有画面在响。访客接听才出声：电脑上点「接听」（或者用键盘、读屏器按下），一圈色光自己收拢；手机上
 * 长按，按住多久收拢多少，没按够就松开会退回去。收拢的同时响起铃声，收拢完就接通，播一声接通音，
 * 她说一句话（只有文字）。声音遵守声音开关，接通、挂断都由交互 reducer 决定；离开这一幕就挂断。
 *
 * 运动版式里光脉冲和振动由 LightStage 按落地页模型写进 --lp-pulse、--lp-shake-x/y，来电画面的不透明度是
 * --lp-act4；定格档里画面静止，接听不带收拢的动画，照样出声；静态档（不支持 WebGL）没有立绘。
 */
export function Call({
  speaker,
  ringGradient,
  copy,
}: {
  speaker: Speaker;
  /** 接听时收拢的那一圈色光：CSS 的 conic-gradient。 */
  ringGradient: string;
  copy: CallCopy;
}) {
  const { call } = useInteraction();
  const { act } = useStage();
  const layout = useLayout();
  /** 静止版式：这一幕快滚到了，才挂立绘。 */
  const [near, setNear] = useState(false);
  const section = useRef<HTMLElement>(null);
  const ringEl = useRef<HTMLSpanElement>(null);
  const statusEl = useRef<HTMLParagraphElement>(null);
  const hold = useRef<number | null>(null);
  const touchedAt = useRef(-Infinity);
  const connectedAt = useConnectedAt(call.phase);

  useCallTones();

  const setHold = (k: number) => ringEl.current?.style.setProperty("--lp-hold", String(k));
  const stopHold = () => {
    if (hold.current !== null) cancelAnimationFrame(hold.current);
    hold.current = null;
  };
  // 卸下时挂断：交互状态在模块里（interactionStore），不会跟着组件重来，不能停在接听中。
  useEffect(
    () => () => {
      stopHold();
      interactionStore.dispatch({ type: "hang-up" });
    },
    [],
  );

  // 离开这一幕就挂断：接听中的铃声停下，回到响铃的样子。
  const lastAct = useRef(act);
  useEffect(() => {
    const before = lastAct.current;
    lastAct.current = act;
    if (before === 4 && act !== 4) {
      stopHold();
      setHold(0);
      interactionStore.dispatch({ type: "hang-up" });
    }
  }, [act]);

  // 静止版式：这一幕进到视口附近才挂立绘。
  useEffect(() => {
    if (!layout || layout.motion || layout.tier === "static") return;
    const io = new IntersectionObserver(([e]) => setNear(e.isIntersecting), { rootMargin: "50% 0px" });
    io.observe(section.current!);
    return () => io.disconnect();
  }, [layout]);

  /** 开始接听。`auto`：点了一下（或者用键盘、读屏器按下），色光自己收拢；不然是手指按着，松开就退回去。 */
  const begin = (auto: boolean) => {
    if (interactionStore.dispatch({ type: "answer" }).call.phase !== "answering") return;
    // 定格档：点了就接通，不放收拢的动画。
    if (auto && layout?.tier === "reduced") return answered();
    const start = performance.now();
    const tick = (now: number) => {
      const k = Math.min(1, (now - start) / ANSWER_MS);
      setHold(k);
      if (k < 1) hold.current = requestAnimationFrame(tick);
      else {
        hold.current = null;
        answered();
      }
    };
    hold.current = requestAnimationFrame(tick);
  };
  const answered = () => {
    // 接听按钮接通以后就不在了：焦点在它身上的话，交给接通的状态，不掉回页面开头。
    const hadFocus = section.current?.contains(document.activeElement);
    interactionStore.dispatch({ type: "answered" });
    if (hadFocus) requestAnimationFrame(() => statusEl.current?.focus());
  };
  const cancel = () => {
    if (hold.current === null) return;
    stopHold();
    setHold(0);
    interactionStore.dispatch({ type: "answer-cancel" });
  };

  const wantStand = !!speaker.outfit && !!layout && layout.tier !== "static" && (layout.motion ? act === 3 || act === 4 : near);
  const connected = call.phase === "connected";

  return (
    <section ref={section} className="lp-act4" data-lp-act="4" data-phase={call.phase} aria-labelledby="lp-act4-title">
      <div className="lp-call-glow" aria-hidden />
      <div className="lp-call-her">
        {wantStand && (
          <div className="lp-call-stand" aria-hidden>
            <StandSlot outfit={speaker.outfit!} framing="waist" still={!layout.motion} speaking={false} />
          </div>
        )}
        <p className="lp-call-name" lang="ja" data-lp-find="act4">
          {speaker.name}
        </p>
      </div>
      <div className="lp-act4-copy" data-lp-find="act4">
        <h2 id="lp-act4-title" className="lp-act-title">
          {copy.title}
        </h2>
        <p className="lp-act-body">{copy.body}</p>
      </div>
      <div className="lp-call-ui">
        <p ref={statusEl} className="lp-call-status" role="status" tabIndex={-1}>
          {connected ? copy.connected : copy.ringing}
          {connected && connectedAt !== null && <Elapsed since={connectedAt} />}
        </p>
        {connected ? (
          <div className="lp-hello">
            <p className="lp-hello-ja" lang="ja">
              {copy.hello.ja}
            </p>
            <p className="lp-hello-zh">{copy.hello.zh}</p>
          </div>
        ) : (
          <div className="lp-answer-wrap">
            <span ref={ringEl} className="lp-answer-ring" style={{ "--lp-ring": ringGradient } as CSSProperties} aria-hidden />
            <button
              type="button"
              className="lp-answer"
              aria-describedby={layout?.touch ? "lp-answer-hint" : undefined}
              onPointerDown={(e) => {
                if (e.pointerType === "mouse") return;
                touchedAt.current = performance.now();
                e.currentTarget.setPointerCapture(e.pointerId);
                begin(false);
              }}
              onPointerUp={(e) => {
                if (e.pointerType === "mouse") return;
                touchedAt.current = performance.now();
                cancel();
              }}
              onPointerCancel={cancel}
              onClick={() => performance.now() - touchedAt.current > TOUCH_CLICK_MS && begin(true)}
              onContextMenu={(e) => e.preventDefault()}
              // 键盘聚焦到这里时还没滚到来电：先滚过去，按钮才在画面上。
              onFocus={() => layout?.motion && stageStore.get().act !== 4 && stageStore.goto?.(4)}
            >
              <svg className="lp-answer-icon" viewBox="0 0 24 24" aria-hidden>
                <path d="M6.6 10.8a15.2 15.2 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z" />
              </svg>
              <span className="lp-answer-label">{copy.answer}</span>
            </button>
            <span id="lp-answer-hint" className="lp-answer-hint">
              {copy.holdHint}
            </span>
          </div>
        )}
      </div>
    </section>
  );
}

/** 接通的时刻（performance.now()）；没接通时是 null。 */
function useConnectedAt(phase: CallState["phase"]): number | null {
  const [at, setAt] = useState<number | null>(null);
  useEffect(() => setAt(phase === "connected" ? performance.now() : null), [phase]);
  return at;
}

/** 通话时长，一秒一跳。读屏器不念它（状态那一行只在接通时念一次）。 */
function Elapsed({ since }: { since: number }) {
  const [now, setNow] = useState(since);
  useEffect(() => {
    const t = window.setInterval(() => setNow(performance.now()), 1000);
    return () => window.clearInterval(t);
  }, []);
  const s = Math.floor((now - since) / 1000);
  return (
    <span className="lp-call-time" aria-hidden>
      {String(Math.floor(s / 60)).padStart(2, "0")}:{String(s % 60).padStart(2, "0")}
    </span>
  );
}

/**
 * 电话的声音：铃声（循环）和接通音，复用应用通话用的那两个文件（GLOSSARY「铃声」「接通音」），接听时才加载。
 * 开始、停下、播一次都按交互状态的变化来（model/interaction.ts 的 callSounds）。真的响起来了报给 reducer
 * （第一次出声时出现声音开关），放不出来也报，但不当作错误。
 *
 * 接通音在色光收拢完才播，那时已经不在访客的手势里了：开始接听（手势里）时先静音地播一下再停住，Safari
 * 才肯在之后放它。
 */
function useCallTones() {
  useEffect(() => {
    let tones: { ring: HTMLAudioElement; connect: HTMLAudioElement } | null = null;
    const report = (event: "playing" | "failed") => interactionStore.dispatch({ type: "tone", event });
    const load = () => {
      if (tones) return tones;
      const ring = new Audio("/sounds/ringback.mp3");
      ring.loop = true;
      const connect = new Audio("/sounds/connect.ogg");
      for (const a of [ring, connect]) a.addEventListener("playing", () => !a.muted && report("playing"));
      return (tones = { ring, connect });
    };
    const play = (a: HTMLAudioElement) => {
      a.muted = false;
      a.currentTime = 0;
      a.play().catch(() => report("failed"));
    };
    const prime = (a: HTMLAudioElement) => {
      if (!a.paused) return;
      a.muted = true;
      a.play().then(
        () => {
          // 接通音已经要真的播了（muted 被 play 改回来）就不打断它。
          if (!a.muted) return;
          a.pause();
          a.currentTime = 0;
          a.muted = false;
        },
        () => (a.muted = false),
      );
    };
    const unsubscribe = interactionStore.subscribe((prev, next) => {
      const { ring, connect } = callSounds(prev, next);
      if (ring === "start") {
        const t = load();
        play(t.ring);
        prime(t.connect);
      }
      if (ring === "stop") tones?.ring.pause();
      if (connect) play(load().connect);
    });
    return () => {
      unsubscribe();
      tones?.ring.pause();
      tones?.connect.pause();
    };
  }, []);
}
