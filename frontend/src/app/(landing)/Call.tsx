"use client";

import { useEffect, useRef, useState } from "react";

import { interactionStore, useInteraction } from "./interactionStore";
import { connectTone, type CallPhase } from "./model/interaction";
import { stageStore, useLayout, useStage } from "./stageStore";
import { StandSlot } from "./StandSlot";
import type { Speaker } from "./Voice";

export type CallCopy = {
  title: string;
  body: string;
  ringing: string;
  connected: string;
  answer: string;
  hello: { ja: string; zh: string };
};

/**
 * 第 4 幕「来电」：全屏是她（极深底色、立绘、竖排的名字），画面跟着铃声的节奏发光、名字跟着振动，滚动经过时
 * 只有画面在响。访客点一下「接听」（电脑、手机一样，键盘、读屏器按下也是）就接通，播一声接通音（不放铃声），
 * 她说一句话（只有文字），开始计时。声音遵守声音开关，接通、挂断都由交互 reducer 决定；离开这一幕就挂断。
 *
 * 运动版式里光脉冲和振动由 LightStage 按落地页模型写进 --lp-pulse、--lp-shake-x/y，来电画面的不透明度是
 * --lp-act4；定格档里画面静止；静态档（不支持 WebGL）没有立绘。
 */
export function Call({ speaker, copy }: { speaker: Speaker; copy: CallCopy }) {
  const { call } = useInteraction();
  const { act } = useStage();
  const layout = useLayout();
  /** 静止版式：这一幕快滚到了，才挂立绘。 */
  const [near, setNear] = useState(false);
  const section = useRef<HTMLElement>(null);
  const statusEl = useRef<HTMLParagraphElement>(null);
  const connectedAt = useConnectedAt(call);

  useConnectTone();

  // 卸下时挂断：交互状态在模块里（interactionStore），不会跟着组件重来。
  useEffect(() => () => void interactionStore.dispatch({ type: "hang-up" }), []);

  // 离开这一幕就挂断，回到响铃的样子。
  const lastAct = useRef(act);
  useEffect(() => {
    const before = lastAct.current;
    lastAct.current = act;
    if (before === 4 && act !== 4) interactionStore.dispatch({ type: "hang-up" });
  }, [act]);

  // 静止版式：这一幕进到视口附近才挂立绘。
  useEffect(() => {
    if (!layout || layout.motion || layout.tier === "static") return;
    const io = new IntersectionObserver(([e]) => setNear(e.isIntersecting), { rootMargin: "50% 0px" });
    io.observe(section.current!);
    return () => io.disconnect();
  }, [layout]);

  const answer = () => {
    // 接听按钮接通以后就不在了：焦点在它身上的话，交给接通的状态，不掉回页面开头。
    const hadFocus = section.current?.contains(document.activeElement);
    interactionStore.dispatch({ type: "answer" });
    if (hadFocus) requestAnimationFrame(() => statusEl.current?.focus());
  };

  const wantStand = !!speaker.outfit && !!layout && layout.tier !== "static" && (layout.motion ? act === 3 || act === 4 : near);
  const connected = call === "connected";

  return (
    <section ref={section} className="lp-act4" data-lp-act="4" data-phase={call} aria-labelledby="lp-act4-title">
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
          <button
            type="button"
            className="lp-answer"
            onClick={answer}
            // 键盘聚焦到这里时还没滚到来电：先滚过去，按钮才在画面上。
            onFocus={() => layout?.motion && stageStore.get().act !== 4 && stageStore.goto?.(4)}
          >
            <svg className="lp-answer-icon" viewBox="0 0 24 24" aria-hidden>
              <path d="M6.6 10.8a15.2 15.2 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z" />
            </svg>
            <span className="lp-answer-label">{copy.answer}</span>
          </button>
        )}
      </div>
    </section>
  );
}

/** 接通的时刻（performance.now()）；没接通时是 null。 */
function useConnectedAt(call: CallPhase): number | null {
  const [at, setAt] = useState<number | null>(null);
  useEffect(() => setAt(call === "connected" ? performance.now() : null), [call]);
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

const reportTone = (event: "playing" | "failed") => interactionStore.dispatch({ type: "tone", event });

/**
 * 接通音：复用应用通话用的那个文件（GLOSSARY「接通音」），第一次接通时才加载，接通时播一次（model/interaction.ts
 * 的 connectTone）。订阅者在 dispatch 里同步跑，播放就发生在访客点「接听」的手势里，手机浏览器不会拦。
 * 真的响起来了报给 reducer（第一次出声时出现声音开关），放不出来也报，但不当作错误。
 */
function useConnectTone() {
  useEffect(() => {
    let tone: HTMLAudioElement | null = null;
    const unsubscribe = interactionStore.subscribe((prev, next) => {
      if (!connectTone(prev, next)) return;
      if (!tone) {
        tone = new Audio("/sounds/connect.ogg");
        tone.addEventListener("playing", () => reportTone("playing"));
      }
      tone.currentTime = 0;
      tone.play().catch(() => reportTone("failed"));
    });
    return () => {
      unsubscribe();
      tone?.pause();
    };
  }, []);
}
