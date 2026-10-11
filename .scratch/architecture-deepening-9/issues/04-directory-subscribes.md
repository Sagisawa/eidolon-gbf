# 04: 对话列表订阅同一个 LiveConversation

**What to build:** 对话列表照旧这样：
- 通话中那位角色的一行显示「正在呼叫」或计时；
- 隐藏了那位角色时，那一行照旧留着；
- 通话中点别的角色、进设置或记忆、回列表，先问一句会不会挂断；
- 不在通话中时离开，不被拦下。

现在对话页每次转换都在 effect 里把通话状态抄一份给列表，列表读的是副本。改成对话页把 LiveConversation 交给列表一次，列表自己订阅同一份快照，`leave()` 在点击的那一刻读它。这是去掉一份重复的状态，不算修 bug：「`leave()` 读到旧值」实际几乎碰不到。

背景见 `../spec.md`（「对话列表订阅同一份快照」）。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

## 已定的设计（2026-10-11 grilling，详见 spec）

- 对话页建好 LiveConversation 后交给列表的外壳（Directory），离开时收回。这一步和建它、dispose 它放在同一个 effect 里。
- LiveConversation 对外说明它是哪位角色的对话。
- Directory 自己订阅交来的那个 LiveConversation：列表那一行、隐藏时保留通话中的角色，都从快照里进行中的通话算出来。
- 删掉 Directory 上的 `setCall`，以及对话页里抄状态的那段 effect。
- 不由 Directory 来建 LiveConversation。
- 只改对话页交出对象的那一处和 Directory，不碰 02、03 改的地方。
- 和 01 都会改对话页里建 LiveConversation 的那段 effect，合并时手工对一下。

## 验收

- [ ] `liveConversation.test.ts` 补一条：LiveConversation 说明的角色，就是建它时给的那位。
- [ ] Directory 上没有 `setCall`，对话页没有抄通话状态的 effect。
- [ ] `vitest`、`tsc`、`sh scripts/check-discipline.sh` 通过。
- [ ] 人工验收清单写进 Comments：在构建版前端、电脑宽度下核对：
  - 拨号时列表那一行显示「正在呼叫」，接通后计时；
  - 隐藏通话中的那位角色，那一行照旧留着；
  - 通话中点别的角色，先弹确认；取消后通话照旧，确认后挂断并切过去，列表那一行恢复成平常的样子；
  - 不在通话中时点别的角色，直接切过去；
  - 窄屏下通话中点返回，同样先弹确认。

## Comments
