# 04: 文字回合也带 `own_keys`，旧页面被拒绝

**What to build:** 「带来的 key」在线上只有一种形状。文字回合的请求体从顶层的 `own_llm` 改成和通话一样的 `own_keys`（只带 LLM），后端的文字回合和通话共用同一处解析。部署那一刻还开着的旧页面再发 `own_llm`，后端回 422 并提示刷新，不会悄悄改用部署者的 key、还计入限额。

前端的自带密钥 module 同时收齐：自带密钥的类型、LLM 协议和语音识别服务商的取值列表都只有一份（设置页的选项从这里来），一次文字回合要带的 `own_keys` 由它拼好；请求函数的文件改为从它引用类型，两者不再互相引用。

对用户：填了 LLM key 照常聊天，用的是自己的 LLM、不计入限额；存了语音 key 也不随文字回合发出去。背景见 `../spec.md`（「线上：带来的 key 只有一种形状」「前端：自带密钥 module」）。

**Blocked by:** 01（前端的请求都走同一个请求函数）

**Status:** ready-for-agent

## 已定的设计（2026-10-11 grilling，详见 spec）

- 文字回合请求体：`{ text, own_keys?: { llm? } }`；`own_keys` 和通话 offer 里的是同一种结构（`OwnKeysInput`）。浏览器只带这次用得上的：文字回合只带 LLM，没存就不带 `own_keys`。
- 后端文字回合经 `OwnKeysInput.brought()` 得到 `BroughtKeys`，删掉另外拼 `BroughtKeys` 的那一处；即使收到语音 key 也不用。
- 请求体里有旧字段 `own_llm` 时回 422，原因「页面已经更新，请刷新后再发」，没有跑任何 LLM、不计入限额。注明是过渡代码、以后可以删。
- `sendTurn` 照旧收 userId、每次现读，读出来的由自带密钥 module 拼好。
- 前后端之间的枚举不做代码生成；前端那份注明跟后端同步。

## 验收

- [ ] 后端 HTTP 测试（仿 `test_own_llm.py`、`test_rate_limit.py`）：带 `own_keys: {llm}` 的文字回合跑在自带的 LLM 上、不计入限额；不带的跑在部署者的上、计入。测试辅助函数 `send_turn` 改发新形状。
- [ ] 后端 HTTP 测试：带旧字段 `own_llm` 的文字回合回 422，原因是要刷新；没有调用任何 LLM，没有计入限额。
- [ ] 前端自带密钥 module 的测试（仿 `localOwnKeys.test.ts`）：文字回合只带 LLM；没存 LLM 时不带；存了语音 key 也不带。
- [ ] 前端请求函数的测试（仿 `api.test.ts`）：`sendTurn` 的请求体是 `own_keys` 的新形状。
- [ ] 前端里语音识别服务商、LLM 协议的取值各只写一份；请求函数的文件和自带密钥 module 不再互相引用。
- [ ] 后端 `pytest`、`ruff`、`pyright`，前端 `vitest`、`tsc`、`sh scripts/check-discipline.sh` 通过。
- [ ] 人工验收清单写进 Comments（例如：填自带 LLM 后发文字回合，看板记为用自带密钥的回合、限额不减；删掉后发，记为部署者的；用改动前的前端发一次，看到要刷新的提示）。
