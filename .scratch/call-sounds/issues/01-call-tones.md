# 01: 铃声、接通音、挂断音

**What to build:** 让拨号、接通、结束各有对应的声音。背景见 `../spec.md`，术语见 `CONTEXT.md` 的「铃声」「接通音」「挂断音」。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## 素材（都提交进仓库，放在 `frontend/public/sounds/`，这个目录现在还不存在）

- `ringback.mp3`：取自仓库根目录的 `打电话铃声.mp3`（37 秒，48kHz 立体声），用 ffmpeg 转成单声道、约 64kbps。转好后删掉根目录的原文件。用户已确认这段铃声可以公开分发。
- `connect.ogg`：Kenney「Interface Sounds」里的 `Audio/confirmation_001.ogg`（CC0，https://kenney.nl/assets/interface-sounds ，zip：https://kenney.nl/media/pages/assets/interface-sounds/fa43c1dd4d-1677589452/kenney_interface-sounds.zip ）。
- `hang-up.mp3`：Felfa 的「busy signal_europe」（CC0，https://freesound.org/people/Felfa/sounds/178821/ ），使用免登录的预览版 https://cdn.freesound.org/previews/178/178821_2103589-hq.mp3 （1.6 秒，三声 425Hz）。
- 在 `frontend/public/sounds/` 下放一个简短的 `CREDITS.md`，写明后两个文件的来源和 CC0 许可。

## 规则

- **铃声**：
  - 用户点下开始通话或重新拨打时立即循环播放，浏览器弹出麦克风权限框时也照样响；
  - 一接通就停，不刻意多响一会儿，不推迟接通；
  - 通话在接通前结束时也要停，包括取消拨号、麦克风被拒、超出限额、自带密钥调用失败、没能接通。
- **接通音**：进入 `connected` 时播放一次。
- **挂断音**：
  - 只要铃声响过，通话进入 `ended` 时就播放一次。实际上就是每一种结束方式都播，包括用户自己挂断、拨号时取消、后端告知结束、连接断开，以及上面列出的各种接通前失败；
  - 通话结束后，同一个 `ended` 状态重复渲染时不能重复播放；
  - 离开对话页时来不及播放，不用强求。
- 三种音效都**不受**「只看文字」（`textOnly`）和收起通话层的影响，也不套用电话质感。
- 播放是由用户的点击触发的，一般不会被浏览器的自动播放策略拦下；万一 `play()` 被拒绝，吞掉错误即可，不影响通话本身。

## 实现提示

- 通话状态机在 `frontend/src/lib/liveConversation.ts`，状态依次是 `idle → dialing → connected → ended`。音效可以根据状态的切换来驱动，最好做成一个小 module（例如 `lib/callTones.ts`），接收"状态从 A 变成 B"，决定播放或停止什么，方便单测。
- 播放本身放在 `ConversationView.tsx` 里，或者做成一个注入的 port。`liveConversation.ts` 本身不直接接触 `Audio`。

## 验收

- [ ] 三个音效文件和 `CREDITS.md` 已提交，根目录的 `打电话铃声.mp3` 已删除。
- [ ] 单测覆盖以下切换：idle→dialing 开始响铃；dialing→connected 停止铃声并播放接通音；dialing→ended、connected→ended 停止铃声并播放挂断音；ended→idle 以及同一状态重复渲染时什么都不做；重新拨打会再次响铃。
- [ ] 在真实应用里走一遍：拨号时听到铃声，接通后听到接通音，挂断后听到挂断音；开着「只看文字」时音效照常播放。
- [ ] `npm test`、`npm run lint`、类型检查通过。
