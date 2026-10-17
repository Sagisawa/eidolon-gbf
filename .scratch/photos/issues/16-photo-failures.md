# 16: 照片没发出来

**What to build:** 生图服务慢了、出错了、给回来的图不对时，她的话照常记下，照片的位置换成一块「照片没发出来」的说明，并写明原因，刷新后也还在。她之后知道那张没发出去，用户问「照片呢」时她能接上。多人同时要照片时按 token 排队，排不上的也按超时失败。规格见 `../spec.md`「生成：生图客户端」的排队和总时限、「一张照片的生命周期」、「前端」的失败一条。

**Blocked by:** 14

**Status:** ready-for-agent

- [ ] **失败原因**：照片表记下失败原因。这张做 `timeout`（包括排队超时）、`service_error`、`bad_image` 三种；`own_key_failed` 在 20 做，`used_up` 在 18 做。
  - 响应解不开、不是正好一张图、宽高不是 832×1216，都算 `bad_image`。
- [ ] **总时限**：从标签写完算起 90 秒，包括排队、生成和下载，写死。超时后晚到的结果丢掉。不自动重试，不给重试按钮。
- [ ] **排队**：按 token 排队，每个 token 有「同时生成几张」的上限，等不到的先进先出，不限队列长度。部署者的上限这张先固定为 1（19 把它做成配置）。排队超时的请求根本没发出去，不记调用。
- [ ] **回复不在了**：回复没写进记录（这回合失败了），或者生成完时对话、账号已经被删，就直接丢掉，不存。她结束对话、用户开了新对话、页面关了，都照样存下、挂上去。
- [ ] **重启**：启动时，照片表里还是「生成中」的行一律改成 `timeout`。
- [ ] **她知道**：历史里没发出去的那张标签加上 `status="failed"`，系统说明里加一句「标了失败的照片对方没收到」。
- [ ] **前端**：同宽的一块矮说明，`bg-foreground/5`，左边 muted 的 `ImageOff`，右边「照片没发出来」，下一行用 Meta 字号写原因：「等太久了」「生图服务出错了」「生成的图不对」。还要支持 `own_key_failed`、`used_up` 的文案（「你的生图密钥没能用」加「去设置自带密钥」、「这一小时的照片用完了」），这样 18、20 只管推原因。图标别名加 `ImageOff`。
- [ ] **`DESIGN.md`**：补上失败说明。
- [ ] **测试**：
  - 假生图服务造出慢、HTTP 报错、尺寸不对、解不开四种情况，看记录里的失败行和原因，刷新后还在。
  - 排队：第二张等第一张，排超 90 秒按超时、请求没发出去。
  - 对话删了以后生成完的不存；重启时「生成中」改成超时。
  - 之后回合的历史里带 `status="failed"`。
  - 前端：失败原因对应的文案。
- [ ] **验收**：本地构建版上用 Playwright，生图走假服务，看各种失败说明。
- [ ] `uv run pytest`、`uv run pyright`、`npm test`、`npm run typecheck` 全部通过。

## Comments

**14 留下的（2026-10-17）。**

- 后端已经在记失败原因：`photos.Photos._generate` 把 `ImageFailed`（`timeout` / `service_error` / `bad_image`，在 `image_generation.py` 里分类）、`asyncio.timeout(PHOTO_TIMEOUT)` 超时和意外异常都记成 `failed` 加原因。90 秒总时限已经包住排队（部署者一侧是一个 `asyncio.Semaphore(1)`），排队超时的请求不会发出去。这些路径都还没有测试。
- 没做：启动时把「生成中」改成 `timeout`；历史里带 `status="failed"`（`engine._prompt` 里 `format_reply(message.segments, tag)`，`Message.photo.status` 现成）；系统说明那一句。
- 回复没写进记录时丢掉已经做了（`engine.turn` 的 `finally` 调 `Photos.dropped`，对话被删时 `Store.finish_photo` 更新不到行就不存），也还没有测试。
- 前端：`PhotoBlock.tsx` 对 `failed` 现在返回 null，失败说明加在那里；失败原因的文案进 `copy.conversation.photo`。图标别名还没有 `ImageOff`。
