## Agent skills

### Issue tracker

Issues live as local markdown files under `.scratch/<feature>/`. See `docs/agents/issue-tracker.md`.

### Triage labels

Default vocabulary: `needs-triage`, `needs-info`, `ready-for-agent`, `ready-for-human`, `wontfix`. See `docs/agents/triage-labels.md`.

### Domain docs

Single-context: one `GLOSSARY.md` + `docs/adr/` at the repo root. See `docs/agents/domain.md`.

### Frontend

前端用 shadcn/ui（底层 Base UI，样式 `base-nova`）加 Tailwind v4。写前端代码前读 `frontend/AGENTS.md` 的「shadcn 纪律」，视觉规范以 `DESIGN.md` 为准。

### Implementing

实现票（`/implement`、`/implement-spec`，连同它们派的子代理）前读 `docs/agents/implementing.md`：本机跑哪些测试、draft PR 和 CI、怎么排票、每张票怎么收尾。

### Local acceptance

票里要求「本地构建版上用 Playwright 验收」时（尤其改了通话、对话页或导航外壳），先读 `docs/agents/local-acceptance.md`：服务怎么起、怎么停，开发登录，假麦克风，怎么拦下 `/api/offer` 造出各种结束卡。

### Character authoring

添加或扩充骑空团伙伴（调用 `gbf-character-author` 技能）时，严格对标娜露梅/维卡拉的黄金标准，严禁「卡及格线交付」：
- **拒绝最低门槛交差**：自动化门禁（`validate_character.py` 的 facts $\ge 50$ 行、episodes $\ge 15$ 段）是防构建破损的物理底线，不是交付标准。正式交付必须达到 **120~150+ 行高密事实**与 **30+ 段模块化切片**。
- **批量新增不降质**：多人同时入团时严禁套用泛化模版敷衍。每位角色必须独立考据：官方角色歌（同步 `world.json`）、全卡池异格（泳装/浴衣/万圣/圣诞）、1~5 年期节日语音心境递进、技能与奥义全台词，以及与团长的深层羁绊。
- **全异格真理核验，严禁套模板虚构**：严禁下意识默认“每个角色都出过泳装或浴衣”。必须对照 Wiki 的「Character Versions」官方列表，只有真实落地的卡池异格（如万圣、情人节、圣诞等）才可独立成段；奥义（【……】）与技能名（1/2/3/4 abi）必须 100% 摘抄自官方战斗表格，严禁自行脑补假技能（如 `~スフィア`、`~ブラスト`）。
- **全篇语气穿透与零违和残留**：第一人称（如「此方」「イーウィヤ」）、第二人称（「特異点」「おぬし」）与句尾口癖（「〜ぞよ」「〜のじゃ」）必须穿透到 facts 全篇（包含人物关系、日常作息、1~5 年节日祝词与生日）。严禁局部设定改了、但节庆和关系中仍然残留二创刻板动漫腔（如「我輩」「下僕」「オイラ」）。
- **RAG 切片细粒度**：剧本必须按场景独立切片（每段 3~5 句对话带 `[season:*]` 标签），严禁大包单篇混杂，确保重排器（Reranker）语义召回精准。
- **原典一手语音压倒二创梗（防萌宠降智）**：严禁采纳同人、玩家梗或官方搞笑四格（ぐらぶるっ！）的戏剧化二创（例如强行让不说话的角色像宝可梦一样叫自己的名字「ゆぐゆぐ〜♪」）。发声与台词必须查验 Wiki 官方语音表（音声・ボイス表）。
- **非人类言语角色心智绝不降级**：无人类语言能力 $\ne$ 无知无觉。对星晶兽、神兽或特殊发声角色，必须赋予其细腻深沉的高维自我意识，严禁降格为被动死物或无脑吉祥物；发声外化（空灵神鸣/乐音）与心声意象（全角括号封闭）必须严格隔离。

