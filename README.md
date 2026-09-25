# Eidolon-SC

和《偶像大师 闪耀色彩》的偶像实时对话的 AI 分身系统，供自己和小圈子使用。术语见 `CONTEXT.md`，规划见 `.scratch/mvp/`。

## 启动

```sh
cp .env.example .env   # 填写对话模型的地址、密钥和模型名
# 准备人设文件，见下方「角色」
docker compose up --build
```

打开 http://localhost:3000 ，在设置页填入访问密钥后即可在角色选择页挑一位角色对话。

## 角色

角色由 `characters/characters.toml` 配置：标识、显示名、简介、Fish Audio 音色 ID、人设文件和头像的位置。新增角色或替换音色 ID 只需要改这个文件，然后重启后端。

人设文件、角色资料和头像不进仓库（ADR-0003）。启动前参照 `characters/sheets/example.md` 写好 `characters/sheets/mano.md` 和 `characters/sheets/kogane.md`；角色资料（可选）参照 `characters/facts/example.md` 写在 `characters/facts/` 下；头像（可选）放在 `characters/avatars/` 下。缺少人设文件时后端会拒绝启动并指出缺哪一份。docker compose 会把 `characters/` 只读挂载进后端容器。

## 语音通话

在 `.env` 里填好 `SONIOX_API_KEY` 和 `FISH_AUDIO_API_KEY` 后，对话页的「语音通话」按钮就能用了：说中文或日语都可以，角色用配置的 Fish Audio 音色读日语原文，日语原文和中文字幕同时显示在对话记录里。通话中打字输入的内容和说的话进入同一条对话，角色同样用语音回复。「静音」开关打开后只显示文字、不合成语音。麦克风和通话音质在设置页选择。

浏览器和后端之间直接走 WebRTC（UDP）。本机用 docker compose 启动时，Linux 上的浏览器可以直接连到容器；其他情况（macOS 的 Docker Desktop、手机访问、公网部署）需要浏览器能连通后端，通常要配置 TURN 服务器，见 `.env.example` 里的 `EIDOLON_ICE_SERVERS`。

## 剧情库

角色能回忆的原作剧情来自 [SCTranslationData](https://github.com/ShinyGroup/SCTranslationData) 的剧情 CSV，缺少的部分可以用游戏原始剧本 JSON 补全。剧情数据不进仓库（ADR-0003）：把它克隆到仓库根目录的 `corpus/`（已被 git 忽略，docker compose 会把它只读挂载到后端容器的 `/corpus`），在 `.env` 里填好 `SILICONFLOW_API_KEY`，然后导入：

```sh
git clone --depth 1 https://github.com/ShinyGroup/SCTranslationData.git corpus/SCTranslationData
docker compose exec backend eidolon story import-csv /corpus/SCTranslationData/data/story
```

- 每个 CSV 导入为一段剧情，以文件末尾 `info` 行指向的原始剧本为主键，重复导入会覆盖更新；内容没有变化的剧情不会重新向量化，所以原作更新后随时可以重新导入。
- 失败结局（W.I.N.G. 敗退、季度目标未达成、G.R.A.D. 败退、试镜落败、约定未遵守）按原始剧本编号识别并排除；制作人的选项不收录。
- 出场角色按台词的说话人识别：`characters.toml` 里每位角色的 `speakers` 列出她在剧本里的名字（如 `真乃`）。修改 `speakers` 或新增角色后需要重新导入。
- 向量化默认使用硅基流动的 `Qwen/Qwen3-Embedding-0.6B`，可用 `EMBEDDING_MODEL` 更换；换模型后重新导入即可。只有出场角色非空的剧情会被向量化。
- 剧情目录按「角色 → 卡或活动 → 话」分层，直接由剧情库生成，所以总是和最近一次导入一致；导入结束时会列出每位角色的目录规模。

SCTranslationData 里没有的剧情，可以用游戏原始剧本 JSON 补全（每个文件是游戏里一段剧本的帧数组，字段有 `speaker`、`text`、`select` 等）：

```sh
docker compose exec backend eidolon story import-json /corpus/scripts
```

- 剧本编号取自文件路径，可以按游戏里的路径存放（`produce_events/100100101.json`），也可以用汉化插件的命名（`produce_events_100100101.json`）。路径里没有剧本编号的文件会被跳过并给出警告（无法和同一段剧本的 CSV 去重）。
- 像 SCTranslationData 那样放在「出处/」目录下时，出处取目录名、标题取文件名；按游戏路径存放时，出处是去掉最后两位话数的剧本编号（如 `produce_events/2011005`），标题是 `produce_events_201100501` 这样的名字。
- 规则和 CSV 相同：排除失败结局，制作人的选项不收录，角色对每个选项的反应都保留。
- 同一段剧本已经从 CSV 导入过时，保留带中文翻译的 CSV 版本，JSON 不会覆盖它；反过来，之后导入的 CSV 会替换 JSON 版本。只从 JSON 导入的剧情没有中文翻译，但检索和剧情目录照常可用。

本地开发时用 `uv run eidolon --db data/eidolon.db story import-csv <目录>`（`import-json` 同理）。

## 对话中的检索

在 `.env` 里填好 `SILICONFLOW_API_KEY`、`AI_GATEWAY_API_KEY` 和 `JEV_MODEL` 后，角色就能在对话中回忆剧情、查阅角色资料；缺任何一项时只凭人设回复。

- 每一句话先交给 Jev（通过 Vercel AI Gateway 调用）判断这句话需要什么：寒暄闲聊不检索，不增加延迟；需要资料时做下面的检索；问「那次……是怎么回事」这类过去经历时，直接用这句话「回顾剧情」，把结果放进提示词，省去对话模型自己调用工具的那一轮。Jev 出错时照常检索。
- 需要检索时，同时检索剧情库里当前角色出场过的剧情和她的角色资料，用硅基流动的 Qwen3-Reranker（`RERANK_MODEL` 可换）重排，取相关程度够高的最多 5 条放进提示词（和话题无关时一条都不放）。检索或重排出错时，本回合不带检索结果照常回复。
- 对话模型还可以调用「回顾剧情」工具（`recall_story`）：制作人问「那次……是怎么回事」这类问题时，角色用一句概括去查自己出场过的剧情，拿回最相关的最多 2 段剧情的原文（附带它在剧情目录中属于哪张卡或哪个活动、同一处还有哪些剧情），再据此回答。一句话最多调用 1 轮工具；Jev 已经判断为回顾剧情的回合不再提供这个工具。对话模型需要支持工具调用。
- 角色资料是 `characters.toml` 里 `facts` 指向的 Markdown 文件，每个标题下的内容是一条。第一次检索某位角色时向量化，之后只有改动过的条目会重新向量化；修改后重启后端即可。

## 用户与访问密钥

管理员用命令行管理用户和访问密钥。一位用户可以持有多把密钥，对话记录属于用户本身；吊销一把密钥不影响用户的数据。

```sh
docker compose exec backend eidolon user create alice    # 创建用户
docker compose exec backend eidolon key issue alice      # 签发密钥（只显示这一次）
docker compose exec backend eidolon key list alice       # 查看密钥编号和状态
docker compose exec backend eidolon key revoke <密钥编号>  # 吊销
```

本地开发时用 `uv run eidolon --db data/eidolon.db ...`。01 阶段遗留的默认用户名为 `default`，为它签发密钥即可继续访问原有对话。

## 开发

后端（Python，`backend/`）：

```sh
cd backend
uv sync
uv run pytest        # 测试
uv run pyright       # 类型检查
CHAT_LLM_BASE_URL=... CHAT_LLM_API_KEY=... CHAT_LLM_MODEL=... uv run eidolon   # 启动在 :8000，读取 ../characters/characters.toml（可用 EIDOLON_CHARACTERS_PATH 覆盖）
```

前端（Next.js，`frontend/`）：

```sh
cd frontend
npm install
BACKEND_URL=http://localhost:8000 npm run dev   # 启动在 :3000，/api/* 转发给后端
npm run typecheck
```
