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

## 导入剧情库

和本地一样：把剧情数据放在仓库根目录的 `corpus/` 下（它以只读方式挂载到后端的 `/corpus`），然后导入。

```sh
git clone --depth 1 https://github.com/ShinyGroup/SCTranslationData.git corpus/SCTranslationData
docker compose -f docker-compose.prod.yml exec backend eidolon story import-csv /corpus/SCTranslationData/data/story
# 可选：用游戏原始剧本 JSON 补全
docker compose -f docker-compose.prod.yml exec backend eidolon story import-json /corpus/scripts
```

也可以用一条命令同步：先导入汉化版，再从 ShinyColorsDB 镜像补齐缺少的卡牌剧情（首次约一到两小时，镜像连不上时退出码为 2，说明见 README 的「剧情库」）：

```sh
docker compose -f docker-compose.prod.yml exec backend eidolon story sync
```

需要 `.env` 里填好 `SILICONFLOW_API_KEY`。导入的结果存在数据库里，之后可以删掉 `corpus/` 节省空间，原作更新时再重新下载导入。

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

- 数据库（用户、访问密钥、对话、记忆、剧情库）在 Docker 卷 `eidolon-data` 里；
- 证书在 Docker 卷 `caddy-data` 里；
- 人设、角色资料、头像在服务器上的 `characters/` 目录，剧情库的原始数据在 `corpus/` 目录（都被 git 忽略，`git pull` 不会动它们）。

不要执行 `docker compose down -v`，`-v` 会删掉这些卷。

## 备份

数据库是 SQLite，用它自带的在线备份，不用停服务：

```sh
docker compose -f docker-compose.prod.yml exec backend python -c \
  "import sqlite3; sqlite3.connect('/data/eidolon.db').backup(sqlite3.connect('/data/backup.db'))"
docker compose -f docker-compose.prod.yml cp backend:/data/backup.db ./eidolon-backup.db
```

`characters/` 目录另外自己备份。

## 排障

- **打不开网站、证书申请失败**：`docker compose -f docker-compose.prod.yml logs caddy`。检查域名的 A 记录是否已经生效、80 和 443 端口是否放行。
- **文字对话正常，语音一直「接通中」然后失败**：先看 `docker compose -f docker-compose.prod.yml logs coturn`。
  - 日志里没有任何来自浏览器的请求：3478 端口（TCP 和 UDP）没有放行。
  - 有 `denied` 或 `Forbidden IP`：`EIDOLON_PUBLIC_IP`（或 `EIDOLON_PRIVATE_IP`）和服务器网卡上的地址对不上，见上方「部署」。
  - 有 `check_stun_auth: Cannot find credentials of user`：`.env` 里的 `EIDOLON_TURN_SECRET` 改过但只重启了其中一个服务，执行一次 `docker compose -f docker-compose.prod.yml up -d` 让两边一致。
- **只放行 443 端口的网络里语音连不上**：目前的已知限制。TURN 走 443 需要和 Caddy 分用这个端口，还没有做。
