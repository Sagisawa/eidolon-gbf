// 落地页的交互状态（spec「交互状态」）：聚焦和点击偶像，招呼要不要出声，声音开关，第 4 幕的接听。
// 纯函数，不碰 DOM：音频的加载、播放和字幕的计时由组件做，结果以动作报回来。
//
// - 聚焦本身从不出声，页面也从不自动出声：只有点了偶像、接听了电话才有声音。
// - 第一次点就出声；真的出了声，才出现常驻的声音开关（开着），音频加载不出来时不出现一个管不了什么的开关。
//   关掉以后点偶像只显示字幕，接听也不出声。
// - 同时只说一句：点另一位、或者指针移到另一位身上，上一句就停下；接听时招呼也停下，接听中点了偶像就挂断。
// - 第 4 幕的来电，滚动经过时只有画面在响。访客接听（电脑上点，手机上长按）时色光收束，不放铃声；
//   收束完就接通、播一声接通音（GLOSSARY「接通音」）。离开这一幕就挂断，回到响铃的样子。

/** 正在说的一句。`n` 每说一句加一：音频事件和字幕的计时都带着它，上一句的事件不会落到这一句上。 */
export type Saying = {
  id: string;
  n: number;
  /** 声音：`loading` 加载中、`playing` 在播、`ended` 播完了；null 是只有字幕（没有音频、开关关着、加载失败）。 */
  voice: "loading" | "playing" | "ended" | null;
};

/** 第 4 幕的来电。 */
export type Call = {
  /** `ringing` 在响（只有画面）、`answering` 接听中（色光在收束）、`connected` 接通了。 */
  phase: "ringing" | "answering" | "connected";
  /** 这次接听出不出声：开始接听时声音开关没关，接通时就播接通音；接听中关掉开关就不播，再打开也不补。 */
  audible: boolean;
};

export type Interaction = {
  /** 指针、键盘焦点、手指指着的那位。 */
  pointed: string | null;
  /** 声音开关：第一次真的出声之前不出现；不出现时当作开着。 */
  sound: "hidden" | "on" | "off";
  saying: Saying | null;
  /** 说过几句，给下一句编号。 */
  said: number;
  call: Call;
};

const RINGING: Call = { phase: "ringing", audible: false };

export const INITIAL: Interaction = { pointed: null, sound: "hidden", saying: null, said: 0, call: RINGING };

export type VoiceEvent = "playing" | "ended" | "failed";

export type InteractionAction =
  /** 指针移上去、键盘聚焦。 */
  | { type: "point"; id: string }
  /** 指针移开、键盘焦点离开。 */
  | { type: "unpoint"; id: string }
  /** 点了她（或者聚焦后按 Enter）。`greeting`：她没有招呼、只有字幕（没有音频地址）、有音频。 */
  | { type: "press"; id: string; greeting: "none" | "subtitle" | "voice" }
  /** 离开她所在的地方（推入别的组合）：放下聚焦，正在说的也收掉。 */
  | { type: "leave" }
  /** 点声音开关。 */
  | { type: "sound" }
  /** 第 n 句的音频开始播放、播完、加载或播放失败（包括迟迟加载不出来）。 */
  | { type: "voice"; n: number; event: VoiceEvent }
  /** 第 n 句的字幕留够了。 */
  | { type: "done"; n: number }
  /** 开始接听：电脑上点了「接听」（或用键盘按下），手机上按下去。 */
  | { type: "answer" }
  /** 手机上没按够就松开了。 */
  | { type: "answer-cancel" }
  /** 色光收束完：接通。 */
  | { type: "answered" }
  /** 离开第 4 幕：挂断，回到响铃的样子。 */
  | { type: "hang-up" }
  /** 接通音真的响起来了，或者放不出来。 */
  | { type: "tone"; event: "playing" | "failed" };

/** 聚焦的那位：指着谁就是谁；谁都没指着时，正在说话的她。 */
export const focusOf = (s: Interaction): string | null => s.pointed ?? s.saying?.id ?? null;

/** 接听时色光收拢要多久（毫秒）：手机上要按住这么久，电脑上点一下以后自己收拢这么久。 */
export const ANSWER_MS = 900;

/** 只有字幕时留这么久（毫秒），够读完一句日语和它的字幕。 */
const TEXT_HOLD_MS = 7000;
/** 声音播完以后字幕再留这么久。 */
const AFTER_VOICE_MS = 1800;

/** 声音还在路上：在加载或在播。 */
export const voicing = (saying: Saying | null): boolean => saying?.voice === "loading" || saying?.voice === "playing";

/** 字幕还要留多久；音频还在加载或在播时等它（null）。 */
export function holdMs(saying: Saying): number | null {
  if (voicing(saying)) return null;
  return saying.voice === "ended" ? AFTER_VOICE_MS : TEXT_HOLD_MS;
}

export function interactionReducer(s: Interaction, a: InteractionAction): Interaction {
  switch (a.type) {
    case "point":
      return { ...s, pointed: a.id, saying: s.saying?.id === a.id ? s.saying : null };
    case "unpoint":
      return s.pointed === a.id ? { ...s, pointed: null } : s;
    case "press": {
      // 同时只有一种声音：接听到一半点了偶像，电话挂断。
      if (s.call.phase === "answering") s = { ...s, call: RINGING };
      if (a.greeting === "none") return { ...s, pointed: a.id, saying: null };
      const voiced = a.greeting === "voice" && s.sound !== "off";
      const n = s.said + 1;
      return {
        ...s,
        pointed: a.id,
        saying: { id: a.id, n, voice: voiced ? "loading" : null },
        said: n,
      };
    }
    case "leave":
      return { ...s, pointed: null, saying: null };
    case "sound":
      if (s.sound === "hidden") return s;
      if (s.sound === "off") return { ...s, sound: "on" };
      return { ...s, sound: "off", saying: s.saying && { ...s.saying, voice: null }, call: { ...s.call, audible: false } };
    case "voice": {
      if (s.saying?.n !== a.n || s.saying.voice === null) return s;
      const voice = a.event === "failed" ? null : a.event;
      return { ...s, saying: { ...s.saying, voice }, sound: voice === "playing" && s.sound === "hidden" ? "on" : s.sound };
    }
    case "done":
      return s.saying?.n === a.n ? { ...s, saying: null } : s;
    case "answer":
      if (s.call.phase !== "ringing") return s;
      return { ...s, saying: null, call: { phase: "answering", audible: s.sound !== "off" } };
    case "answer-cancel":
      return s.call.phase === "answering" ? { ...s, call: RINGING } : s;
    case "answered":
      return s.call.phase === "answering" ? { ...s, call: { ...s.call, phase: "connected" } } : s;
    case "hang-up":
      return s.call === RINGING ? s : { ...s, call: RINGING };
    case "tone":
      return a.event === "playing" && s.sound === "hidden" ? { ...s, sound: "on" } : s;
  }
}

/** 状态从 `prev` 变成 `next` 时要不要播接通音：接听中接通了，并且这次接听出声。 */
export const connectTone = (prev: Interaction, next: Interaction): boolean =>
  prev.call.phase === "answering" && next.call.phase === "connected" && next.call.audible;
