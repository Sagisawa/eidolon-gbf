// 原型里的通话状态。正式实现时由 liveConversation 扩展出同样的阶段（spec「通话状态」）。

export type EndReason = "not-connected" | "dropped" | "time-up" | "limit" | "own-key" | "mic-denied";

export type CallPhase =
  | { kind: "idle" }
  | { kind: "dialing" }
  | { kind: "connected"; since: number }
  | { kind: "ended"; reason: EndReason };

/** 单次通话的时长上限（示意值）。 */
export const CALL_LIMIT_SECONDS = 30 * 60;

/** 结束页上的说明。是否计入限额按 CONTEXT.md「限额」「接通」。 */
export const endings: Record<
  EndReason,
  { title: string; body: string; counted: boolean; action?: { label: string } }
> = {
  "not-connected": {
    title: "没能接通",
    body: "语音服务没有响应，通话没有连上。",
    counted: false,
  },
  dropped: {
    title: "通话中断了",
    body: "网络或语音服务出了问题，通话在中途断开。已经说完的回合都记在对话里。",
    counted: true,
  },
  "time-up": {
    title: "这次通话已经满 30 分钟了",
    body: "单次通话最长 30 分钟，对所有人都一样。可以马上重拨。",
    counted: true,
  },
  limit: {
    title: "这一小时的通话次数用完了",
    body: "每小时最多发起 6 次通话，16:05 之后可以再打。语音相关服务都用自带密钥的通话不计入限额。",
    counted: false,
    action: { label: "去填自带密钥" },
  },
  "own-key": {
    title: "你的语音合成密钥调用失败",
    body: "密钥（末 4 位 a1b2）被服务拒绝，通话没有接通，也没有改用部署者的密钥。",
    counted: false,
    action: { label: "检查密钥" },
  },
  "mic-denied": {
    title: "没有麦克风权限",
    body: "浏览器拒绝了麦克风。在地址栏左侧的权限设置里允许麦克风，然后重拨。",
    counted: false,
  },
};

export function clock(seconds: number): string {
  const s = Math.max(0, Math.floor(seconds));
  return `${String(Math.floor(s / 60)).padStart(2, "0")}:${String(s % 60).padStart(2, "0")}`;
}
