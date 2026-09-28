# 01: rerank 校准能标注作品资料，并跑出基线

**What to build:** 让 `eidolon eval rerank` 如实反映线上回合的行为：线上是剧情、角色资料、作品资料三类参考资料一起重排、用同一个阈值筛。现在的校准集没法标注作品资料，所以作品资料的候选全被判为「不相关」，校准结果失真。修好以后跑一次，得到一条可信的基线，供 03 改名和改提示词之后对比。背景见 `../spec.md`，决定的来由见 `../grilling-notes.md`。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 校准集的问题类型增加作品资料一类，标签是作品资料条目的标题。
- [ ] 作品资料的候选按标签判定为相关、可放可不放或不相关。
- [ ] kind 写错、作品资料问题引用了 `world.json` 里没有的标题时，命令报出清楚的中文错误。
- [ ] 报告分为两组：「参考资料」包括剧情、角色资料、作品资料，用 references 阈值；「记忆」用 memories 阈值。旧的「剧情与角色资料」标题不再出现。
- [ ] 从 `characters/world.json` 起草约 6 条作品资料的校准问题（歌曲、唱片、演出日各 2 条），写上 relevant 和 acceptable，交人工审阅后提交。
- [ ] `test_rerank_eval` 补上作品资料的用例和上面的错误用例，经由 `evaluate` 和报告断言。
- [ ] 用真实服务跑一次 `eval rerank`，把基线（参考资料和记忆两组的分布、阈值命中）记到本 ticket 的 Comments。只报告结果，不改阈值。
