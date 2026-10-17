# 她发照片

Label: wayfinder:map

## Destination

一份可以直接拆票实现的规格（`.scratch/photos/spec.md`）：制作人在文字回合或通话里明确要她发照片时，她在回复里发来一张拍到她本人的照片，由 NovelAI 生成；NovelAI 官方接入点和中转都能接，部署者配、用户也能自带。所需的决定全部定下，交给 `/to-spec` → `/to-tickets`。

## Notes

- 术语以 `GLOSSARY.md` 为准，定图时新加了「照片」，自带密钥能带的服务里加了「生图」。说回合、对话、通话，不说消息、聊天、会话；照片不是立绘，也不是插画。
- 每张拍板类（grilling）票都要调用 grilling 和 domain-modeling 两个 skill。原型票调用 prototype，原型放在 `prototype/<name>` 分支。调研票由子代理调用 research skill，结论放在 `research/<name>` 分支，票里留指针。前端相关的先读 `frontend/AGENTS.md` 的「shadcn 纪律」，视觉以 `DESIGN.md` 为准。
- 这张地图只做计划，交付物是规格，不是实现。地图和设计文档都放在 `feat/photos` 分支，不进 main。
- 对齐 NovelAI 最新的官方文档、模型和库：凡是写进规格的接口细节，都以调研票查到的官方现状为准，不凭记忆。
- 定图时已定（2026-10-17 的 grilling）：
  - 目的地是一份规格；文字回合和通话都在这张地图里定。
  - 谁出钱：部署者在后台配（官方或中转），用户也能自带（和其他自带密钥一样只存在浏览器里）。如果调研查出 NovelAI 条款不允许一个订阅给公开服务用，回头重议。
  - 严格只出全年龄内容，写死、不做开关；越界的要求她以自己的口吻拒绝。
  - 照片只拍她本人（自拍或别人帮她拍），背景、服装、动作随情境变。
  - 用户手上只有一个中转（地址和 key），没有官方订阅：官方接入点只能按文档对齐，实测走中转。
- 定图时查到的现状：
  - 文字回合和通话走同一个 `Engine.turn`（`engine.py`），已有工具调用循环，目前只有 `recall_story` 一个工具，`MAX_TOOL_ROUNDS = 1`；自带 LLM 本来就要求支持工具调用。她结束对话由判断模型决定，不是工具。
  - 文字回合用 SSE 推 `user`/`delta`/`done`/`error`；通话里同样的事件经 WebRTC 数据通道（RTVI server message）推给前端，另有 `segment-playing`、`emotion`、`ended`。
  - 消息表（`messages`）和对话事件表都没有附件字段。运行时没有存用户内容的地方：存储桶是公开读的，只放事先从命令行上传的素材；头像和背景图从本地磁盘读。前端 CSP 的 `img-src` 只放行同源和存储桶。
  - 角色配置（`characters.toml`）没有结构化的外貌字段，外貌只散在角色资料的文字里；存储桶里有每位角色的 Spine 立绘和衣装缩略图。
  - 新加一项服务要动：`config.py`（设置、`ProxiedService`）、`live_config.py`（后台配置项）、`activity.py`（运行记录的服务名）、`prices.py`（单价）、前端 `adminConfig.ts`；能自带的还要动 `own_keys.py` 和 `localOwnKeys.ts`。
  - 限额只有每小时的回合数和通话次数，没有按天的；花费只对部署者的 key 估算，按 `service_calls` 记。

## Decisions so far

- [调研：NovelAI 官方图像 API 现状](issues/01-novelai-api-research.md)：最新 V5（Curated/Full），V5 没有角色参考图；Opus 免费有条件且 V5 扣用量条；一个 token 同时一张；条款禁止公众共用订阅，自带 token 可以；官方不过滤内容；不用社区库，直接发 HTTP。
- [调研：NovelAI 中转的常见协议](issues/02-relay-research.md)：四种形态（原样转发、OpenAI images、OpenAI chat、自定义），支持前两种就能覆盖绝大多数；参数常被静默忽略、200 也可能是错误图、超时不重试。

## Not yet specified

- **照片在文字回合和通话里怎么呈现**：生成中的占位（她说「等一下」？气泡里的进度？）、照片在对话记录里的样子和点开放大、通话层上怎么显示、收起成通话条时怎么提示；通话中照片比她的话晚到十几秒，怎么记进那个回合。等「怎么触发、谁来写提示词」和「失败、限额与计费」定了再变成一张原型票。

## Out of scope

- 多人同框（组合伙伴等别的偶像一起出现在照片里）：第一版只拍她本人。
- 她不经要求主动发照片。
- 用户给她发图、让模型看图。
- 对已发的照片改图、重拍、换姿势。
- 照片导出、做成分享图。
