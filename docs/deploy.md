# 部署到 VPS

生产环境用 `docker-compose.prod.yml`，和本地开发用的 `docker-compose.yml` 分开。它包含四个服务：

- **caddy**：HTTPS 入口。自动向 Let's Encrypt 申请、续期证书，HTTP 自动跳转到 HTTPS（浏览器只有在 HTTPS 下才允许使用麦克风）。
- **frontend**、**backend**：只监听 127.0.0.1，不直接暴露在公网上。
- **coturn**：STUN/TURN 服务。手机在移动网络等 NAT 后面时，常常没法和服务器直接建立 UDP 连接，这时语音经 coturn 中继（UDP 或 TCP 的 3478 端口）。只放行 443 端口的网络（部分公司、学校的网络）目前连不上语音，文字对话不受影响。

四个服务都用 host 网络：后端要把本机的公网地址告诉浏览器，coturn 要直接收发 UDP，用 Docker 的端口映射做不到。所以这份配置只适用于 Linux。

## 准备

- 一台 Linux VPS，有公网 IPv4 地址。
- 装好 Docker 和 Docker Compose 插件（`docker compose version` 能运行）。
- 一个域名，添加一条 A 记录指向这台 VPS。国内的服务器需要域名已备案，否则 80、443 端口会被拦截。
- 打算用 Gemini 做向量化时（见下文「选择向量化服务」），VPS 不能在中国大陆、香港、澳门：Gemini API 不对这些地区开放。用硅基流动没有这个限制。
- 防火墙（包括云厂商控制台里的安全组）放行：

  | 端口 | 协议 | 用途 |
  |---|---|---|
  | 80、443 | TCP | 网站（80 只用来申请证书和跳转到 HTTPS） |
  | 443 | UDP | HTTP/3（可选） |
  | 3478 | TCP 和 UDP | STUN/TURN |
  | 49160-49259 | UDP | TURN 中继端口（可用 `EIDOLON_TURN_MIN_PORT`、`EIDOLON_TURN_MAX_PORT` 调整） |

  防火墙不放行其他 UDP 端口也没关系，语音会经 coturn 中继；放行时（很多 VPS 默认不设防火墙），电脑和服务器之间可以直接连接，少绕一步。

## 部署

```sh
git clone <仓库地址> eidolon-sc && cd eidolon-sc
cp .env.example .env
```

在 `.env` 里填写：

- 模型和各项服务的密钥，和本地开发时一样（见 `.env.example` 里的说明）。至少要有对话模型；语音通话需要 Fish Audio（`FISH_AUDIO_API_KEY`），加 Soniox 或阿里云百炼之一做语音识别（`SONIOX_API_KEY`，或 `STT_PROVIDER=bailian` 加 `DASHSCOPE_API_KEY`）；剧情库、检索和记忆需要向量化服务（见下一节）。
- `EIDOLON_DOMAIN`：网站的域名，例如 `eidolon.example.com`。
- `EIDOLON_PUBLIC_IP`：这台服务器的公网 IPv4 地址。coturn 只允许把语音中继到这台服务器（也就是后端），别人拿不到它当开放的中继用。
- `EIDOLON_PRIVATE_IP`：只有公网地址不在网卡上时才填，填网卡上的内网地址。在服务器上执行 `ip -4 addr`：能看到公网地址就不用填（Vultr、DigitalOcean、搬瓦工等大多如此）；只能看到 `10.`、`172.`、`192.168.` 开头的内网地址时（AWS、阿里云、腾讯云等 1:1 NAT 的云主机），填这个内网地址。这种环境还没有实际验证过，语音连不上时请看「排障」。
- `EIDOLON_TURN_SECRET`：coturn 和后端共用的密钥，用 `openssl rand -hex 32` 生成。后端给每位用户签发 24 小时后过期的 TURN 凭据，这个密钥本身不会发给浏览器。
- `GITHUB_CLIENT_ID`、`GITHUB_CLIENT_SECRET`，`GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`：用户登录用的 OAuth 应用，至少配一家，见下文「配置 OAuth 应用」。只配了一家时，登录页只显示那一种。
- `EIDOLON_SECRET_KEY`：加密用户自带 API 密钥和后台里保存的 key 用的密钥，用 `openssl rand -hex 32` 生成。不填就不开放自带密钥，后台里的 key 也只能看不能改。填了之后**不要更换**：换了以后已保存的自带密钥都无法解密，用户要重新填写；后台里保存的 key 也解不开，那几项回退到 `.env` 的值（见下文「后台」）；封禁名单是用它派生的密钥做的哈希，也对不上了，被删除的封禁用户能重新注册。
- `EIDOLON_ADMINS`、`EIDOLON_CONTACT`（可选）：管理者名单和给被封禁的用户看的联系方式，见下文「后台」。不填管理者名单时没有后台，一切照旧用 `.env` 和命令行。
- **不要**填 `EIDOLON_DEV_LOGIN`：它让任何人不经登录就能冒充任何用户，只能在本地开发时打开。配置了 `EIDOLON_DOMAIN` 时后端检测到它会拒绝启动。

`EIDOLON_ICE_SERVERS`、`EIDOLON_TURN_URLS` 不用填：生产配置会自动用本机的 coturn。

### 选择向量化服务

剧情库、角色资料和记忆用同一个向量化服务，在 `.env` 里用 `EMBEDDING_PROVIDER` 二选一（ADR-0005）：

- `siliconflow`（默认）：硅基流动的 `Qwen/Qwen3-Embedding-0.6B`，只需要 `SILICONFLOW_API_KEY`。
- `gemini`：Google 的 `gemini-embedding-2`，填 `GEMINI_API_KEY`（在 [Google AI Studio](https://aistudio.google.com/apikey) 申请），向量维度用 `EMBEDDING_DIMENSIONS` 指定（默认 1536）。重排仍然在硅基流动，`SILICONFLOW_API_KEY` 照样要填。
  - 服务器必须在 Gemini API 开放的地区（不含中国大陆、香港、澳门），否则向量化会报错并提示地区不支持。
  - 免费层每分钟最多向量化 100 条文本（一次批量请求里的每条文本都各算一次请求）。同步、导入和 `eidolon reembed` 碰到限流会按 Google 给的时间自动等待再继续，所以能跑完，只是整个剧情库要花上几十分钟以上；免费层可能还有每天的上限（在 AI Studio 的 Rate Limit 页面查看），碰到时命令会报错退出，第二天重新运行即可接着做。对话中的查询不等待：限流时这一回合不带检索结果照常回复。
  - **公开部署不要用免费层**（ADR-0005 的修订）：免费层的内容会被 Google 用于改进产品，送去向量化的包括剧情库（没有许可证的剧情文本，ADR-0003）和陌生用户的记忆。在 AI Studio 开通计费（付费层的内容不用于训练；文本约 $0.20 / 百万 token，全量剧情库重新向量化一次只要几美元），然后在 `.env` 里填 `GEMINI_BILLING_ENABLED=1` 声明已开计费；没有声明时，公开部署的后端每次启动都会在日志里警告。不想开计费就改用硅基流动。

然后准备人设文件（见 README 的「角色」：`characters/sheets/` 下每位角色一份，角色资料和头像可选），启动：

```sh
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

前端和后端用 CI 发布到 GHCR 的镜像（`ghcr.io/sallyn0225/eidolon-sc-frontend`、`-backend`），服务器上不用构建。镜像只有 linux/amd64 一种。arm64 的服务器，或者想用自己改过的代码时，改用 `up -d --build` 在服务器上构建。

第一次启动时 Caddy 会申请证书，稍等片刻后用浏览器打开 `https://你的域名`。后端启动失败时（缺少人设文件、对话模型检查不通过等），用 `docker compose -f docker-compose.prod.yml logs backend` 查看原因。

下面的命令都要带上 `-f docker-compose.prod.yml`。嫌麻烦的话，在这台服务器上执行一次 `export COMPOSE_FILE=docker-compose.prod.yml`（或者写进 shell 的配置文件），之后 README 里的 `docker compose ...` 命令就能原样使用。

## 同步剧情库

剧情库用一条命令同步：先导入 SCTranslationData 的汉化版，再从 ShinyColorsDB 镜像补齐还缺的卡牌剧情、培育剧情和活动剧情（原文剧情，规则见 README 的「剧情库」）。需要 `.env` 里填好向量化服务的 key（默认 `SILICONFLOW_API_KEY`，选 Gemini 时是 `GEMINI_API_KEY`）。

`deploy/story-sync.sh` 把这件事做完整：更新（第一次是克隆）仓库根目录下的 `corpus/SCTranslationData`，再在后端容器里运行 `eidolon story sync`，把输出追加到 `logs/story-sync.log`。先手动运行一次首次全量补齐：

```sh
deploy/story-sync.sh
tail -f logs/story-sync.log   # 另开一个终端看进度
```

首次要下载几千个剧本，镜像要求逐个请求、间隔约一秒，所以大约需要一到两个小时（还要加上向量化的时间）。中途中断（关掉终端、重启服务器、向量化出错）也没关系，重新运行会接着做，已下载的剧本不会重新下载。之后每次只下载新卡、新活动和有变化的卡，通常几分钟就结束。

活动名写在 `deploy/event-names.toml`（参照 `deploy/event-names.example.toml`，每出一个新活动加一行；`deploy/` 以只读方式挂载到后端的 `/deploy`），改完后下一次同步生效，没填的活动先用占位名，同步结束时会列出来。

### 每周自动同步

用主机上的 cron 每周运行一次。`crontab -e`，加一行（路径换成仓库的实际位置；这里是每周一 4:17，时间随意，避开整点即可）：

```cron
17 4 * * 1 /home/you/eidolon-sc/deploy/story-sync.sh
```

运行 cron 的用户要能执行 `docker compose`（root，或在 `docker` 组里），并且对仓库目录有写权限（要写 `corpus/` 和 `logs/`）。主机上要有 `git` 和 `flock`（util-linux，一般发行版都自带）。脚本自己把输出写进日志，cron 不会发邮件。

日志在 `logs/story-sync.log`（可用环境变量 `EIDOLON_SYNC_LOG` 改到别处），每次同步以「开始同步剧情库」开头、以「结束：退出码 N（含义）」结尾，中间是 git 的输出和同步报告：汉化版新增、更新了多少段（其中多少段取代了原文剧情），原文剧情下载、新增了多少，跳过了多少失败结局，新向量化了多少段，还有需要人工核对的失败嫌疑剧情和没有活动名的活动。看最近几次的结果：

```sh
grep '结束：' logs/story-sync.log | tail
```

| 退出码 | 含义 | 要做什么 |
|---|---|---|
| 0 | 完全成功 | 不用管 |
| 1 | 同步命令出错：配置错误（对照表格式不对、缺少向量化服务的 key 等），或向量化中断 | 看日志里的错误；向量化中断时重新运行即可继续 |
| 2 | 镜像或 API 出错，这次没拉到（全部）原文剧情；汉化版已照常导入 | 通常不用管，下次同步会接着拉取；连续几周都是 2 时看日志里的错误 |
| 3 | git 没能更新 SCTranslationData（网络问题、本地改动导致不能快进、`corpus/SCTranslationData` 不是 git 仓库）；有已下载的数据时照常用它同步 | 看日志里 git 的输出，必要时删掉 `corpus/SCTranslationData` 让脚本重新克隆。用 root 的 cron 运行、仓库却属于别的用户时，git 会报 `dubious ownership`，按提示执行 `git config --global --add safe.directory …`，或者改用仓库所属用户的 crontab |
| 4 | 后端容器没有运行，或无法运行同步命令（没有 docker 的权限、找不到 flock 等，原因在日志里） | 容器没有运行时 `docker compose -f docker-compose.prod.yml up -d` |
| 5 | 上一次同步还没结束（例如首次全量补齐还在跑），这次没有运行 | 不用管 |

同步出错时退出码以 1、2 为准（git 同时出错会写在日志里）。日志每周只增加几十行，不用轮转；太大时直接删掉即可。

脚本默认用 `docker-compose.prod.yml`，设置了 `COMPOSE_FILE` 时用它指定的配置。想先小规模试一试，可以直接在容器里运行同步，例如只同步櫻木真乃的卡和相册：`docker compose -f docker-compose.prod.yml exec backend eidolon story sync --idol 1`。

### 缓存与手动导入

下载的原始剧本缓存在后端数据卷里的 `/data/mirror`（和数据库同在 `eidolon-data` 卷里，升级、重建容器都会保留），不进仓库。镜像修正了某个剧本、想重新下载时，删掉缓存里对应的文件即可，例如：

```sh
docker compose -f docker-compose.prod.yml exec backend rm /data/mirror/scripts/produce_events/200100401.json
```

镜像上没有的剧本，缓存里会在它的位置留一个 `.missing` 标记。卡牌和活动的每次同步都会再问，相册里的只在相册有变化时才再问。想让同步马上再问一次相册里的某个剧本，删掉它的标记即可，例如 `rm /data/mirror/scripts/produce_events/100100103.missing`。

也可以不用同步，手动导入（例如只想导入汉化版，或者有自己导出的游戏剧本 JSON）：

```sh
git clone --depth 1 https://github.com/ShinyGroup/SCTranslationData.git corpus/SCTranslationData
docker compose -f docker-compose.prod.yml exec backend eidolon story import-csv /corpus/SCTranslationData/data/story
# 用游戏原始剧本 JSON 补全（放在 corpus/scripts 下）
docker compose -f docker-compose.prod.yml exec backend eidolon story import-json /corpus/scripts
```

导入的结果存在数据库里。只手动导入时，之后可以删掉 `corpus/` 节省空间；用每周同步时要保留 `corpus/SCTranslationData`，脚本每次只 `git pull` 增量更新。

## 更换向量化服务、模型或维度

库里只保留当前模型的向量，换了之后要用库里的原文重新向量化一遍（不需要重新下载或导入剧情）：

1. 改 `.env` 里的 `EMBEDDING_PROVIDER`、`EMBEDDING_MODEL` 或 `EMBEDDING_DIMENSIONS`（换到 Gemini 时别忘了 `GEMINI_API_KEY`；换服务时把 `EMBEDDING_MODEL` 清空或改成新服务的模型，否则旧服务的模型名会原样发给新服务）。
2. 重启后端：`docker compose -f docker-compose.prod.yml up -d`。启动日志里会提示剧情库有多少段缺当前模型的向量。
3. 重新向量化：

   ```sh
   docker compose -f docker-compose.prod.yml exec backend eidolon reembed
   ```

   依次处理剧情库、角色资料和全部用户的记忆，打印进度和各处新向量化的条数；全部成功后删除旧模型的向量。整个剧情库要花一段时间（和首次同步的向量化差不多），期间服务照常可用，只是剧情检索暂时只查得到已完成的部分（角色资料和记忆在被检索到时就会按新模型补上向量）。中途中断或向量化出错时，已完成的部分会保留、旧向量不会删除，重新运行即可接着做。

模型的存储标识带上了维度（如 `gemini-embedding-2@1536`），所以只改维度也要走一遍这个流程。换回原来的模型同样要再跑一次。

## 校准重排阈值

重排默认用硅基流动的 `Qwen/Qwen3-Reranker-0.6B`，也可以用 `RERANK_MODEL` 换成 `Qwen/Qwen3-Reranker-4B`（国内站 `api.siliconflow.cn` 提供；国际站已标为 Deprecated）。在校准数据集上，0.6B 挑剧情和角色资料比 4B 准，4B 挑记忆略好一些。重排分数低于阈值的剧情、角色资料、作品资料（歌曲、唱片和演出）或记忆不会放进提示词，阈值按模型分组，都是用下面的命令校准过的：0.6B 是 `0.3` / `0.01`，4B 是 `0.7` / `0.005`；其他模型用 4B 的值并在启动日志里提示。也可以在 `.env` 里用 `RERANK_MIN_RELEVANCE`（参考资料：剧情、角色资料和作品资料）和 `RERANK_MEMORY_MIN_RELEVANCE`（记忆）手动指定。

`eidolon eval rerank` 用仓库里的校准数据集（`backend/eval/rerank-calibration.toml`：一些有代表性的问题，以及哪些剧情、角色资料、作品资料、记忆和它们相关；只有编号和标题，不含剧情原文）对着本地的剧情库和 `characters/world.json` 跑一遍检索和重排，分「参考资料」（剧情、角色资料和作品资料一起重排，和对话中一样）和「记忆」两组，打印「相关」与「不相关」候选的分数分布、当前阈值下的命中与误放数量，以及没进入向量检索结果的相关候选（那是召回问题，调阈值解决不了）。作品资料的问题引用了 `world.json` 里没有的标题时，命令报错退出：

```sh
docker compose -f docker-compose.prod.yml exec backend eidolon eval rerank
docker compose -f docker-compose.prod.yml exec backend eidolon eval rerank --model Qwen/Qwen3-Reranker-4B
```

换重排模型前用它比较两个模型的分数分布，再决定阈值。需要剧情库已经同步好，并且有当前向量化模型的向量；数据集里的记忆是虚构的示例，运行时临时向量化，不会写进数据库。

## 校准判断模型阈值

判断模型（Jev、Clef 或 Clef-flash，见 README 的「对话中的检索」）对每个问题给出概率，达到阈值才算「是」。阈值按模型写在 `backend/src/eidolon/judge.py` 的 `JUDGE_THRESHOLDS` 里，Clef-flash 经 OpenRouter 和直连用同一组；其他模型名用 Jev 的，并在启动日志里提示。情绪的最低概率可以用 `JUDGE_EMOTION_MIN_PROBABILITY` 覆盖，检索的三个阈值不能在 `.env` 里改。

| | 要检索参考资料 | 问过去的经历 | 在说自己的事 | 情绪最低概率 |
|---|---|---|---|---|
| Jev | 0.5 | 0.5 | 0.5 | 0.5 |
| Clef | 0.5 | 0.8 | 0.1 | 0.4 |
| Clef-flash | 0.5 | 0.7 | 0.3 | 0.4 |

`eidolon eval judge` 用仓库里的 eval 集（`backend/eval/judge.toml`：虚构的对话回合和回复片段，以及期望的判断结果，不含剧情原文）按对话中的方式逐条提问，打印检索判断的混淆矩阵和准确率、每个问题在期望为是和期望为否时的概率分布、情绪和点头的准确率、输入 token 数和平均延迟；`--json` 把汇总写进文件，方便比较：

```sh
docker compose -f docker-compose.prod.yml exec backend eidolon eval judge
docker compose -f docker-compose.prod.yml exec backend eidolon eval judge --provider cloudflare --model clef --json /tmp/clef.json
```

不带 `--provider` 时用 `.env` 里配的那一家。定上面这些阈值时（47 条检索、33 条情绪），检索判断的准确率 Jev 和 Clef 都是 94%，Clef-flash 87%；情绪准确率 Jev 100%，Clef 和 Clef-flash 都是 91%。eval 集不大，换模型或改了判断的问题后，先跑一遍看概率分布再改阈值。

## 记忆评测

`eidolon eval memory` 用仓库里的评测集（`backend/eval/memory.toml`：虚构的用户说的话和角色的回复，以及这一轮该写下什么、该想起哪些记忆，不含剧情原文）检查角色「记得对不对」。它用 `.env` 里配的背景模型、向量化、重排和判断模型，按真实回合的路径跑：每题用一个临时数据库和一位虚构的用户，不碰部署的数据库。提炼题看这一轮该记的记了没有、不该记的有没有记、该取代的取代了没有，每题跑 3 次取多数；召回题看该想起的想起来没有、不该想起的有没有出现，并打印判断模型的结论。结果按题型（取代、重复、短期状态、代词、专有名词、前情）汇总；`--json` 把逐条结果写进文件：

```sh
docker compose -f docker-compose.prod.yml exec backend eidolon eval memory --json /tmp/memory.json
```

基线结果提交在评测集旁边（`backend/eval/memory-baseline.json`）。改动记忆的提炼或召回以后重跑：针对的那一类题，通过数要多于基线；其他各类最多比基线少 1 个用例（前情类只作参考）。一次完整的运行要调用背景模型一百次左右，需要几分钟。

## 立绘素材

通话层上可以叠一层原作的 Spine 立绘（GLOSSARY.md「立绘」）。素材不进仓库（ADR-0003 的 2026-09-30 修订），放在你选的 S3 兼容对象存储里，浏览器直接从存储桶下载。三项都配好了，这位角色的通话层才显示立绘；少一项就和原来一样，只显示背景图：

- `characters/characters.toml` 里这位角色的 `idol_id`：原作的偶像编号，即 ShinyColorsDB 的 `idolId`（同步后整理目录 `source/spine_manifest.json` 里也有）（真乃是 1，灯织是 2，めぐる是 3，恋钟是 4）。
- 同一段里的 `default_outfit`：用户没选过衣装时她穿的那一套，写成 `stand/<enzaId>`（这张卡的私服）或 `stand_costume/<enzaId>`（演出服），`enzaId` 是卡的十位编号（`source/spine_manifest.json` 里的 `enzaId`），例如 `stand/1030010010`。
- `.env` 的 `EIDOLON_STAND_ASSETS_URL`：存储桶的公开访问地址，例如 `https://stand.example.com`。

改完重启后端。`idol_id` 或 `default_outfit` 格式不对时后端拒绝启动，并说明是哪位角色的哪一项。

### 选择对象存储

任何 S3 兼容的对象存储都行：Cloudflare R2（不收流量费）、腾讯云 COS、阿里云 OSS、AWS S3，或者自己搭的 MinIO、SeaweedFS。同步脚本只用 S3 接口，不依赖哪一家。每位角色约 120MB（真乃 84 套、恋钟 80 套衣装，加上缩略图），浏览器打电话时下载一套，平均约 1.3MB（之后走缓存）。服务器在国内时，选国内的存储、配上已备案的域名，手机上的加载会快很多。

建一个存储桶，再建一对只能写这个存储桶的访问密钥（R2 叫「API 令牌」，选 Object Read & Write），然后配置：

- **公开可读**：不签名、不要求登录（R2 在存储桶设置里连接自定义域名或打开 `r2.dev` 地址；COS、OSS 把存储桶设成「公有读私有写」）。这个公开地址就是 `EIDOLON_STAND_ASSETS_URL`。
- **CORS**：允许网站的域名（`https://你的域名`）用 `GET` 访问。立绘用 WebGL 绘制，贴图跨域时没有 CORS 就加载不了，通话层会退回背景图。本地开发时再加上 `http://localhost:3000`。
- **缓存**：同步脚本上传时给每个文件设好了 `Cache-Control`，存储桶这边不用另外设置，只要别用规则覆盖掉：衣装的文件内容不会变，是 `public, max-age=31536000, immutable`；缩略图可能重画，是一天；衣装清单随新卡变化，是 `no-cache`（每次都向存储桶确认）。前面有 CDN 时，让它沿用源站的 `Cache-Control`。

**前面有 CDN 时**（推荐，尤其是国内）：存储桶可以保持私有，只让 CDN 回源。以腾讯云为例：CDN 添加加速域名（例如 `stand.你的域名`），源站类型选 COS 源、选中这个存储桶，打开「私有存储桶访问」并按提示给 CDN 授权；缓存配置里节点缓存和浏览器缓存都选「遵循源站」（不然衣装清单会被缓存几十天，新卡迟迟不出现）；「高级配置 → HTTP 响应头」加一条 `Access-Control-Allow-Origin: *`（存储桶私有时 CORS 由 CDN 统一加）；申请证书、开启 HTTPS 服务（网站是 HTTPS，浏览器不许加载 HTTP 的立绘）；建议再设一条用量封顶，防止被刷流量。`EIDOLON_STAND_ASSETS_URL` 填 CDN 的地址，例如 `https://stand.你的域名`。这样直接访问存储桶会被拒绝，公开的只有 CDN。

**存储桶里的结构**：

| 位置 | 内容 |
|---|---|
| `spine/idols/<stand 或 stand_costume>/<enzaId>/` | 一套衣装的 `data.json`、`data.atlas`、`data.png`，和 ShinyColorsDB 的 CDN 上一样。贴图原样上传：约一半其实是 WebP，只是叫 `.png`，上传时按文件内容标成 `image/webp` |
| `thumbnails/<stand 或 stand_costume>/<enzaId>.png` | 这套衣装的缩略图：电脑「半身 ADV」的取景，400×500，透明背景 |
| `outfits/<idol_id>.json` | 这位角色的衣装清单，换衣装面板按它列出衣装 |

后端通过 `/api/characters` 把默认衣装的地址和衣装清单的地址（`stand.outfits_url`）告诉浏览器。

**衣装清单**的格式：

```json
{
  "idol_id": 1,
  "cards": [
    {
      "id": "1030010010",
      "name": "ナチュラルモード",
      "type": "P_SR",
      "everyday": {"id": "stand/1030010010", "url": "../spine/idols/stand/1030010010/", "thumbnail": "../thumbnails/stand/1030010010.png"},
      "stage": {"id": "stand_costume/1030010010", "url": "../spine/idols/stand_costume/1030010010/", "thumbnail": "../thumbnails/stand_costume/1030010010.png"}
    }
  ]
}
```

- 每张卡一项，按 `id`（enzaId）排序，也就是原作的发布顺序。只收 stand 和 stand_costume，不收 Q 版小人（cb）。
- `name` 是卡名，原文去掉【】和角色名（`【ナチュラルモード】櫻木真乃` 是 `ナチュラルモード`）；原作里没有卡名的（`【】櫻木真乃`）用角色名。`type` 是 `spine_manifest.json` 的 `dressType`：P_SR、P_SSR、Special、Mizugi 等。
- `everyday` 是这张卡的私服（`stand`），`stage` 是演出服（`stand_costume`），没有的为 `null`。两套贴图逐字节相同时（多数 Special 卡）只算一套，记在 `everyday`。`default_outfit` 要写清单里有的那套：写成被去重的演出服时它不会上传，同步时会提示。
- `url` 和 `thumbnail` 是相对于衣装清单本身的地址（浏览器里用 `new URL(url, outfits_url)` 解析）。

### 同步素材

`deploy/stand-sync.sh` 从 ShinyColorsDB 拉取新卡、把立绘上传到存储桶（ADR-0011），分四步：

1. `eidolon stand fetch`：每次都向 ShinyColorsDB 的 API 重新要 `characters.toml` 里配了 `idol_id` 的每位角色的卡，从它的 CDN 下载整理目录的 `source/` 里还没有的私服和演出服（不下载 Q 版小人）。衣装的文件不会变，已经有的不再下载；请求一个一个发、间隔约 1 秒，第一次拉 4 位角色要十几分钟，之后只拉新卡。`source/spine_manifest.json` 记着拉到的每套衣装，只增不减：上游哪天不再列某张卡，换衣装面板上也照常有它。上游列了却还没有文件（或发来的文件不对）的衣装跳过并提示，下次同步再试。ShinyColorsDB 连不上或接口变了时，已拉到的照常保留，后面三步用已有的素材照常跑，同步以退出码 6 结束。
2. `eidolon stand outfits`：从拉取到的立绘为每位配了 `idol_id` 的角色整理衣装清单，写进整理目录。`default_outfit` 不在清单里时会提示。
3. `npm run stand:thumbnails`（在 `frontend/` 里）：用和通话层同一套播放代码，在无界面的 Chromium 里给每套衣装渲染一张缩略图，渲染前先让动画走约 1 秒，避开待机表情开头的眨眼。已经有缩略图的不再渲染，想全部重画时删掉整理目录里的 `thumbnails/`（或者直接运行 `npm run stand:thumbnails -- --force`）。
4. `eidolon stand upload`：上传衣装清单列出的每套衣装的文件、缩略图，最后上传衣装清单。缩略图渲染失败的衣装照常上传、照常列在清单里，换衣装面板上暂时没有它的缩略图，下次同步补上。存储桶里已经有、内容相同的（按 ETag 比较 MD5）不重复上传，所以再次同步时只多列一次存储桶。

脚本不经过 docker，直接在服务器或自己的电脑上运行都行（后端只需要知道 `EIDOLON_STAND_ASSETS_URL`）。这台机器上要有：

- [uv](https://docs.astral.sh/uv/)（运行 `eidolon` 命令）和 Node.js 22.18 以上（渲染缩略图）。有 `flock`（util-linux，Linux 一般都自带）时脚本会加锁，防止两次同步重叠；没有时（例如 Windows 的 Git Bash）不加锁照常同步。在 Windows 上用 Git Bash 运行 `sh deploy/stand-sync.sh`。
- Playwright 的 Chromium：在 `frontend/` 里 `npm ci`，再 `npx playwright install --with-deps chromium`（`--with-deps` 会用 apt 装上它要的系统库，需要 root；装过一次即可）。没有显卡也能渲染。

在仓库根目录的 `.env` 里填好下面这些（脚本从这里读，环境变量里已有的优先；变量的说明见 `.env.example`）：

```sh
EIDOLON_STAND_S3_ENDPOINT=https://<账户 ID>.r2.cloudflarestorage.com
EIDOLON_STAND_S3_BUCKET=eidolon-stand
EIDOLON_STAND_S3_ACCESS_KEY_ID=...
EIDOLON_STAND_S3_SECRET_ACCESS_KEY=...
# EIDOLON_STAND_S3_REGION=ap-shanghai              # 腾讯云 COS、阿里云 OSS、AWS 要填存储桶所在的地域；R2、MinIO 不用填
# EIDOLON_STAND_S3_ADDRESSING=virtual              # 阿里云 OSS、腾讯云 COS 要填 virtual
```

然后运行：

```sh
deploy/stand-sync.sh
tail -f logs/stand-sync.log   # 另开一个终端看进度
```

整理目录默认是仓库根目录下的 `corpus/stand`（可用 `EIDOLON_STAND_BUILD_PATH` 改到别处，写绝对路径），不进仓库。首次同步要拉取约 250MB（十几分钟）、渲染约 160 张缩略图、上传约 250MB，本机实测渲染 1 分钟左右，上传的时间取决于上行带宽。

以前用过单独的立绘镜像（`shinycolors-spine` 这类目录，里面有 `spine_manifest.json` 和 `assets/`）的话，可以把这两样拷进整理目录的 `source/`，第一次就不用重新下载；镜像里别的偶像和 Q 版小人留着也没关系，衣装清单只收配了 `idol_id` 的角色的私服和演出服。

日志在 `logs/stand-sync.log`（可用环境变量 `EIDOLON_STAND_SYNC_LOG` 改到别处），每次同步以「开始同步立绘素材」开头、以「结束：退出码 N（含义）」结尾，中间是每位角色的卡数和衣装数、渲染了多少张缩略图、上传了多少文件和多少 MB：

| 退出码 | 含义 | 要做什么 |
|---|---|---|
| 0 | 完全成功 | 不用管 |
| 1 | 配置出错：缺存储桶的设置、角色配置有误、从来没拉取成功过等，没有上传 | 看日志里的错误 |
| 2 | 存储桶出错（连不上、密钥不对、没有写权限），这次没传完 | 看日志里存储桶返回的错误（`SignatureDoesNotMatch` 多半是密钥或 `EIDOLON_STAND_S3_REGION` 不对）；已上传的不会重复上传，改好后重新运行即可继续 |
| 3 | 有衣装的缩略图没渲染出来，其余已照常上传 | 看日志里哪几套失败；下次同步会再渲染 |
| 4 | 缺少运行环境：uv、Node.js、frontend 的依赖或 Playwright 的 Chromium | 按日志里的提示装上 |
| 5 | 上一次同步还没结束，这次没有运行 | 不用管 |
| 6 | 没能从 ShinyColorsDB 拉取完新卡，已有的照常同步 | 偶尔一次不用管，下次同步会再拉；连续几周都是 6，看日志里的错误，多半是 ShinyColorsDB 的接口变了。缩略图也失败时退出码是 3，拉取的错误只在日志里 |

原作隔一两周出一次新卡，建议用 cron 每周同步一次，新卡就会自己出现在换衣装面板上；没有新卡时只是问一遍 ShinyColorsDB、列一遍存储桶，一分钟内结束。照「每周自动同步」加一行，和剧情同步错开时间（运行 cron 的用户要能运行 `uv`、`node`，对仓库目录有写权限）：

```cron
47 4 * * 2 /home/you/eidolon-sc/deploy/stand-sync.sh
```

**新增角色**：在 `characters.toml` 里给她配上 `idol_id` 和 `default_outfit`，重新运行 `deploy/stand-sync.sh`（已上传的衣装不会重复上传），再重启后端。

**下架**：收到权利方的要求时，清空存储桶即可。前端加载不到素材，通话层自动退回背景图，不需要改代码或重新部署。之后别再运行同步脚本，也可以把 `EIDOLON_STAND_ASSETS_URL` 清空、重启后端，连换衣装的入口一起去掉。

### 本地开发时怎么看效果

只看通话层的立绘时，不用存储桶：同步过一次之后，用一个开了 CORS 的本地静态服务器直接提供整理目录的 `source/assets`，再把地址指过去：

```sh
npx http-server corpus/stand/source/assets -p 8765 --cors
```

```sh
# .env
EIDOLON_STAND_ASSETS_URL=http://localhost:8765
```

然后重启后端，打开对话页打电话。换一套衣装看效果时，改 `characters.toml` 的 `default_outfit` 再重启后端。这样没有衣装清单和缩略图；要连换衣装一起看，就在本机跑一个 S3 兼容的存储（例如 SeaweedFS：`weed server -s3 -s3.allowedOrigins='*'`，配一个可写的密钥和匿名只读），照上面同步一次，再把 `EIDOLON_STAND_ASSETS_URL` 指向存储桶的地址（例如 `http://localhost:8333/<存储桶>`）。

## 配置 OAuth 应用

任何人都能用 Google 或 GitHub 登录（ADR-0006），登录由后端完成：浏览器跳到 Google 或 GitHub 登录，再回到网站的回调地址。回调地址是：

| 提供方 | 回调地址 |
|---|---|
| GitHub | `https://你的域名/api/auth/github/callback` |
| Google | `https://你的域名/api/auth/google/callback` |

本地开发时把 `https://你的域名` 换成 `http://localhost:3000`（可以另建一个开发用的应用）。

> [!TIP]
> 在仓库根目录运行 `scripts/setup-oauth.sh`，它会一步步打开下面要用的页面，告诉你每一栏填什么，把复制回来的值写进 `.env`，顺带生成 `EIDOLON_SECRET_KEY`、设置开发登录和 Gemini 计费的开关，最后重启后端，并列出用真实账号要验证的几件事。下面是同样的步骤，手动配置时照着做。

**GitHub**：在 [GitHub Developer Settings → OAuth Apps](https://github.com/settings/developers) 点「New OAuth App」，Homepage URL 填 `https://你的域名`，Authorization callback URL 填上表的地址。创建后生成一个 Client secret，把 Client ID 和它分别填进 `.env` 的 `GITHUB_CLIENT_ID`、`GITHUB_CLIENT_SECRET`。登录时只申请读取公开资料和邮箱（`read:user user:email`）；注册不满一年的 GitHub 账号不能登录。

**Google**：在 [Google Cloud Console](https://console.cloud.google.com/) 新建（或选一个）项目：

1. 「Google Auth Platform」（旧称「OAuth 同意屏幕」）里填应用名称和支持邮箱，受众选「外部」，数据访问（作用域）只要 `openid`、`email`、`profile`。测试阶段只有加进测试用户名单的账号能登录，对公众开放前点「发布应用」。
2. 「客户端」（旧称「凭据」）里创建 OAuth 客户端 ID，类型选「Web 应用」，已获授权的重定向 URI 填上表的地址。
3. 把客户端 ID 和客户端密钥填进 `.env` 的 `GOOGLE_CLIENT_ID`、`GOOGLE_CLIENT_SECRET`。邮箱没有验证的 Google 账号不能登录。

改完 `.env` 后 `docker compose -f docker-compose.prod.yml up -d` 让后端生效。打开网址就是登录页：第一次登录的用户要同意隐私政策和使用条款、声明年满 13 岁。登录方式、限额、自带密钥等见 README 的「登录与用户」和「自带密钥」；封禁、查看用量等管理命令也在那里，同样的事也可以在后台里做（见下一节）。

> [!NOTE]
> 对公众开放意味着陌生人的对话和记忆会存在这台服务器上，并交给你配置的第三方服务处理（见网站的隐私政策页）。几点注意：
> - 日志里不记对话原文和记忆原文；备份（见下文「备份」）里有，所以备份是加密的，私钥由你离线保存。
> - 用户可以在设置页删除自己的全部数据，线上立刻彻底删除；已经进入备份的副本最多 30 天后随备份过期清除。
> - 公开部署用 Gemini 向量化时要开计费，见上文「选择向量化服务」。

## 后台

后台是同一个网站上的 `/admin`，只有管理者能进入（ADR-0013）：看板（各项服务是否正常、用量、估算的花费）、配置（模型、key、限额、单价）和用户（搜索、封禁、单独限额、删除）。管理者在后台里看不到任何用户的对话、记忆和制作人档案。其他人看不到入口，访问 `/admin` 和后台接口都得到 404。

### 开启后台

1. 用你自己的 Google 或 GitHub 身份在网站上登录一次。
2. 在服务器上列出用户，找到自己。每个登录方式后面括号里的 `github:12345`、`google:109876543210` 就是它的标识：

   ```sh
   docker compose -f docker-compose.prod.yml exec backend eidolon user list
   ```

3. 填进 `.env` 的 `EIDOLON_ADMINS`，多个用逗号分隔。按登录方式认定，不按邮箱；一位用户绑定的登录方式里有一个在名单里就算管理者。顺便可以填 `EIDOLON_CONTACT`（例如一个邮箱地址）：被封禁的用户登录时，「已被封禁」后面附上它，隐私政策的末尾也显示它。

   ```sh
   EIDOLON_ADMINS=github:12345,google:109876543210
   EIDOLON_CONTACT=admin@example.com
   ```

4. `docker compose -f docker-compose.prod.yml up -d` 重建后端，让它读到新的 `.env`。
5. 刷新设置页，「删除我的全部数据」上方多出「后台」一节，点「进入后台」。

管理者名单只能在 `.env` 里改，后台里不能增减。所有管理者的权限都一样。后台不能封禁或删除管理者（包括自己）；命令行可以封禁管理者，被封禁的管理者也进不了后台（命令行没有删除用户的命令）。

### 后台和 `.env` 的关系

规则只有一条：**后台里改过的项优先于 `.env`**。

- 后台里改的配置存进数据库，不用重启：之后的新回合和新通话就用新值。进行中的通话不受影响，语音合成、语音识别、通话中判断情绪的模型和单次通话的上限都按接通时的配置走到挂断；检索用的判断模型、重排阈值和历史回合数按回合取当时的值，通话里的下一个回合就会用上。
- 保存前会先试调一次（扮演角色和提炼记忆的 LLM 检查流式输出和工具调用，语音合成和语音识别做不花钱的 key 检查，判断模型发一个最小的请求），试不通就不保存，并显示原因。限额这类数字不需要试调。
- 每一项旁边同时显示 `.env` 的值和当前生效的值；key 只显示末 4 位。每一项都可以「恢复成 .env 的值」。
- 一项被后台改过之后，你再改 `.env` 里的同一项并重建容器，**不会生效**。启动日志里会列出生效中的覆盖项：

  ```sh
  docker compose -f docker-compose.prod.yml logs backend | grep "config overrides"
  ```

  想让 `.env` 的值生效，在后台把这一项恢复成 `.env` 的值。
- 重启时每一项覆盖都会再试调一次。试不通（例如那个 key 已经在服务商那边吊销了，或者换过 `EIDOLON_SECRET_KEY` 解不开了）时服务照常启动，这一项改用 `.env` 的值，日志里有一行以 `WARNING: the admin console's override of …` 开头、写明原因的警告，后台把它醒目地标为「覆盖已失效」。覆盖本身保留，直到你在后台修好或恢复它。
- 判断模型的回忆阈值、情绪阈值是针对设置时选用的判断模型的 family（Jev、Clef、Clef-flash）设的：同一 family 里换写法或换版本（例如 `typesafe/jev-1.13` 换成 `jev-1.13` 或 `jev-1.14`），覆盖照常生效；换到别的 family 才失效。不属于任何 family 的模型，名字一变就失效。在后台换判断模型失效时，两个判断阈值的覆盖随之清掉；在 `.env` 里换的，覆盖保留但不生效（回到新模型的默认值），后台标为「覆盖已失效」并说明是为哪个模型设的，启动日志也有一行警告。重排的阈值照旧针对设置时的重排模型：在 `.env` 里换了重排模型，覆盖同样保留但不生效。没有校准过阈值的判断模型按 Jev 的阈值判断，它生效时（启动、后台保存或恢复判断模型时）日志里提醒一次。
- 没有设 `EIDOLON_SECRET_KEY` 时，key 不能加密保存，后台里的各种 key 只能看不能改，其他项照常可以改。

只能在 `.env` 里改、后台里只显示的项：管理者名单、`EIDOLON_SECRET_KEY`、OAuth、域名、WebRTC/TURN、备份、各种路径，以及向量化的服务和模型（换了要运行 `eidolon reembed` 全部重新计算，见上文）。改完照常 `up -d`。

### 后台用不了时

后台和网站是同一个后端，网站能打开、你能登录，后台就能用。万一进不去（例如登录方式出了问题），用户的管理照样可以在服务器上用命令行做，和后台走的是同一段代码：

```sh
docker compose -f docker-compose.prod.yml exec backend eidolon user list                    # 用户、登录方式的标识、是否封禁和备注
docker compose -f docker-compose.prod.yml exec backend eidolon user ban <用户 ID> --note "刷量"  # 备注只有管理者看得到
docker compose -f docker-compose.prod.yml exec backend eidolon user unban <用户 ID>
docker compose -f docker-compose.prod.yml exec backend eidolon user usage <用户 ID>         # 最近 24 小时；7 天、30 天的在后台看
```

命令行不能改配置。要在进不了后台时撤掉后台的全部配置覆盖、回到 `.env`，删掉数据库里的覆盖再重启后端：

```sh
docker compose -f docker-compose.prod.yml exec backend python -c "import os, sqlite3; db = sqlite3.connect(os.environ['EIDOLON_DATABASE_PATH']); db.execute('DELETE FROM config_overrides'); db.commit()"
docker compose -f docker-compose.prod.yml restart backend
```

### 运行记录和封禁名单

- 看板的数字来自运行记录：每个回合、每次通话和其中每一次服务调用各一条，记结果、用了哪家服务和模型、是否自带密钥、用量和延迟，不含任何对话内容。满 90 天自动删除。删除用户后，他的运行记录不再关联到任何人，看板上的历史数字不变。
- 后台删除用户和用户自己删除完全一样。被封禁的用户被删除前，他每个登录方式的标识会做成哈希存进封禁名单，以后用同一身份登录或绑定都被拒绝；名单不会过期，也没法再对应回人，所以「被封禁后删除」的用户不能解封。哈希的密钥由 `EIDOLON_SECRET_KEY` 派生（没设时用普通的 SHA-256），**更换 `EIDOLON_SECRET_KEY`（包括从没有到有）之后名单里的哈希就对不上了**，这些人能重新注册。

### 花费估算用的单价

后台看板按单价估算部署者的 key 花了多少钱。按 tokens 计费的模型，单价来自两份公开的价格目录：后端启动时，以及之后每过一天，会访问 [models.dev](https://models.dev/api.json) 和 [OpenRouter 的模型列表](https://openrouter.ai/api/v1/models) 各拉取一次。遇到没有单价的模型时，最多每 6 小时补拉一次。这些请求只读取公开数据，不带任何用户数据和密钥。

服务器访问不了这两个地址时，看板改用代码里的预设单价估算，预设整理于 2026-10-07。后台「配置」页的单价一节会显示拉取失败的原因，也可以在那里点「立即从目录刷新」重试。按字节计费的语音合成、按秒计费的语音识别，以及目录里没有的模型，始终按预设估算。后台设定的单价优先于目录和预设。

## 升级

等 main 上这次提交的 CI 跑完（GitHub 的 Actions 页面显示通过；镜像只在检查全部通过后才发布），然后：

```sh
git pull
docker compose -f docker-compose.prod.yml pull
docker compose -f docker-compose.prod.yml up -d
```

`git pull` 不能省：人设、`deploy/` 下的脚本和 compose 配置本身都来自仓库，不在镜像里。

CI 在 main 上的每次推送都发布 `:main`（默认用的就是它）和 `:sha-<7 位提交哈希>`，推送 `v1.2.3` 这样的标签时另外发布 `:1.2.3` 和 `:latest`。升级后出了问题，在 `.env` 里把 `EIDOLON_IMAGE_TAG` 设为上一版的 `sha-…`（在仓库的 Packages 页面或 `git log --oneline` 里找），再 `up -d` 即可回滚；之后删掉这一行，回到跟随 main。只回滚镜像不回滚数据库：新版本改过数据库结构时，旧版本不一定能用，回滚前看一眼这次升级的提交说明。

### 镜像的可见性

CI 第一次发布后，GHCR 上的两个包跟随仓库，默认是私有的，服务器拉不下来。到 GitHub 个人主页的 Packages，分别打开 `eidolon-sc-backend` 和 `eidolon-sc-frontend`，在 Package settings 的 Danger Zone 里改成 Public。公开的包不占账号的存储和流量额度，服务器不用登录就能拉取。改成公开后不能再改回私有。注意后端镜像里有 `backend/src` 的全部源代码，前端镜像里有构建后的前端代码：包公开就等于这部分代码公开了，即使仓库还是私有的。

不想公开时，包保持私有，在服务器上用一个只有 `read:packages` 权限的 GitHub 令牌（classic personal access token）登录一次：`echo <令牌> | docker login ghcr.io -u <GitHub 用户名> --password-stdin`。

数据都在持久化的位置，升级不会丢失：

- 数据库（用户及其登录方式、会话、对话、记忆、制作人档案、加密后的自带密钥、最近 24 小时的用量、剧情库，以及后台的配置覆盖、单价、单独限额、封禁名单和最近 90 天的运行记录）和同步下载的原始剧本缓存在 Docker 卷 `eidolon-data` 里；
- 证书在 Docker 卷 `caddy-data` 里；
- 人设、角色资料、头像在服务器上的 `characters/` 目录，剧情库的原始数据在 `corpus/` 目录，活动名对照表是 `deploy/event-names.toml`，同步和备份的日志在 `logs/`（都被 git 忽略，`git pull` 不会动它们）。

不要执行 `docker compose down -v`，`-v` 会删掉这些卷。

## 备份

数据库（用户、对话、记忆、剧情库，全部在一个 SQLite 文件里）由 `deploy/db-backup.sh` 每天备份一次（ADR-0012）：它在后端容器里运行 `eidolon backup`，不用停服务，把整个数据库导出成一个一致的副本、检查完整性、压缩，用 age 公钥加密后上传到一个私有的 S3 兼容存储桶，再删掉 30 天前的备份。最新的一份总是保留，哪怕已经超过 30 天，存储桶不会被删空；当天上传失败时过期的备份也照删。

`characters/` 目录、`deploy/event-names.toml` 和 `.env` 不在备份里，另外自己保存。原始剧本缓存不用备份，丢了只是下一次同步重新下载。

### 第一次配置

1. **建一个私有的存储桶**。推荐 Cloudflare R2（存储费低，下载不收流量费），其他 S3 兼容存储也行，见「选择对象存储」。这个存储桶**不要开公开访问**（R2 不连自定义域名、不开 `r2.dev`），也**不要和立绘共用**：立绘桶是公开可读的，配错一次就会把数据库泄露出去。
2. **建一个只能读写这个存储桶的密钥**。R2：「管理 R2 API 令牌 → 创建 API 令牌」，权限选「对象读和写」，「指定存储桶」只选备份桶。不要复用立绘的令牌。
3. **生成 age 密钥对**，在**你自己的电脑上**，不在服务器上（[age](https://github.com/FiloSottile/age) 或 [rage](https://github.com/str4d/rage) 都行，`apt install age`、`brew install age`、`winget install FiloSottile.age`）：

   ```sh
   age-keygen -o eidolon-backup.key
   # Public key: age1...
   ```

   `age1` 开头的公钥填进服务器的 `.env`；`eidolon-backup.key` 是私钥，**只离线保存**（密码管理器、加密的 U 盘），不要放到服务器上：服务器被攻破，攻击者也解不开历史备份。**私钥丢了，所有备份就都解不开了。**
4. **另外保存 `EIDOLON_SECRET_KEY`**（和私钥放在一起）：用户的自带密钥和后台里保存的 key 是用它加密的，封禁名单也靠它，恢复后没有它就解不开、对不上。
5. **填 `.env`**，然后 `docker compose -f docker-compose.prod.yml up -d` 让后端读到：

   ```sh
   EIDOLON_BACKUP_S3_ENDPOINT=https://<账户 ID>.r2.cloudflarestorage.com
   EIDOLON_BACKUP_S3_BUCKET=eidolon-backups
   EIDOLON_BACKUP_S3_ACCESS_KEY_ID=...
   EIDOLON_BACKUP_S3_SECRET_ACCESS_KEY=...
   EIDOLON_BACKUP_AGE_RECIPIENT=age1...
   EIDOLON_BACKUP_PING_URL=https://hc-ping.com/...   # 可选，见下文「心跳」
   ```

6. **手动备份一次**，确认存储桶里出现了 `eidolon-<UTC 时间>.db.gz.age`：

   ```sh
   deploy/db-backup.sh
   tail logs/db-backup.log
   ```

7. **装 cron**，每天一次。`crontab -e`，加一行（路径换成仓库的实际位置；时间随意，避开整点和剧情同步即可）：

   ```cron
   43 3 * * * /home/you/eidolon-sc/deploy/db-backup.sh
   ```

   运行 cron 的用户要能执行 `docker compose`（root，或在 `docker` 组里），对 `logs/` 有写权限；主机上要有 `flock`（util-linux）。
8. **演练一次恢复**（见下文「从备份恢复」），确认私钥能用、步骤走得通。

手动备份也是运行 `deploy/db-backup.sh`。

### 日志和退出码

日志在 `logs/db-backup.log`（可用环境变量 `EIDOLON_BACKUP_LOG` 改到别处），每次备份以「开始备份数据库」开头、以「结束：退出码 N（含义）」结尾，中间是备份的名字和大小、删掉了哪些过期备份、存储桶里还有几份。看最近几次的结果：

```sh
grep '结束：' logs/db-backup.log | tail
```

| 退出码 | 含义 | 要做什么 |
|---|---|---|
| 0 | 完全成功 | 不用管 |
| 1 | 配置不全：缺存储桶的设置或 age 公钥，或公钥格式不对；没有备份 | 照上面补全 `.env`，`docker compose -f docker-compose.prod.yml up -d` |
| 2 | 导出数据库或完整性检查失败（数据库损坏、磁盘满了），没有上传；过期备份照常删除 | 看日志里的错误。数据库损坏时**不要**等它自己好，尽快从最新的备份恢复 |
| 3 | 上传失败（网络、密钥、存储桶），这次没有备份；过期备份照常删除，最新的一份保留 | 看日志里存储桶返回的错误；网络问题通常下次就好 |
| 4 | 备份已上传，但没能删掉 30 天前的备份 | 通常是令牌没有删除权限，改成「对象读和写」；下次备份会接着删 |
| 5 | 后端容器没有运行，或无法运行备份命令（没有 docker 的权限、找不到 flock 等，原因在日志里） | 容器没有运行时 `docker compose -f docker-compose.prod.yml up -d` |
| 6 | 上一次备份还没结束，这次没有运行 | 不用管 |

日志每天只增加几行，不用轮转。

### 心跳

备份停了（cron 没跑、服务器整台没了）脚本自己没法告诉你。配上 `EIDOLON_BACKUP_PING_URL` 后，每次备份**完全成功**（退出码 0）就访问一次这个地址；在 [healthchecks.io](https://healthchecks.io/) 之类的服务建一个每天一次、宽限几小时的检查，地址填进去，超时没收到就会发邮件提醒你。访问失败只在日志里记一条「注意」，不影响退出码。

### 30 天和删除用户

用户删除自己的数据时，线上数据库里立刻彻底删除；已经做好的备份里的副本，要等这些备份过期才消失，最多 30 天（隐私政策和删除确认里写明了这一点）。这个期限靠每天的备份来执行：cron 停了，或者服务器整台没了，过期的备份就不会再被删，要你自己去存储桶里删掉 30 天前的。

## 从备份恢复

默认用**最新的一份**。回滚到更早的备份，会让这段时间里删除了数据的用户重新出现（他们的对话和记忆会回来），尽量不要这样做；不得已时，恢复后在用户反馈里留意。

1. **下载**：在存储桶里（R2 在网页上就能下载）找到最新的 `eidolon-<UTC 时间>.db.gz.age`，下载到**你自己的电脑上**。
2. **解密、解压**（私钥只在你的电脑上用）：

   ```sh
   age -d -i eidolon-backup.key eidolon-20261003T034300Z.db.gz.age | gunzip > eidolon.db
   sqlite3 eidolon.db 'PRAGMA integrity_check; SELECT count(*) FROM users;'   # 应输出 ok 和用户数
   ```

3. **传到服务器**，例如 `scp eidolon.db 服务器:/tmp/eidolon.db`。
4. **停后端，替换卷里的数据库**，删掉旧的 `-wal`、`-shm`（不删的话，旧的日志会被当成新数据库的一部分）：

   ```sh
   docker compose -f docker-compose.prod.yml stop backend
   docker compose -f docker-compose.prod.yml run --rm --no-deps -v /tmp/eidolon.db:/restore.db:ro      --entrypoint sh backend -c 'rm -f /data/eidolon.db-wal /data/eidolon.db-shm && cp /restore.db /data/eidolon.db'
   docker compose -f docker-compose.prod.yml start backend
   rm /tmp/eidolon.db
   ```

   换了一台新服务器时，先照「部署」把 `.env`（包括原来的 `EIDOLON_SECRET_KEY`）、`characters/` 准备好，`up -d` 一次让卷建出来，再做这一步。
5. **确认**：登录网站，看对话和记忆都在；`docker compose -f docker-compose.prod.yml exec backend eidolon user list` 能列出用户。

建议第一次配好备份后就在本地的 compose（`docker-compose.yml`）上演练一次：步骤一样，只是把 `-f docker-compose.prod.yml` 去掉。

## 排障

- **打不开网站、证书申请失败**：`docker compose -f docker-compose.prod.yml logs caddy`。检查域名的 A 记录是否已经生效、80 和 443 端口是否放行。
- **文字对话正常，语音一直「接通中」然后失败**：先看 `docker compose -f docker-compose.prod.yml logs coturn`。
  - 日志里没有任何来自浏览器的请求：3478 端口（TCP 和 UDP）没有放行。
  - 有 `denied` 或 `Forbidden IP`：`EIDOLON_PUBLIC_IP`（或 `EIDOLON_PRIVATE_IP`）和服务器网卡上的地址对不上，见上方「部署」。
  - 有 `check_stun_auth: Cannot find credentials of user`：`.env` 里的 `EIDOLON_TURN_SECRET` 改过但只重启了其中一个服务，执行一次 `docker compose -f docker-compose.prod.yml up -d` 让两边一致。
- **管理者打开 `/admin` 得到 404，设置页也没有「进入后台」**：`EIDOLON_ADMINS` 里的标识要和 `eidolon user list` 括号里的完全一样（`github:` 或 `google:` 加数字，不是邮箱），改完要 `docker compose -f docker-compose.prod.yml up -d` 重建后端，只 `restart` 读不到新的 `.env`。
- **改了 `.env` 却没生效**：这一项可能被后台覆盖了，见「后台和 `.env` 的关系」。
- **只放行 443 端口的网络里语音连不上**：目前的已知限制。TURN 走 443 需要和 Caddy 分用这个端口，还没有做。
