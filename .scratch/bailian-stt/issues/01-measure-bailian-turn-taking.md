# 01: 测量百炼实时识别在轮流说话上的表现

**Type:** prototype

**What to build:** 一个一次性的测量脚本，用真实的百炼 key 连 `qwen-audio-3.1-asr-flash-streaming`，把录好的音频按实时速度推过去，记下每条事件和它到达的时间。脚本和录音放在 `.scratch/bailian-stt/prototype/`，不进 `backend/src`；结论写进本文件的 `## Answer`。背景见 `../spec.md`。

**Blocked by:** None (can start immediately)。需要用户在 `.env` 里填 `DASHSCOPE_API_KEY`（北京地域，已开通 3.1），并录几段音频（见下）。

**Status:** ready-for-agent

## 要回答的问题

1. **出终稿要多久**：从说完最后一个字（录音里的时刻）到收到 `sentence_end=true`，各要多久？`near_meeting_16k` 和 `far_field_meeting_16k` 各测一遍。由此定百炼的 `FOLLOW_ON_TIMEOUT`（Soniox 是 4.0：最长端点延迟 3 秒加余量）。`max_sentence_silence` 对 3.1 是否生效，顺带测一下。
2. **开口多快被发现**：从开口到第一条中间结果要多久？这决定打断的反应速度。
3. **没听到词时出不出稿**：咳嗽、清嗓、键盘声、短暂的「嗯」，会不会出 `sentence_end=true` 的空稿或乱码稿？如果出，长什么样（空字符串？标点？）。
4. **中日混说**：`language_hints: ["zh","ja"]` 下，纯中文、纯日语、一句里中日混说（如「真乃ちゃん今天好可爱」）、角色名（「櫻木真乃」「風野灯織」）的识别效果。和不填 `language_hints` 对比一次。
5. **静音保活**：持续发静音 30 秒以上，会不会被断开（23 秒超时说的是「不发数据」还是「没有语音」）？要不要开 `heartbeat`？
6. **试调能不能不花钱**：`run-task` → `task-started` → `finish-task`、不发音频，控制台账单上是否为 0；模型没开通时返回什么（用一个没开通的模型名试，如 `fun-asr-realtime`，如果它没开通的话）；北京的 key 连新加坡返回什么。
7. **中间结果的形态**：`stash` 和 `fixed` 怎么变化，`text` 是累积的还是增量的；一段话里会不会出多个 `sentence_end`。

## 录音（用户提供）

16 kHz 单声道 WAV，用通话时会用的那种麦克风录，放 `.scratch/bailian-stt/prototype/audio/`：

- 一句中文、一句日语、一句中日混说、一句带角色名的话；
- 两句话中间停顿约 1 秒（看会不会被切成两句）；
- 咳嗽、清嗓、「嗯……」；
- 30 秒以上的安静。

录音不提交（`.scratch/bailian-stt/prototype/audio/` 加进 `.gitignore`）。

## 验收

- [ ] 上面 7 个问题都在 `## Answer` 里有答案，附测量数据。
- [ ] 给出 ticket 02 要用的参数：`FOLLOW_ON_TIMEOUT`、`vad_model`、是否填 `language_hints`、保活方式、空稿怎么过滤。
- [ ] 如果测出来百炼做不到 Soniox 的三条规格（比如出终稿要 6 秒以上，或者咳嗽必出空稿），在 Answer 里写明，并回到 grilling，不直接开始 02。

## Comments

### 2026-10-02：key 已填，做了试调握手

用户的 `DASHSCOPE_API_KEY` 已经填进 `.env`，是 `sk-ws-` 开头的新格式。用老域名、不带 WorkspaceId 的握手如下：

- **北京** `dashscope.aliyuncs.com`：
  - 模型列表 200；
  - `qwen-audio-3.1-asr-flash-streaming`、`qwen-audio-3.0-asr-flash-streaming`、`fun-asr-realtime` 三个模型都是 `run-task` → `task-started`（约 0.3 s）→ `finish-task` → `task-finished`，`output` 为空。
- **新加坡** `dashscope-intl.aliyuncs.com`：模型列表 401 `InvalidApiKey`，WebSocket 握手 HTTP 401。「北京被拒才试新加坡」反过来也成立：可以靠 401 判断地域。
- **不存在的模型**：`task-started` 之前就返回 `task-failed`，`error_code=ModelNotFound`。
- **还没测**：
  - 「存在但没开通」的错误码。这个 key 下三个模型都已开通，没法测。
  - 不发音频的握手是否计费，要等控制台账单更新后再看。

`run-task` 的报文：`header: {action: run-task, task_id: <32 位 hex>, streaming: duplex}`，`payload: {task_group: audio, task: asr, function: recognition, model, parameters: {format: pcm, sample_rate: 16000}, input: {}}`。

### 2026-10-02：录音已备好

`.scratch/bailian-stt/prototype/audio/` 下的文件。原始录音是用户录的 m4a（AAC，48 kHz 立体声），已用 ffmpeg 转成 16 kHz、单声道、s16 的 WAV。测量用 WAV：

| 文件 | 内容 | 来源 | 时长 |
|---|---|---|---|
| `01.wav` | 一句中文、一句日语、一句中日混说、一句带角色名的话 | 用户录音 | 16.06 s |
| `02.wav` | 两句话，中间停顿约 1 秒 | 用户录音 | 6.98 s |
| `03.wav` | 咳嗽、清嗓、「嗯……」 | 用户录音，峰值 -4.7 dB | 9.07 s |
| `04-silence.wav` | 纯数字静音 | 合成 | 35 s |
| `05-room-noise.wav` | 很轻的粉红噪声，平均 -64.7 dB，模拟真实麦克风的底噪 | 合成 | 35 s |

- **静音保活（问题 5）**：两种静音都测。浏览器麦克风静音时推过来的是纯零还是底噪，取决于实现。
- **各句的起止时刻**：录音里没有标注，测量时要先从波形（或用 ffmpeg `silencedetect`）找出来，作为算「说完到出终稿」的起点。
- 整个目录已加进 `.gitignore`。
