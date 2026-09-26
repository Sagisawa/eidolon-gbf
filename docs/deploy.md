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

- 模型和各项服务的密钥，和本地开发时一样（见 `.env.example` 里的说明）。至少要有对话模型；语音通话需要 `SONIOX_API_KEY` 和 `FISH_AUDIO_API_KEY`。
- `EIDOLON_DOMAIN`：网站的域名，例如 `eidolon.example.com`。
- `EIDOLON_PUBLIC_IP`：这台服务器的公网 IPv4 地址。coturn 只允许把语音中继到这台服务器（也就是后端），别人拿不到它当开放的中继用。
- `EIDOLON_PRIVATE_IP`：只有公网地址不在网卡上时才填，填网卡上的内网地址。在服务器上执行 `ip -4 addr`：能看到公网地址就不用填（Vultr、DigitalOcean、搬瓦工等大多如此）；只能看到 `10.`、`172.`、`192.168.` 开头的内网地址时（AWS、阿里云、腾讯云等 1:1 NAT 的云主机），填这个内网地址。这种环境还没有实际验证过，语音连不上时请看「排障」。
- `EIDOLON_TURN_SECRET`：coturn 和后端共用的密钥，用 `openssl rand -hex 32` 生成。后端给每位用户签发 24 小时后过期的 TURN 凭据，这个密钥本身不会发给浏览器。

`EIDOLON_ICE_SERVERS`、`EIDOLON_TURN_URLS` 不用填：生产配置会自动用本机的 coturn。

然后准备人设文件（见 README 的「角色」：`characters/sheets/` 下每位角色一份，角色资料和头像可选），启动：

```sh
docker compose -f docker-compose.prod.yml up -d --build
```

第一次启动时 Caddy 会申请证书，稍等片刻后用浏览器打开 `https://你的域名`。后端启动失败时（缺少人设文件、对话模型检查不通过等），用 `docker compose -f docker-compose.prod.yml logs backend` 查看原因。

下面的命令都要带上 `-f docker-compose.prod.yml`。嫌麻烦的话，在这台服务器上执行一次 `export COMPOSE_FILE=docker-compose.prod.yml`（或者写进 shell 的配置文件），之后 README 里的 `docker compose ...` 命令就能原样使用。

## 同步剧情库

剧情库用一条命令同步：先导入 SCTranslationData 的汉化版，再从 ShinyColorsDB 镜像补齐还缺的卡牌剧情、培育剧情和活动剧情（原文剧情，规则见 README 的「剧情库」）。需要 `.env` 里填好 `SILICONFLOW_API_KEY`（向量化用）。

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

运行 cron 的用户要能执行 `docker compose`（root，或在 `docker` 组里），并且对仓库目录有写权限（要写 `corpus/` 和 `logs/`）。脚本自己把输出写进日志，cron 不会发邮件。

日志在 `logs/story-sync.log`（可用环境变量 `EIDOLON_SYNC_LOG` 改到别处），每次同步以「开始同步剧情库」开头、以「结束：退出码 N（含义）」结尾，中间是 git 的输出和同步报告：汉化版新增、更新了多少段（其中多少段取代了原文剧情），原文剧情下载、新增了多少，跳过了多少失败结局，新向量化了多少段，还有需要人工核对的失败嫌疑剧情和没有活动名的活动。看最近几次的结果：

```sh
grep '结束：' logs/story-sync.log | tail
```

| 退出码 | 含义 | 要做什么 |
|---|---|---|
| 0 | 完全成功 | 不用管 |
| 1 | 同步命令出错：配置错误（对照表格式不对、缺少 `SILICONFLOW_API_KEY` 等）或向量化中断 | 看日志里的错误；向量化中断时重新运行即可继续 |
| 2 | 镜像或 API 出错，这次没拉到（全部）原文剧情；汉化版已照常导入 | 通常不用管，下次同步会接着拉取；连续几周都是 2 时看日志里的错误 |
| 3 | git 没能更新 SCTranslationData（网络问题，或本地改动导致不能快进）；有已下载的数据时照常用它同步 | 看日志里 git 的输出，必要时删掉 `corpus/SCTranslationData` 让脚本重新克隆 |
| 4 | 后端容器没有运行，或无法运行同步命令 | `docker compose -f docker-compose.prod.yml up -d` |
| 5 | 上一次同步还没结束（例如首次全量补齐还在跑），这次没有运行 | 不用管 |

同步出错时退出码以 1、2 为准（git 同时出错会写在日志里）。日志每周只增加几十行，不用轮转；太大时直接删掉即可。

额外的参数会传给 `eidolon story sync`，例如 `deploy/story-sync.sh --idol 1` 只同步櫻木真乃的卡和相册，用来试一试。脚本默认用 `docker-compose.prod.yml`，设置了 `COMPOSE_FILE` 时用它指定的配置。

### 缓存与手动导入

下载的原始剧本缓存在后端数据卷里的 `/data/mirror`（和数据库同在 `eidolon-data` 卷里，升级、重建容器都会保留），不进仓库。镜像修正了某个剧本、想重新下载时，删掉缓存里对应的文件即可，例如：

```sh
docker compose -f docker-compose.prod.yml exec backend rm /data/mirror/scripts/produce_events/200100401.json
```

也可以不用同步，手动导入（例如只想导入汉化版，或者有自己导出的游戏剧本 JSON）：

```sh
git clone --depth 1 https://github.com/ShinyGroup/SCTranslationData.git corpus/SCTranslationData
docker compose -f docker-compose.prod.yml exec backend eidolon story import-csv /corpus/SCTranslationData/data/story
# 用游戏原始剧本 JSON 补全（放在 corpus/scripts 下）
docker compose -f docker-compose.prod.yml exec backend eidolon story import-json /corpus/scripts
```

导入的结果存在数据库里。只手动导入时，之后可以删掉 `corpus/` 节省空间；用每周同步时要保留 `corpus/SCTranslationData`，脚本每次只 `git pull` 增量更新。

## 签发访问密钥

```sh
docker compose -f docker-compose.prod.yml exec backend eidolon user create alice
docker compose -f docker-compose.prod.yml exec backend eidolon key issue alice   # 密钥只显示这一次
```

把网址和密钥发给朋友：用手机或电脑打开网址，在设置页填入访问密钥，就能挑一位角色对话、通话。吊销密钥、限额等见 README 的「用户与访问密钥」。

## 升级

```sh
git pull
docker compose -f docker-compose.prod.yml up -d --build
```

数据都在持久化的位置，升级不会丢失：

- 数据库（用户、访问密钥、对话、记忆、剧情库）和同步下载的原始剧本缓存在 Docker 卷 `eidolon-data` 里；
- 证书在 Docker 卷 `caddy-data` 里；
- 人设、角色资料、头像在服务器上的 `characters/` 目录，剧情库的原始数据在 `corpus/` 目录，活动名对照表是 `deploy/event-names.toml`，同步日志在 `logs/`（都被 git 忽略，`git pull` 不会动它们）。

不要执行 `docker compose down -v`，`-v` 会删掉这些卷。

## 备份

数据库是 SQLite，用它自带的在线备份，不用停服务：

```sh
docker compose -f docker-compose.prod.yml exec backend python -c \
  "import sqlite3; sqlite3.connect('/data/eidolon.db').backup(sqlite3.connect('/data/backup.db'))"
docker compose -f docker-compose.prod.yml cp backend:/data/backup.db ./eidolon-backup.db
```

`characters/` 目录和 `deploy/event-names.toml` 另外自己备份。原始剧本缓存不用备份，丢了只是下一次同步重新下载。

## 排障

- **打不开网站、证书申请失败**：`docker compose -f docker-compose.prod.yml logs caddy`。检查域名的 A 记录是否已经生效、80 和 443 端口是否放行。
- **文字对话正常，语音一直「接通中」然后失败**：先看 `docker compose -f docker-compose.prod.yml logs coturn`。
  - 日志里没有任何来自浏览器的请求：3478 端口（TCP 和 UDP）没有放行。
  - 有 `denied` 或 `Forbidden IP`：`EIDOLON_PUBLIC_IP`（或 `EIDOLON_PRIVATE_IP`）和服务器网卡上的地址对不上，见上方「部署」。
  - 有 `check_stun_auth: Cannot find credentials of user`：`.env` 里的 `EIDOLON_TURN_SECRET` 改过但只重启了其中一个服务，执行一次 `docker compose -f docker-compose.prod.yml up -d` 让两边一致。
- **只放行 443 端口的网络里语音连不上**：目前的已知限制。TURN 走 443 需要和 Caddy 分用这个端口，还没有做。
