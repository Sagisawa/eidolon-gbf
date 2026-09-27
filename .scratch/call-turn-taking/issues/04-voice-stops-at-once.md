# 04: 打断时声音立刻停下

**What to build:** 通话中角色被打断时，声音要立刻停下。现在从 `InterruptionFrame` 到声音真正停下要 0.9–1.4 秒，见 02 的 Comments 里的真实通话时间线。规则见 `../spec.md` 和 `CONTEXT.md` 的「打断」一条：「角色立刻停止发声」。

**Blocked by:** 02

**Status:** needs-triage

- [ ] 原因（Pipecat 1.11，`pipecat/services/tts_service.py`）：
  - `InterruptibleTTSService._handle_interruption` 在角色说话时（`_bot_speaking` 或 `_tts_started`），会先断开再重连 Fish 的 websocket；
  - `TTSService.process_frame` 要等它做完，才把 `InterruptionFrame` 往下游推；
  - 所以输出端要等重连结束才收到打断，这期间把已缓冲的音频继续播出去；
  - 打断前已经发出的 `delta` 和 `done`（`RTVIServerMessageFrame` 同样经过 TTS）也会晚到约 1 秒。
- [ ] 让打断先到达输出端，再重连。可能的做法：
  - 包一层 `FishAudioTTSService`，调整 `_handle_interruption` 的顺序；
  - 或者在 TTS 之后放一个处理器，直接转发打断。
  - 要注意：重连期间如果有新回复的文字送来，不能丢，也不能打到已经关掉的连接上。
- [ ] 测试：在 `test_voice_call.py` 的层面（假 TTS），打断之后输出端先收到打断，不必等 TTS 的重连完成。
- [ ] 真实通话验证：按 02 的场景再做一次，确认从 `InterruptionFrame` 到客户端静音在几百毫秒以内，`done` 也不再晚到。在 Comments 里记下时间线。
