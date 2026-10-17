# 15: 生图的运行记录和花费

**What to build:** 管理者在看板上看得到生图：每次生成都是一条「生图」调用，挂在那个回合下面，带张数和错误原因，并按单价估出花费。官方 V5 Curated 有预设单价，中转的单价由管理者自己填。规格见 `../spec.md`「一张照片的生命周期」的计费一条和「单价」一节。

**Blocked by:** 14

**Status:** ready-for-agent

- [ ] **服务名**：运行记录加 `image`，中文「生图」，后端的服务名和前端看板、文案都要改。
- [ ] **调用**：每次真的发出去的生图请求都记一条调用，挂在那个回合的运行记录下面（同一个 `record_id`），回合已经结束也一样。
  - 只有确实拿到了图（包括尺寸不对的错误图）才记 1 张用量；HTTP 报错、超时都记 0 张。
  - 失败的带上错误原因。
- [ ] **单位**：计量单位新加「张」（`images`），单价按每张填，不按每百万。单价表、后台设单价的接口和前端的单位文案都要加。
- [ ] **预设单价**：官方 `nai-diffusion-5-curated` 每张 0.036 美元，查价日期 2026-10-17。中转没有预设，没填就和现有没设单价的服务一样显示。
- [ ] 自带 key 的调用照现有规则只统计用量、不计价（自带生图在 20 接上以后自然生效）。
- [ ] **测试**：生图调用挂在回合下、张数和错误、预设单价算出的花费、看板上的服务名和单位。先例是 `test_activity_records.py`、`test_cost_estimate.py`、`test_service_call_models.py`，前端是 `dashboard` 相关的测试。
- [ ] `uv run pytest`、`uv run pyright`、`npm test`、`npm run typecheck` 全部通过。

## Comments

**14 留下的（2026-10-17）。** 生图客户端是 `backend/src/eidolon/image_generation.py` 的 `ImageGenerator.generate`，`photos.Photos._generate` 调它；现在还没有记任何运行记录。`Photos.begin` 是在回合里调的（`engine._begin_photo`），要挂到那个回合的 `record_id` 下面，得在 `begin` 时把回合的运行记录带进去（照 `activity.timed` 和 `recording.current()` 的做法），因为生成在回合结束以后才完。
