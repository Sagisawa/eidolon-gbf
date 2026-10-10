// 落地页的交互状态（spec「交互状态」）：聚焦和点击偶像，招呼要不要出声，声音开关。纯函数，不碰 DOM：
// 音频的加载、播放和字幕的计时由组件做，结果以动作报回来。
//
// - 聚焦本身从不出声，页面也从不自动出声：只有点了偶像才说话。
// - 第一次点就出声；真的出了声，才出现常驻的声音开关（开着），音频加载不出来时不出现一个管不了什么的开关。
//   关掉以后点偶像只显示字幕。
// - 同时只说一句：点另一位、或者指针移到另一位身上，上一句就停下。

/** 正在说的一句。`n` 每说一句加一：音频事件和字幕的计时都带着它，上一句的事件不会落到这一句上。 */
export type Saying = {
  id: string;
  n: number;
  /** 声音：`loading` 加载中、`playing` 在播、`ended` 播完了；null 是只有字幕（没有音频、开关关着、加载失败）。 */
  voice: "loading" | "playing" | "ended" | null;
};

export type Interaction = {
  /** 指针、键盘焦点、手指指着的那位。 */
  pointed: string | null;
  /** 声音开关：第一次真的出声之前不出现；不出现时当作开着。 */
  sound: "hidden" | "on" | "off";
  saying: Saying | null;
  /** 说过几句，给下一句编号。 */
  said: number;
};

export const INITIAL: Interaction = { pointed: null, sound: "hidden", saying: null, said: 0 };

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
  | { type: "done"; n: number };

/** 聚焦的那位：指着谁就是谁；谁都没指着时，正在说话的她。 */
export const focusOf = (s: Interaction): string | null => s.pointed ?? s.saying?.id ?? null;

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
      return { ...s, sound: "off", saying: s.saying && { ...s.saying, voice: null } };
    case "voice": {
      if (s.saying?.n !== a.n || s.saying.voice === null) return s;
      const voice = a.event === "failed" ? null : a.event;
      return { ...s, saying: { ...s.saying, voice }, sound: voice === "playing" && s.sound === "hidden" ? "on" : s.sound };
    }
    case "done":
      return s.saying?.n === a.n ? { ...s, saying: null } : s;
  }
}
