# 20: 通话 module：信令、归属、限额和管线藏到一个 interface 后面

**What to build:** 把 `app.py` 里的通话逻辑（peer 连接注册表、归属检查、通话限额的扣除与退还、`Call` 构造、`SmallWebRTCRequestHandler`、ICE servers 与 TURN 凭证）和 `call.serve_calls` 收进一个 `Calls` module；测试 seam 从 `CallStarter` 下移到真正的外部服务 STT 与 TTS（`Speech` port），补上从 `/api/offer` 到落库消息的端到端测试。

**Blocked by:** —

**Status:** ready-for-agent

## 背景（2026-09-26，架构体检候选 5）

候选 1、2、3（ticket 18、记忆 module、ticket 19）合入之后：

1. `app.py` 仍持有 `calls` 注册表、归属、`usage.take/give_back`、`Call` 构造和 WebRTC handler；ticket 19 明确把这些留给候选 5。
2. seam 在 `CallStarter`，`FakeCalls` 停在那里：RTVI 经 data channel 的收发从未被自动化测试覆盖（ticket 04 只手动冒烟过），也没有测试确认语音回合看得到检索和记忆。
3. ticket 14 的已知缺口：通话在 SDP 应答之后才失败（ICE 不通、Soniox / Fish 连不上）时计数不退还。
4. 服务停止时正在进行的通话没人等：`webrtc.close()` 只异步触发 `worker.cancel()`，回合可能在 Store 和记忆关闭后才写入。

可行性验证（离线、进程内）：aiortc 浏览器 ↔ 真实 `SmallWebRTCRequestHandler` 经 loopback host candidate 约 35ms 接通，`STTService` / `TTSService` 的假子类接进原样管线，`user`/`delta`/`done` 经 data channel 到达浏览器，打字的 `user-text` 被接下，落库、挂断干净；30 次无失败。

## Comments

### 决定（2026-09-26，grill-with-docs）

- **边界**：`Calls` 拥有注册表、归属、通话限额、`Call` 构造、管线启动、WebRTC handler 生命周期、ICE servers 与 TURN 凭证。`app.py` 不再 import `aiortc` / `pipecat`，只做鉴权、`conversation_or_404`，并把领域异常翻译成状态码。
- **interface**：`ice_servers(user_id)`、`start(user_id, conversation, character, CallOptions(muted, quality, device_timezone), offer) -> answer`、`renegotiate(user_id, offer) -> answer`、`add_candidates(user_id, patch)`、`aclose()`。异常：`CallsUnavailable` → 503、`CallNotFound`（不存在或不是你的）→ 404、`CallFailed`（信令失败，计数已退还）→ 500、`OverLimit` → 429。`Backend.calls` 始终存在，未配置语音时由它抛 `CallsUnavailable`（与记忆 module 的 null 实现同一思路），`require_voice` 消失。
- **seam**：一个 `Speech` port 成对给出 `stt() -> STTService` 与 `tts(voice_id, sample_rate) -> TTSService`；生产实现 Soniox + Fish Audio 在两个 key 都有时才构造得出来（「两者都配置才能通话」住在这里）。`build(speech=...)` 取代 `build(call_starter=...)`；`CallStarter`、`serve_calls`、`FakeCalls` 删除。`CallLimits` 由 `Calls` 从 Settings 读。
- **接通与限额**（`CONTEXT.md`「接通」）：offer 时先扣。退还：连接在 connected 之前就 closed / failed；30 秒仍未 connected（主动断开，清掉注册表条目）；因服务不可用结束（`ProcessorUnusablePolicy.CANCEL`）且一个回合都没记下。其余都计数：用户挂断、达到上限、服务停止。
- **关闭**：`Calls.aclose()` 取消所有通话并等它们结束、再关闭 WebRTC handler，排在记忆关闭之前；进行中的回合按失败处理，不留记录。lifespan 里单独的 `webrtc.close()` 去掉。
- **测试**：新增端到端（aiortc 浏览器 + 真实 loopback WebRTC + `FakeSpeech` + 带检索和记忆的完整 engine）：说话、打字、`X-Timezone`、检索与记忆、落库；限额的三种退还（连不上、服务故障且零回合、有回合不退）。`test_voice_call` 改用 `FakeSpeech`，用例全保留。`test_call_turns` 只留静音、空白、打断、两种上限、失败回合不计入上限、一个回复一次 TTS 响应；「打字和说话进同一条对话」「设备时区」挪到端到端。测试里把 Pipecat 的 NLTK 断句器换成按「。！？」切分，保持离线（生产镜像已下载 `punkt_tab`）。
- **范围外**：「每位用户同时只能有一个通话」不做。
- `CONTEXT.md` 新增「通话」「接通」（已提交）；不写 ADR（都容易撤回）。
