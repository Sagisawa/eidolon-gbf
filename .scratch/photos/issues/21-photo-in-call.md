# 21: 通话里的照片

**What to build:** 通话里说「拍一张给我看」，和文字回合一样能收到照片。电脑上台词卡上方出一张小卡；手机上出一颗胶囊，点开能放大。生成中写「正在拍照…」，失败时写明原因。把通话层收起、在看别的页面时，外壳顶上的通话条会提示「新照片」。她先挂断、照片后到的，照样挂进对话记录，回到对话就能看到。规格见 `../spec.md`「接口和事件」的通话一条、「前端」的通话层一条，以及 ADR-0018，呈现照 `12-presentation-prototype.md` 的 Answer。

**Blocked by:** 16, 18

**Status:** ready-for-agent

- [ ] **后端**：
  - 通话里的回合照样能发照片（引擎是同一个，标签不进语音和字幕）。
  - RTVI 服务器消息加 `photo`，带 `reply` 编号：标签写完时推 `pending`；生成完、通话还连着时推 `ready` 或 `failed`（带 `reason`）。
  - 次数用完时推 `photos-used-up`。
- [ ] **电脑**（通话层只盖住对话栏）：
  - 台词卡上方一张毛玻璃小卡（`bg-white/12`、`backdrop-blur-md`、`rounded-2xl`、`p-1.5`），里面是 128px 宽的照片，点开放大。
  - 生成中是同样大小的占位，加转圈和「正在拍照…」；失败时写「照片没发出来 · {原因}」。
  - 卡一直留着，这通电话里有了下一张就换成下一张。
- [ ] **手机**（铺满整屏）：台词卡上方只出一颗毛玻璃胶囊。生成中是「正在拍照…」加转圈；到了是相机图标加「发来一张照片 · 点开看」，点了放大；失败是「照片没发出来 · {原因}」。
- [ ] 小卡和胶囊都放在台词卡和底栏上面，不挡她的脸，有没有立绘都一样。
- [ ] **收起时到了照片**：只有外壳顶上那条通话条在状态后面加一个相机图标和「新照片」，展开通话层或打开她的对话页后消失。她对话页页首下面那条通话条不提示。
- [ ] **挂断以后**：
  - 她挂断后才到的照片不上结束卡，照常挂进记录。前端回到对话时靠记录和轮询拿到结果。
  - 通话里收到 `photos-used-up` 时，胶囊进对话记录，通话层上不另外提示。
- [ ] 通话里的照片也同步进对话记录（对话页开着时能看到）。
- [ ] **`DESIGN.md`**：补上通话层电脑和手机两种，以及外壳顶上通话条的「新照片」。
- [ ] **测试**：
  - 用 `test_voice_call.py` 的夹具和 `browser.py` 的 RTVI 客户端：`photo` 的三种状态、`photos-used-up`、挂断后才到的照片挂进记录。
  - 前端：通话事件怎么并进对话状态、「新照片」什么时候亮和灭、结束卡不带照片（先例是 `callEnd.test.ts`、`conversationLog.test.ts`）。
- [ ] **验收**：按 `docs/agents/local-acceptance.md` 在本地构建版上用 Playwright，假麦克风打电话，生图走假服务。电脑看小卡，手机看胶囊；收起时看「新照片」；挂断后才到的照片。
- [ ] `uv run pytest`、`uv run pyright`、`npm test`、`npm run typecheck` 全部通过。

## Comments

**14 留下的（2026-10-17）。** 通话里现在没有照片资格：`engine.ConversationEngine._could_send_photo` 要求 `in_call is None`。去掉这个条件以后，`PhotoPending` 会照 `asdict` 发到 RTVI（`call.py` 的 `_reply_events`），`done` 已经改用 `TurnDone.shown()`。前端 `CallEvent` 已经包含 `photo` 事件的类型（来自 `TurnEvent`），`onCallEvent` 现在落到 `default`。

**票 15 留下的（2026-10-17）。** 照片的生图调用记在开始它的那个回合下：`Photos.begin` 取当时的 `activity.recording()`，生成时在它下面计时。通话里的回合在 `call.py` 的 `with turn.current()` 里跑，`begin` 要在这个上下文里调，否则会记到通话或者单独一条。`ActivityLog.record` 已经改成：回合记录已经写进库就直接挂到它的 id 下，通话里结束了但还没随通话写进库的回合就先挂在它身上、随通话一起写；所以挂断以后才出来的照片也挂在那个回合下。

**票 16 留下的（2026-10-17）。** 失败原因是 `store.PhotoFailure`，通话层的「照片没发出来 · {原因}」可以用 `lib/photoFailure.ts` 的 `photoFailureNote(reason).reason` 拿那半句。

**票 22 留下的（2026-10-17）。** 列表的最后一句（`Store._last`）现在连照片表，最后一条回复的照片是「发出来了」时，`/api/conversations/latest` 和 `/api/conversations` 的 `last_message` 带 `photo: true`，前端在最后一句前加相机。通话里的照片只要同样经 `add_turn` 的 `photo` 写进照片表、挂在她那条回复上，列表就会自己带上相机，不用另做；挂断后才到的照片也一样（落库以后列表下次读就有）。测试里造「发出来 / 生图服务报错 / 一直在生成」三种照片的小工具在 `tests/test_past_conversations.py`（`photographing`、`with_photo`、`in_turn`、`broken`、`taking_its_time`），要用可以照搬。

**票 17 留下的（2026-10-17）。** 通话里的照片只要走 `Photos.begin`，清洗、改写表、黑名单和运行记录里剥掉的类别都自动有，不用另做。

**票 18 留下的（2026-10-17）。** 次数和文字回合共用，按人计，不用另做：`Photos.eligibility(character, user_id)` 和 `Photos.begin(character, tag, user_id)` 都按 `conversation.user_id` 算。通话里照片资格还是 None（`engine._photo_eligibility` 里 `in_call is not None` 就返回 None），去掉这个条件就会开始查次数。用完时引擎在 `TurnDone` 之前产出 `PhotosUsedUp(retry_at)`（`type: "photos-used-up"`），文字回合经 SSE 发出去；通话要经 RTVI 发，前端 `onCallEvent` 现在会把它落到 `default`（只动立绘），要加一个 `case "photos-used-up"` 走 `applyTurnEvent(event, { stand })`，胶囊就会挂在这回合她那条回复后面（`conversationLog` 已经处理，`done` 时带到记录里的那条上）。规格说通话层上不另外提示。

**票 20 留下的（2026-10-18）。** 通话的 offer 照旧带全部自带密钥，`OwnKeysInput.image` 已经解析成 `BroughtKeys.image`（`ImageSettings`，只有四项，同时数和画风由 `OwnImageService.generator` 补），但通话里的回合还没用它：文字回合是 `app.text_turn` 调 `engine.turn(..., own_image=brought.image)`，通话里 `call.py` 调 `self._engine.turn(...)` 时也要传进去（`Calls.start` 拿到的 `brought` 要存到通话上，或者放进 `CallKeys`）。传了以后 `Photos.eligibility` / `begin` 自然按自带的走：不查次数、`take(..., exempt=True)`、失败记 `own_key_failed`。测试照 `tests/test_own_image.py` 的 `MINE` 和 `photo_uses`。

