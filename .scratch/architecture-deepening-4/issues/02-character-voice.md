# 02: 角色的声音交给 LiveConversation

**What to build:** 通话里角色的声音（`CharacterVoice`）改由 `LiveConversation`（`frontend/src/lib/liveConversation.ts`）经一个声音 port 告诉：拨号时（带电话质感，在用户这次点击里）、她的音轨到了、切换只看文字、离开这一页。快照给出 `canDial`、`canStartNew`，页面的电话键和「开新对话」直接读它们。对话页（`ConversationView.tsx`）不再替声音做判断，删掉 `useCharacterVoice.ts`。背景和取舍见 `../spec-02-character-voice.md`。

**Blocked by:** 01（`01-stale-call-events.md`）：音轨要过 01 设的闸，01 的表驱动测试要加一行。

**Status:** ready-for-agent

## 已定的设计（2026-10-02 grilling）

- **声音 port**：`Ports.onCharacterAudio` 换成 `voice: { dial(phoneTexture), play(track), setTextOnly(textOnly), dispose() }`。`CharacterVoice` 是真实 adapter，不用改；`attach` 只留在页面。
- **拨号**：`startCall` 守卫通过以后、第一个 `await` 之前，只读一次偏好，同时交给 `voice.dial(phoneTexture)` 和 `ports.startCall`。守卫没通过就不碰声音。`startCall` 的注释写明：必须在用户的点击里同步调用，否则 AudioContext 恢复不了。
- **页面的拨号**只剩 `void live?.startCall()`（电话键和结束页重拨共用）；页面不再 import `loadCallPreferences`，电话质感从此走 `Ports.preferences`。
- **只看文字**：构造时按偏好同步调一次 `voice.setTextOnly`；`toggleTextOnly` 里同步调。删掉 effect。
- **离开这一页**：`LiveConversation.dispose()` 顺带调 `voice.dispose()`。删掉 `useCharacterVoice.ts`，页面只留 `const [voice] = useState(() => new CharacterVoice())`。
- **她的音轨过闸**：01 里原样直通的音轨 handler 也先过闸，闸从此没有例外。更新 01 写在闸附近的注释。
- **快照加 `canDial`、`canStartNew`**，和 `startCall`、`startNewConversation` 的守卫是同一个判断（对话已打开、没有文字回合在进行、不在通话中）。不加 `canSend`。
- **页面**：电话键 `isDisabled={!canDial}`（通话中照旧换成「回到通话」）；菜单 `isDisabled: !canStartNew`，拿掉「没登录」这一条。
- **不动的**：`CharacterVoice` 和它的测试、`useCallTones`、`CallLayer` 和它的 props、`<audio>` 元素、通话 adapter、后端。
- **不改 `CONTEXT.md`，不写 ADR**。

## 验收

- [ ] **按 TDD**：先在 `liveConversation.test.ts` 写下面的测试，看到它们失败，再改实现。
- [ ] 假 Ports 里加 `FakeVoice`，记下每一次调用，替换 `onCharacterAudio: () => {}`。
- [ ] **拨号**：`live.startCall()` 一返回（还没 await），`voice.dial` 已经收到偏好里的电话质感；`ports.startCall` 收到的偏好是同一次读出来的。
- [ ] **守卫没通过时不碰声音**（表驱动）：通话中、文字回合进行中、对话还没打开，`startCall()` 都不调 `voice.dial`。
- [ ] **只看文字**：偏好里已是只看文字时，构造后 `setTextOnly(true)` 已调；`toggleTextOnly()` 当场同步调 `setTextOnly`。
- [ ] **音轨**：当前这一通的音轨交给 `voice.play`。
- [ ] **离开这一页**：`dispose()` 调 `voice.dispose()`。
- [ ] **能不能做**（表驱动）：`canDial`、`canStartNew` 在打开中、已打开、文字回合进行中、拨号中、通话中、结束页、打开失败时的取值。
- [ ] **扩展 01 的表驱动测试**：「迟到的是什么」加一行「她的音轨」，断言 `FakeVoice` 没收到 `play`。不另写测试。
- [ ] `characterVoice.test.ts` 原样通过；现有测试一律原样通过。
- [ ] `useCharacterVoice.ts` 已删除；`ConversationView.tsx` 里不再出现 `loadCallPreferences`、拷贝的拨号守卫和 `failure?.signedOut` 的菜单条件。
- [ ] `frontend/` 下 `npm test` 和 `npm run typecheck` 都通过。
- [ ] **人工验收（留给用户）**：打几通真实电话，用户验过之后再标 `resolved`。
  - 打开电话质感后拨号，听到的是电话里的声音；关掉之后，下一通恢复干净的声音；
  - 通话中切换只看文字，她的声音当场停下或恢复，开不开电话质感都试一次；
  - 偏好里已是只看文字时，打开对话页拨号，一开始就没有她的声音；
  - 在结束页重拨，电话质感照常生效；
  - 收起通话层再展开，声音不受影响。

## Comments
