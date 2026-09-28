# 03: 参考资料来源列表，作品资料改名

**What to build:** 参考资料的三个来源（剧情、角色资料、作品资料）改成一张列表。每个来源自带四样东西：
- kind；
- 提示词里的标题；
- 给角色的那行使用说明；
- 按查询向量为某位角色检索候选。

`Retrieval` 接收这张列表，拼提示词只是遍历拼接，自由函数 `rank_references` 消失。一个工厂函数接收数据库路径、embedder、角色和世界设定（可以没有），返回可以一次性关闭的来源列表；`assembly` 和 CLI 的 `eval rerank` 共用它，缺向量的警告也由它统一发出。

同时按 `CONTEXT.md` 的「作品资料 (Work Facts)」改名：
- 代码里的 world index 改为作品资料的名字，kind 从 `"world"` 改为 `"work"`；`World` 本身不动。
- 提示词标题「资料」改为「作品资料」，Jev 判断说明里的措辞跟着改。

回顾经过和想起记忆不进列表。回顾经过直接调用作品资料的来源，按演出、唱片过滤；`recall_story` 工具仍然只查剧情。背景见 `../spec.md`。

**Blocked by:** 01（要用它的基线做对比，两者也都改 `eval rerank`）、02（来源建在向量化文本集的 adapter 上）

**Status:** ready-for-agent

- [ ] 加一个参考资料来源只需要在一处写它的检索、标题和使用说明，外加在工厂函数里登记。
- [ ] `eval rerank` 通过同一个来源列表拿到候选和分数，不再手工构造剧情库和各个索引。
- [ ] 回合的提示词里，「作品资料」和「角色资料」两个标题各自对应正确的条目；经由回合的测试补上这条断言。
- [ ] 回顾经过照样把相关的演出和唱片与剧情一起带上；`recall_story` 仍然只查剧情。
- [ ] `test_world_retrieval`、`test_retrieval`、`test_recall_story`、`test_rerank_eval` 只改名字和标题文字，全部通过。
- [ ] 三份 README 里提到「资料」标题或 world index 的地方，同步改为作品资料。
- [ ] 用真实服务跑一次 `eval rerank`，和 01 的基线对比，结果记到本 ticket 的 Comments。
- [ ] 用两位角色做一次真实对话，问到歌曲、唱片、演出，确认会照作品资料回答，也不和角色资料混淆；结果记到本 ticket 的 Comments。
