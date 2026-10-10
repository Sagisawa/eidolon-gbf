// 舞台的循环（LightStage）和光谱的 DOM（Spectrum）之间传的几样东西。循环每帧算画面、直接写样式，
// 不走 React 状态；只有偶尔才变的（当前组合、该挂立绘的人）经这里通知 React。反过来，访客聚焦到谁、
// 按组合跳转，由 Spectrum 写在这里，循环下一帧读到。

export type StageSnapshot = {
  /** 第 2 幕当前的组合。 */
  unit: number;
  /** 该挂立绘的那一位（落地页模型的 `spectrum.stand`）。 */
  stand: string | null;
};

type Listener = () => void;

let snapshot: StageSnapshot = { unit: 0, stand: null };
const listeners = new Set<Listener>();

export const stageStore = {
  get: (): StageSnapshot => snapshot,
  /** 只有真的变了才通知。 */
  set(next: Partial<StageSnapshot>) {
    if (Object.entries(next).every(([k, v]) => snapshot[k as keyof StageSnapshot] === v)) return;
    snapshot = { ...snapshot, ...next };
    listeners.forEach((l) => l());
  },
  subscribe(listener: Listener) {
    listeners.add(listener);
    return () => listeners.delete(listener);
  },
  /** 访客聚焦到的偶像：指针移上去、键盘聚焦、手指点。循环据此让她的光和背景淡入。 */
  focus: null as string | null,
  /** 滚到第 u 个组合停稳的地方；运动版式的循环挂上它，`instant` 时不带过渡（键盘聚焦到别的组合时）。 */
  jump: null as ((unit: number, instant?: boolean) => void) | null,
};
