# 03: 重排校准，默认改用 Qwen3-Reranker-4B

**What to build:** 一份提交进仓库的小校准数据集和 `eidolon eval rerank` 命令，对着本地的私有剧情库和记忆，打印某个重排模型给「相关」与「不相关」候选的分数分布。用它比较 0.6B 与 4B，定出 4B 的检索阈值和记忆阈值；然后把默认重排模型改为 `Qwen/Qwen3-Reranker-4B`，阈值按模型分组。

**Blocked by:** None (can start immediately)

**Status:** ready-for-human（标注需要人工校对；代码部分 agent 可以先做）

- [ ] 数据集 `backend/eval/rerank-calibration.toml`：二三十条有代表性的问题，每条注明角色、问的是剧情/资料/记忆，以及哪些候选相关、哪些不相关（用剧情编号、资料标题或记忆文本标识）。只含问题、编号、标题和标注，不含剧情原文（ADR-0003）。agent 起草，人工校对
- [x] 记忆类问题需要的记忆不来自真实用户：数据集里自带几条示例记忆，命令运行时临时向量化，不写入数据库
- [x] 命令 `eidolon eval rerank [--model 模型名]`：按与对话中相同的方式取候选（向量检索 `CANDIDATES_PER_SOURCE` / 记忆 `CANDIDATES`）并重排，按「相关 / 不相关」分组打印分数分布，以及给定阈值下的命中与误放数量；标注里的候选没进入向量检索结果时单独列出（这是召回问题，不是阈值问题）
- [ ] 分别用 0.6B 和 4B 跑一遍，在 Comments 记录分数分布和选定的阈值及理由
- [x] 阈值按模型分组：0.6B 保持 `0.3` / `0.01`，4B 用校准出的值；未知模型用 4B 的阈值并在启动时打警告；`RERANK_MIN_RELEVANCE`（检索）与 `RERANK_MEMORY_MIN_RELEVANCE`（记忆）可手动覆盖
- [x] `DEFAULT_RERANK_MODEL` 改为 `Qwen/Qwen3-Reranker-4B`（已确认国内站 `api.siliconflow.cn` 仍提供；国际站标为 Deprecated，在 Comments 里注明）
- [x] 测试：阈值选择（已知模型、未知模型、环境变量覆盖）；`eval rerank` 用假的 embedder/reranker 跑通并输出预期统计

## Comments

2026-09-27 数据集初稿：`backend/eval/rerank-calibration.toml`，33 条（剧情 22、资料 5、记忆 6，其中 5 条 `relevant = []`），示例记忆 8 条。剧情编号取自 SCTranslationData 各 CSV 的 info 行，用到的剧情都确认角色出场、只取成功路线。全部 `reviewed = false`，待人工校对。需要特别注意：

- ~~资料类的标题是按 `characters/facts/example.md` 猜的~~ 已改为 `characters/facts/mano.md`、`kogane.md`（同日写成，随仓库提交，见 ADR-0003 修订）解析出的真实标题路径，并用 `parse_facts` 核对过全部引用。
- 私有剧情库里同步来的原文剧情不在 SCTranslationData 中，若有与问题相关的，会被算作「不相关」，校准跑出来时留意。
- `produce_events/100100002`、`produce_events/100400002`（与初见、试镜重复的独立剧本）都标成了相关，前提是它们在剧情库里是独立的剧情。
- 边界标注：下雨那条把【ソラを跳ね】「あめのひ」当作易误放项；恋鐘生日那条资料问题可能带出生日小剧情；「回老家」记忆问题把长崎出差记忆当干扰项。

2026-09-27 代码部分完成，等人工：校对数据集（`reviewed`）、用真实 key 分别跑 0.6B 和 4B。

- 命令：`eidolon eval rerank [--model 模型名] [--file 数据集] [--characters]`，逻辑在 `eidolon/rerank_eval.py`。剧情/资料问题走与对话相同的 `retrieval.rank_references`（这次从 `Retrieval._references` 抽出来的），记忆问题用示例记忆临时向量化后取 `memory.CANDIDATES` 条最近的再重排，不写数据库。输出分「剧情与角色资料」「记忆」两组，每组打印相关/不相关分数的分位数（最低、p10、p25、中位、p75、p90、最高）、当前阈值下的命中与误放数、没进入向量检索结果的相关候选，最后逐条列出每个问题的候选、分数和标注（+ 相关、~ 可放可不放、- 不相关）。
- 打印的阈值是该模型的分组阈值，环境变量覆盖同样生效；Docker 镜像里带上了 `eval/`，容器里直接 `docker compose exec backend eidolon eval rerank --model …`。
- 阈值分组在 `rerank.KNOWN_THRESHOLDS`。**4B 暂时沿用 0.6B 的 `0.3` / `0.01`**，校准后改这一处（和上面的注释）即可。未知模型用 4B 的阈值，启动时打警告。
- 默认模型已经改为 `Qwen/Qwen3-Reranker-4B`。国内站 `api.siliconflow.cn` 仍提供，国际站标为 Deprecated（见 `config.DEFAULT_RERANK_MODEL` 的注释）。
- 测试 `tests/test_rerank_eval.py` 还核对了数据集里引用的资料标题都在 `characters/facts/*.md` 中，改了资料标题会让它失败。

2026-09-27 剩下的做法（已和用户确定）：

1. 同步剧情库（agent 做，后台跑）：本地还没有数据库。把 SCTranslationData 克隆到仓库根目录的 `corpus/`，在 `backend/` 下运行 `uv run eidolon --db data/eidolon.db story sync`，首次大约一到两个小时，可以中断后重跑。**向量化用硅基流动**（`.env` 里 `EMBEDDING_PROVIDER` 留空，也就是默认的 siliconflow），不用 Gemini。
2. 校对数据集（用户做，可以用 `/grilling` 逐条过）：`backend/eval/rerank-calibration.toml` 里的标注，改完把 `reviewed` 设为 true。
3. 同步和校对都完成后，分别跑 `eidolon eval rerank --model Qwen/Qwen3-Reranker-0.6B` 和 `--model Qwen/Qwen3-Reranker-4B`。把分数分布和建议的阈值记在这里，用户确认后改 `rerank.KNOWN_THRESHOLDS`，同时决定默认模型是否保持 4B。

