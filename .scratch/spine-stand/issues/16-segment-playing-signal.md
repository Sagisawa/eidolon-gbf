# 16: 每段声音开始播放时，前端会收到标记

**What to build:** 通话中，角色的每段话一开始播放，前端就收到一条 `segment-playing {reply, segment}` 消息，时机跟着真实播放走。为此 Fish 改成每段一个会话，并预先开好下一个连接，段落之间不能多出听得出来的停顿。段落边界主动 flush，顺带修掉「每段最后一句日语要等下一段的中文字幕生成后才送去合成」。前端先把这条消息解析成事件，这一张不影响画面。规则见 `../spec.md`「Fish 分段合成」一节；依据和实测见「调研：pipecat 怎么知道每段语音什么时候开始播放」和「拍板：每段语音开始播放的信号怎么做」（`10-segment-playback-timing.md`、`11-segment-start-signal.md`）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] **回复编号**：`CallTurns` 给每条回复编号，一次通话里递增。发给 TTS 的日语要带上回复编号和段号，现在的 `Voice` 命令要能表达这一点。
- [ ] **每段一个 Fish 会话**：
  - 当前这段在合成时，就把下一段要用的连接打开等着。
  - 当前段结束时，发 `stop` 并等到 `finish`，然后立即在备用连接上开始下一段。
  - 一条回复的最后一段结束后，不再多开备用连接。开着闲置的连接，下一条回复开始时可以直接用；Fish 空等约 7 秒不会断开。连接要不要设一个空闲超时，由你定，在 Comments 里说明。
- [ ] **段落开始的标记**：在第 N 段第一块音频之前，往音频队列里插一条 `OutputTransportMessageFrame`，内容是 RTVI server message `{type: "segment-playing", reply, segment}`，由输出传输层按播放节奏发出。
- [ ] **段落边界 flush**：一段的日语在段落完整时（`SegmentComplete`）立即 flush 给 Fish，不再等下一段的文字。
- [ ] **打断**：行为和现在的 `InterruptsFirst` 一致，立即放行打断、在后台重建连接；备用连接一起作废。已经排进队列、还没发出的 `segment-playing` 随音频一起清掉。
- [ ] **只看文字**：不合成，也不发 `segment-playing`。
- [ ] **前端**：把 `segment-playing` 解析成一种新的 `CallEvent`，`LiveConversation` 记下「现在播到哪条回复的第几段」，暂时不影响画面。
- [ ] **测试**：
  - 后端，照语音打断测试的做法，用一个假的 Fish WebSocket：每段一个会话；下一个连接预先打开；段落完整时 flush；`segment-playing` 正好排在这段第一块音频之前，回复编号和段号都正确；打断时立即停止，备用连接作废。
  - 后端帧级测试（`CallUnderTest`）：多段回复时，每段的日语带着正确的回复编号和段号送给 TTS。
  - 前端：`segment-playing` 事件正确更新快照。
- [ ] **真实通话验证**：打一通电话，听三段以上的回复，确认段落之间没有多出停顿；在浏览器开发者工具里看 `segment-playing` 的到达时间和听到声音的时间是否对得上。在 Comments 里记下结果。
- [ ] `uv run pytest`、`uv run pyright`、`npm test`、`npm run typecheck` 全部通过。
