# 05: 剧本缓存 module：「拉一个剧本」只写一次，缓存以文件为准

**What to build:** 把 `story_sync` 里三处拉剧本的规则（已汉化不下载、失败结局不下载、已有就跳过、下载、镜像上没有、记 ETag）、`_Cache` 的剧本部分和 `Mirror.download` 的写盘收进一个 `ScriptCache` module。缓存里有没有一个剧本以文件本身为准，让 `docs/deploy.md` 的「删掉缓存里的剧本，下次同步会重新下载」对卡牌、相册、活动都成立。

**Blocked by:** —

**Status:** ready-for-agent

- [ ] 回归测试（卡牌、相册、活动各一个）：删掉缓存里的剧本后再同步，镜像被请求、剧本回到盘上
- [ ] 相册列出而镜像上没有的剧本，相册没变时不再被请求
- [ ] 新增 `eidolon/script_cache.py`：`ScriptCache`，interface 见下
- [ ] `Mirror.download` 改为 `Mirror.script(script, etag)`，不再写盘
- [ ] 剧情库新增 `is_translated(id)`，取代 `story_sync` 里的 `imported_from(x) == "csv"`
- [ ] 三类进度记录（`cards.json` / `albums.json` / `events.json`）只表示「还需不需要再问镜像」；每次同步在本地核对所有已知剧本
- [ ] `docs/deploy.md`：保留删缓存重下的说明，补上强制重试「镜像上没有」的剧本
- [ ] 现有测试不改仍全部通过

## 背景（2026-09-26，架构体检候选 1）

PR #9（剧情同步）合入后的架构体检发现：

1. 「拉一个剧本」在 `_fetch_cards`、`_fetch_albums`、`_walk_event` 里各写了一遍，细节各不相同：只有卡牌会带 ETag 条件请求、处理「没变」；只有相册会先查失败结局；只有活动在「镜像上没有」时停下。相册和活动计 `downloaded` 时总是加一，这只在它们总传 `etag=None` 时才对，没有写在任何地方。
2. 「这个剧本缓存了吗」有两个答案：文件在不在，和进度记录（`_CardState.complete`、相册 ETag、`events.json`）。已拉完且没变的卡、回 304 的相册、不是最新的活动，都只看进度记录，于是删掉缓存里的剧本后，下次同步既不重新下载、也不再导入它（已复现：删 `produce_events/300100401.json` 后再同步，镜像一次也没被请求）。
3. `Mirror.download` 收一个 `Path` 并自己写 `.part` 再替换，缓存布局一半在 `_Cache`，一半在 `Mirror`。
4. 「已汉化」写成 `corpus.imported_from(x) == "csv"`，在 `story_sync` 里出现 8 次，把存储格式当成领域概念。

## Comments

### 决定（2026-09-26，grill-with-docs）

- **承诺**：保留 `docs/deploy.md` 的「删掉缓存里的剧本，下次同步会重新下载」，改代码让它对三类剧情都成立。
- **以文件为准**：剧本文件在，就是缓存了。三类进度记录只回答「还需不需要再问镜像」：没变的卡不再请求剧情 API，但本地核对它列出的剧本、缺的补上；相册回 304 时同样本地核对；走完的活动不再试探新话，但本地核对第 1 到 n 话，最新活动照旧重走。只多本地查文件，网络请求不变。`_CardState.complete` 不再使用，读到时忽略。
- **范围**：只管剧本（文件、`.etag`、`.missing`）。三类进度记录留在 `_Cache`，归候选 2。
- **跳过规则在 ScriptCache 里**：已汉化、失败结局都由 `fetch` 判断，对三类剧情统一适用（卡牌和活动的剧本编号不会匹配失败结局的规则，统一执行无害）。ScriptCache 依赖剧情库和 `story_import.is_failure_ending`。
- **interface**：
  - `fetch(script, *, recheck=False, retry_missing=True) -> 结果`，结果是「已汉化 / 失败结局 / 已有 / 刚下载 / 没变 / 镜像上没有」之一。`recheck`：已有的文件也带 ETag 条件请求一次（卡牌版本变了时）。`retry_missing`：记着「镜像上没有」的剧本也再问一次。
  - `path(script) -> Path | None`：盘上有这个剧本时的路径，给导入用。
  - `downloaded(前缀) -> 剧本列表`：取代活动那边的 glob。
  - `_Cache` 的 `script_path`、`etag`、`set_etag`、`event_scripts` 移走，调用方不再接触 ETag。名字可在实现时微调。
- **镜像上没有**：ScriptCache 在剧本旁记一个 `.missing`，下载成功时清掉。卡牌、活动总是 `retry_missing=True`（卡牌的新剧本常晚几天上镜像；最新活动的下一话每次都要问，404 就是「走到头了」）；相册只在相册变了时 `retry_missing=True`（相册 2024 年后不再更新，缺的基本永远缺）。管理员删掉剧本文件不会留下 `.missing`，所以一定会重拉；想强制重试缺失的剧本就删 `.missing`。
- **Mirror**：`download(script, target, etag)` 改为 `script(script, etag)`，返回新内容和 ETag、没变、或镜像上没有；帧数组的格式检查留在 `Mirror`。落盘、`.part` 原子替换、`.etag` 都归 ScriptCache。
- **剧情库**：新增 `is_translated(id)`；`CONTEXT.md` 新增「汉化版」（已提交）。
- **计数**：调用方按 `fetch` 的结果计入同步报告，报告字段和日志口径不变（`translations_kept` 仍只算卡牌和相册，`missing` 与 `album_missing` 分开，`album_failures` 仍只算相册）。报告的形状归候选 3。
- **兼容**：磁盘布局不变（`scripts/<类型>/<编号>.json` 与旁边的 `.etag`），现有 `cards.json` 等照旧能读，已有的缓存不用重拉。
- **文件**：新建 `backend/src/eidolon/script_cache.py`，只被 `story_sync` 使用。
- **测试**：仍只经 `sync_stories` 测外部行为；现有测试不改，作为重构的安全网（按请求次序计数的测试若因顺序变化失败，再按行为重写）。新增：卡牌、相册、活动各一个「删缓存重下」，相册「镜像上没有」在相册没变时不再请求。
- 不写 ADR（都容易撤回）。
