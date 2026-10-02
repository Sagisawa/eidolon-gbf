# 02: 部署者可以选阿里云百炼做语音识别

**What to build:** 百炼的 pipecat STT 服务，以及 `STT_PROVIDER=bailian` 的部署配置。部署者选百炼后，所有没有自带语音识别密钥的用户，通话都由百炼识别，补充和打断照常。背景见 `../spec.md`，参数来自 ticket 01 的 Answer。

**Blocked by:** 01。只改 `backend/`。

**Status:** ready-for-agent

## 要做的

- **拆开 `SonioxFishSpeech`**：语音识别和语音合成分开，语音识别按服务商有两个实现（Soniox、百炼），Fish Audio 不变。`Speech` port 的形状可以改，但 `Calls` 那边仍然不区分是谁的 key。
- **`FOLLOW_ON_TIMEOUT` 由语音识别服务给出**：`CallTurns` 从通话实际用的那家拿，不再是 `call.py` 里的全局常量。Soniox 保持 4.0；百炼 3.0（ticket 01）。`test_call_turns.py` 里 monkeypatch 这个常量的地方跟着改。
- **百炼 STT 服务**：继承 `WebsocketSTTService`，用 `websockets` 直连，不引入 `dashscope` SDK。
  - 协议：`run-task`（`language_hints: ["zh","ja"]`、`vad_model: "near_meeting_16k"`、`heartbeat: true`，见 ticket 01 的 Answer）→ 等 `task-started` → 二进制音频帧 → `result-generated` → 结束时 `finish-task`、等 `task-finished`。`task-failed` 当作服务出错。
  - 音频重采样到 16 kHz 单声道 PCM。
  - 第一条**有字**的中间结果出来时 `ProposedUserStartedSpeakingFrame` + `InterimTranscriptionFrame`；`sentence_begin` 的空结果和 `heartbeat=true` 的心跳跳过；`sentence_end=true` 时 `ProposedUserStoppedSpeakingFrame` + `TranscriptionFrame`；空稿（去掉标点和空白后为空）不发 `TranscriptionFrame`，细则见 ticket 01 的 Answer。
  - 麦克风静音期间不能让服务端 23 秒超时把通话断掉：开 `heartbeat`，上游一段时间没有音频帧时补发静音。浏览器静音时 pipecat 是否继续送音频帧，实现时确认。
  - key 被拒等不可恢复的错误让处理器不可用，照现有的 `ProcessorUnusablePolicy.CANCEL` 结束通话。
- **地域**：给一个 key，先连北京、被拒再连新加坡（老域名，见 spec）。
- **配置**：`config.py` 加 `STT_PROVIDER`（`soniox`|`bailian`，默认 `soniox`，其他值启动报错）、`DASHSCOPE_API_KEY`、`BAILIAN_STT_MODEL`（默认 `qwen-audio-3.1-asr-flash-streaming`，暂时只允许它，其他值启动报错）。`DeployerKeys.stt` 取所选那家的 key。
- **启动时试调**：选百炼且填了 key 时，用 `run-task`/`finish-task` 试调并判断地域；两个地域都拒绝或模型没开通，拒绝启动并说明原因（`去阿里云百炼控制台开通 <模型名>` 之类）。没填 key 照常启动、不开放通话。
- `SERVICE_LABELS["stt"]` 和自带密钥的部分本 ticket 不动（ticket 03）。

## 验收

- [ ] **按 TDD**：先写测试看到红，再写实现。
- [ ] 百炼 STT 服务的单元测试：用一个假的 WebSocket 服务端回放 `task-started`、几条 `result-generated`、`task-finished`，断言发出的帧和顺序；`sentence_begin` 空结果和心跳不算开口；空稿不出 `TranscriptionFrame`；`task-failed` 和握手 401 让服务不可用。
- [ ] 地域判断的测试：北京 401 时改连新加坡；两边都 401 时报错。
- [ ] 配置测试：默认 `soniox`；`bailian` 时用 `DASHSCOPE_API_KEY`；非法的 `STT_PROVIDER`、`BAILIAN_STT_MODEL` 启动报错。
- [ ] `CallTurns` 按通话所用服务的 `FOLLOW_ON_TIMEOUT` 等待补充，现有的补充和打断测试全部照常通过。
- [ ] `backend/` 下 `pytest` 全部通过，`pyright` 0 errors。
- [ ] **人工验收（留给用户）**：`STT_PROVIDER=bailian` 起本地后端和前端，打一通电话：
  - 中文、日语都能识别，字幕和回复正常；
  - 角色说话时开口能打断，角色没开口前补一句能并入；
  - 咳嗽一声不会打断、不会多出空回合；
  - 静音麦克风 30 秒以上，通话不断；
  - 填一个错的 `DASHSCOPE_API_KEY`，后端拒绝启动并说明原因。

## Comments
