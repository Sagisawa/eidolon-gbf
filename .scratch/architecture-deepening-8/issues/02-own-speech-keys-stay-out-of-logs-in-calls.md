# 02: 通话中自带的语音 key 失败时，key 不出服务器

**What to build:** 补上 ADR-0017「服务器的日志和报错不能带出 key」的最后一块验证：通话中途，用户自带的语音合成 key 或语音识别 key 失败时，服务器的日志（logging 和 loguru，包括 Pipecat 自己打的）和发给用户的结束原因里都找不到这把 key。现在 `test_own_keys_in_logs.py` 只覆盖文字回合和三个校验接口，不打电话。如果测出泄漏，在这张票里把漏的那一处遮掉。

只改后端。背景见 `../spec.md`（「Testing Decisions」里「key 不出服务器」一条）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## 已定的设计（2026-10-11 grilling，详见 spec）

- 只补测试，不重组遮蔽的做法（现在分散在几处）；测出漏处就修那一处，修法和已有的一致：先把 key 遮成 `***` 再截断。
- 经 `Browser.call` 跑真实的 WebRTC，`FakeSpeech` 让自带的那一项在通话中途失败，失败的原文里带上这把 key（模拟服务商把 key 回显在报错里）。
- 日志级别按生产的设置（loguru 只输出 INFO 以上），和已有的泄漏测试一样。

## 验收

- [ ] 新测试：通话中自带的语音合成 key 失败，抓 logging 和 loguru 的输出，断言找不到 key；浏览器收到的结束消息里的原因也没有 key。
- [ ] 新测试：同上，换成自带的语音识别 key。
- [ ] 如果有泄漏：修好，并在 Comments 里写明漏在哪里、怎么修的。
- [ ] `pytest` 全部通过，`ruff`、`pyright` 没有新的报错。
- [ ] 人工验收清单写进 Comments（例如：设置页填一把故意写错的语音合成 key 拨号，看通话结束时的提示和服务器日志里都没有这把 key）。
