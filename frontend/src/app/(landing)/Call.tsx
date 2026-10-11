"use client";

import { useEffect, useRef, useState } from "react";

import { interactionStore, useInteraction } from "./interactionStore";
import { connectTone, openerShown, openerStarts, type CallPhase, type VoiceEvent } from "./model/interaction";
import { stageStore, useLayout, useStage } from "./stageStore";
import { StandSlot } from "./StandSlot";
import type { Speaker } from "./Voice";

export type CallCopy = {
  title: string;
  body: string;
  ringing: string;
  connected: string;
  answer: string;
};

/**
 * 第 4 幕「来电」：她打来电话，画面跟着铃声的节奏发光、振动，滚动经过时只有画面在响。访客点一下「接听」（电脑、
 * 手机一样，键盘、读屏器按下也是）就接通，播一声接通音（不放铃声），接着她说开场白（GLOSSARY「开场白」，原文和字幕，有音频时出声、立绘动嘴），开始计时；她没有开场白时只有立绘和
 * 计时。声音遵守声音开关，接通、挂断、开场白出不出声都由交互 reducer 决定；离开这一幕就挂断。
 *
 * 运动版式里她的光收成一台手机的侧边，手机转到正面、亮屏（LightStage 和 phoneStage.ts 按落地页模型画）：three.js
 * 的画布放进 .lp-phone，来电界面（名字、状态、接听、接通后她说的一句）摆进模型给的屏幕矩形（--lp-screen-*），
 * 和手机在同一个容器里一起振动（--lp-shake-x/y）；标题在手机上方、正文在手机下方。手机画出来以前、手机画布丢了
 * 上下文时，是原来的全屏来电（她的立绘、竖排的名字）。光脉冲是 --lp-pulse，来电界面的不透明度是 --lp-act4；
 * 定格档里画面静止；静态档（不支持 WebGL）没有立绘。
 */
export function Call({ speaker, copy }: { speaker: Speaker; copy: CallCopy }) {
  const { call, opener } = useInteraction();
  const { act, phone } = useStage();
  const layout = useLayout();
  /** 静止版式：这一幕快滚到了，才挂立绘。 */
  const [near, setNear] = useState(false);
  const section = useRef<HTMLElement>(null);
  const statusEl = useRef<HTMLParagraphElement>(null);
  const connectedAt = useConnectedAt(call);

  useCallAudio(speaker.opener?.audio_url ?? null);

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
    const said = speaker.opener;
    interactionStore.dispatch({ type: "answer", opener: said ? (said.audio_url ? "voice" : "subtitle") : "none" });
    if (hadFocus) requestAnimationFrame(() => statusEl.current?.focus());
  };

  // 手机上的来电不挂全屏的立绘。
  const wantStand =
    !!speaker.outfit && !!layout && layout.tier !== "static" && !phone && (layout.motion ? act === 3 || act === 4 : near);
  const connected = call === "connected";

  return (
    <section ref={section} className="lp-act4" data-lp-act="4" data-phase={call} aria-labelledby="lp-act4-title">
      <div className="lp-call-glow" aria-hidden />
      <div className="lp-call-her">
        {wantStand && (
          <div className="lp-call-stand" aria-hidden>
            <StandSlot outfit={speaker.outfit!} framing="waist" still={!layout.motion} speaking={opener?.voice === "playing"} />
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
      <div className="lp-phone">
        <div className="lp-call-ui">
          <p ref={statusEl} className="lp-call-status" role="status" tabIndex={-1}>
            {connected ? copy.connected : copy.ringing}
            {connected && connectedAt !== null && <Elapsed since={connectedAt} />}
          </p>
          {connected ? (
            speaker.opener &&
            openerShown(opener) && (
              <div className="lp-hello">
                <p className="lp-hello-ja" lang="ja">
                  {speaker.opener.ja}
                </p>
                <p className="lp-hello-zh">{speaker.opener.subtitle}</p>
              </div>
            )
          ) : (
            <button
              type="button"
              className="lp-answer"
              onClick={answer}
              // 键盘聚焦到这里时来电还没显出来（没滚到，或者手机还在转）：先滚到手机停稳、亮屏的地方，按钮才在画面上。
              onFocus={() => layout?.motion && !section.current?.closest("[data-lp-call]") && stageStore.goto?.(4)}
            >
              <svg className="lp-answer-icon" viewBox="0 0 24 24" aria-hidden>
                <path d="M6.6 10.8a15.2 15.2 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.57a1 1 0 0 1-.25 1z" />
              </svg>
              <span className="lp-answer-label">{copy.answer}</span>
            </button>
          )}
        </div>
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

const CONNECT_TONE = "/sounds/connect.ogg";
/** 开场白这么久还没开始播就当作加载失败，退成只有字幕（和招呼一样）。 */
const OPENER_LOAD_TIMEOUT_MS = 8000;

/** 接通音和开场白的那个 <audio> 现在放的是哪一样。 */
type Playing = { what: "tone" } | { what: "opener"; n: number; timeout: number };

/**
 * 接通音和开场白：接通音复用应用通话用的那个文件（GLOSSARY「接通音」），接通时播一次（model/interaction.ts 的
 * connectTone）；它放完（或放不出来），reducer 说轮到她开口（openerStarts），就放开场白 `openerUrl`。
 *
 * 两样用同一个 <audio>，第一次接通时才建：订阅者在 dispatch 里同步跑，接通音在访客点「接听」的手势里放，
 * 同一个元素之后换成开场白再放，手机浏览器不会拦。开始播、播完、放不出来都报给 reducer（第一次出声时出现
 * 声音开关），放不出来不当作错误。挂断、关掉声音开关时 reducer 不再要开场白的声音，这里就停下。
 */
function useCallAudio(openerUrl: string | null) {
  const url = useRef(openerUrl);
  useEffect(() => {
    url.current = openerUrl;
  }, [openerUrl]);

  useEffect(() => {
    const dispatch = interactionStore.dispatch;
    let el: HTMLAudioElement | null = null;
    let now: Playing | null = null;

    /** 正在放的那样报一个事件；早就换掉了的（例如接通音被开场白顶掉时它的 play() 被打断）不报。 */
    const report = (playing: Playing | null, event: VoiceEvent) => {
      if (!playing || playing !== now) return;
      if (playing.what === "tone") return dispatch({ type: "tone", event });
      if (event !== "playing") now = null;
      window.clearTimeout(playing.timeout);
      dispatch({ type: "opener", n: playing.n, event });
    };
    const audio = () => {
      if (el) return el;
      el = new Audio();
      el.addEventListener("playing", () => report(now, "playing"));
      el.addEventListener("ended", () => report(now, "ended"));
      el.addEventListener("error", () => report(now, "failed"));
      return el;
    };
    const play = (playing: Playing, src: string) => {
      const a = audio();
      if (now?.what === "opener") window.clearTimeout(now.timeout);
      now = playing;
      a.src = src;
      a.currentTime = 0;
      a.play().catch(() => report(playing, "failed"));
    };
    const stop = () => {
      if (now?.what === "opener") window.clearTimeout(now.timeout);
      now = null;
      el?.pause();
    };

    const unsubscribe = interactionStore.subscribe((prev, next) => {
      if (connectTone(prev, next)) play({ what: "tone" }, CONNECT_TONE);
      const n = openerStarts(prev, next);
      if (n !== null) {
        // 没有地址（不该发生：没有音频时接听就只有字幕）也退成字幕；不在订阅者里同步再 dispatch。
        if (!url.current) return queueMicrotask(() => dispatch({ type: "opener", n, event: "failed" }));
        const playing: Playing = { what: "opener", n, timeout: 0 };
        playing.timeout = window.setTimeout(() => report(playing, "failed"), OPENER_LOAD_TIMEOUT_MS);
        play(playing, url.current);
        return;
      }
      // 挂断了、关掉了声音开关：她不再出声。接通音照常放完。
      const voicing = (v: typeof next.opener) => v?.voice === "loading" || v?.voice === "playing";
      if (now?.what === "opener" && voicing(prev.opener) && !voicing(next.opener)) stop();
    });
    return () => {
      unsubscribe();
      stop();
    };
  }, []);
}
