# 03: 后台模型的思考强度和额外请求参数

**What to build:** 部署者可以在 `.env` 或后台给后台模型（后台叫「记忆模型」）设一档思考强度、填一段额外请求参数 JSON。保存时检查带着这一档把工具调用走完两轮，不支持就当场报出是哪一档、服务方怎么说。这张票把「设置 → 适配器 → 请求体」整条链路先打通，后面几张票复用它。背景见 `../spec.md`「模型设置」「按协议发什么」「额外请求参数」「保存时的检查」。

**Blocked by:** 01（检查走两轮在 01 里）

**Status:** ready-for-agent

**难度：高。** 一张票穿过所有层：模型设置、三个适配器、`.env` 解析、实时配置的存取、后台接口、后台表单和文案、检查与报错。额外请求参数和强度共用这条链路，所以放在一起。

## 已定的设计（详见 spec）

- 一个模型的设置加两项：思考强度（八档之一或不设置）、额外请求参数（JSON 对象或不设置）。
- 三种协议按 spec 里的表发；Anthropic 没有 minimal。Responses 在 minimal 到 max 时带 `include:["reasoning.encrypted_content"]`。
- 额外请求参数深合并、最后合并；拒绝 `model`、`stream`、`stream_options`、`messages`、`input`、`instructions`、`system`、`tools`、`tool_choice`。校验写成一份，05 要复用。
- `.env`：`BACKGROUND_LLM_REASONING_EFFORT`、`BACKGROUND_LLM_EXTRA_BODY`；同时给对话模型加 `CHAT_LLM_REASONING_EFFORT`、`CHAT_LLM_EXTRA_BODY`（这张票里对话模型只有一项强度，04 再分出通话）。不在槽位之间回退。
- 后台表单：档位用下拉框，中文名后面括号写原值；选 Anthropic 时不列「极低」。额外请求参数用多行输入框。提示：用 JSON 控制思考时强度选「不设置」；选「高」及以上时输出上限留空或设宽裕。
- 检查被拒时，报错先写「思考强度『<档>』被服务拒绝：」，后面接服务方原文；截断时保证原文开头完整。

## 验收

- [ ] 适配器测试：三种协议每一档的请求体（含 Anthropic 的 `display:"omitted"`、Responses 的 `include`）；不设置时请求体和现在一样；额外参数深合并并覆盖我们生成的思考参数。
- [ ] 额外参数校验测试：不是对象、带禁用键时拒绝并说明是哪个键；思考相关的键允许。
- [ ] `.env` 测试：两个槽位的新变量各自生效，非法档位、非法 JSON 启动时报错。
- [ ] 后台配置测试：PUT 保存强度和额外参数；不改时回退 `.env`；非法额外参数返回 422 和原因；检查失败返回 422，报错带强度前缀。
- [ ] 前端 `adminConfig` 纯函数测试：新字段的行、表单、改动校验（含 JSON 校验和 Anthropic 不列「极低」）。
- [ ] 实测：用线上的 DeepSeek，把后台模型分别设成「关闭」和「高」保存成功；在本地构建版的后台页面上看一眼表单和提示。
- [ ] `backend/` 下 `pytest`、`frontend/` 下 `npm test` 全部通过，`ruff`、`pyright`、`tsc` 没有新的报错。
