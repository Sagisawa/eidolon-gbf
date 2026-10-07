# 03: 租约自带「这是哪个模型」和计量

**What to build:** 部署者的客户端和它的身份（settings）成对存放、成对交出：`Swappable` 存「客户端 + settings」，`LiveConfig.lease()` 交出的扮演、记忆、情绪判断的客户端都已按自己的 settings 套上计量，判断阈值也按租约里的判断模型算；检索的判断模型每问一次取一次租约，同样处理。用户自带的 LLM 由 `OwnKeys` 在造客户端时套上计量。`turn_llms` 删掉，`Admissions` 不再读部署者的模型、不再重读自带 LLM 的描述。

对用户和管理者的变化：运行记录里每次服务调用记的模型，始终是实际作答的那个，即使后台恰好在回合开始时换了模型；判断用的阈值始终是实际作答的判断模型的。背景见 `../spec.md`。

**Blocked by:** 01（测试经 `FakeServiceClients` 走生产路径）

**Status:** ready-for-agent

## 已定的设计（2026-10-07 grilling，详见 spec）

- **`Swappable`**：存「客户端 + settings」；`replace(client, settings)` 在同一把锁下一起换；`Lease` 交出这一对。关闭旧客户端的规则不变。
- **`LiveConfig.lease()`**：
  - 扮演、记忆的客户端按租约里的 `LLMSettings` 套计量；记忆跟随扮演模型时（`chat.again()`）用扮演模型的 settings，服务名记为 `memory_llm`。
  - 情绪判断的 origin 和情绪阈值按判断模型租约里的 `JudgeSettings` 算，阈值覆盖照旧叠上（按 02 的绑定规则）；超时照旧读生效配置。
  - `activity` 改为必填。
- **`LiveRetrievalJudge`**：每问一次取一次租约，origin 和阈值都按租约里的 settings 算。
- **试调不计量**：`check_chat_llm` / `try_judge_model` 用 `Swappable` 里的裸客户端。
- **自带 LLM**：`OwnKeys._llms` 造 `_OwnLLM` 时按 key 记录的 `base_url` / `model` 套计量（`own_key=True`），扮演和记忆各记各的服务名。`OwnKeys` 多收一个 `ActivityLog`。`TurnKeys` / `CallKeys` 带上是否自带 LLM，`Admission.own_llm` 由它给出。
- **删掉** `activity.turn_llms`、`Admissions` 的 `deployer_llms` 参数、`_admit` 里重读 `describe()` 的那一步。放行的顺序变为：取 key → 开运行记录 → 占次数。
- **不进租约**：历史回合数、重排阈值、限额照旧按回合读；单次通话上限照旧在接通时读。

## 验收

- [ ] **按 TDD**：先写下面的用例，看到它们失败，再改实现。
- [ ] 后台换扮演模型后发一个文字回合：服务调用记的是新模型（主机、模型名），实际作答的也是新模型的假件（按 key 区分）。
- [ ] 换模型之前已接通的通话，之后的回合：服务调用记的仍是旧模型，和实际作答的客户端一致。
- [ ] 后台把判断模型换到别的 family：之后的检索判断记新模型、按新模型的阈值判定；之前已接通的通话，情绪判断仍记旧模型、按旧阈值。
- [ ] 自带 LLM 的回合和通话：服务调用记为自带，记用户的主机和模型。
- [ ] 后台试调新模型（保存成功或失败）都不留服务调用。
- [ ] `turn_llms` 不存在；`Admissions` 构造时只收限额、运行记录和自带密钥；`test_admission.py` 里靠 `deployer_models_broken` 的两个用例随「准备」这一步一起删掉，其余用例不改断言就通过。
- [ ] `backend/` 下 `pytest` 全部通过，`ruff` 和 `pyright` 没有新的报错；经 HTTP 的测试不改断言就能通过，如有必须改的，在 Comments 写明原因。
- [ ] **人工验收（留给用户）**：本地起服务：
  - 发几个文字回合、打一通电话，看板的服务调用里扮演、记忆、判断模型记的是生效配置里的模型；
  - 通话中在后台换扮演模型或判断模型，这通电话剩下的回合仍记旧模型，挂断后新拨的一通记新模型；
  - 配了自带 LLM 的用户，服务调用标为自带，模型是他填的那个。

## Comments
