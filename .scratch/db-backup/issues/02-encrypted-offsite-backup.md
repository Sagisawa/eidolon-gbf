# 02: 数据库每天加密备份到私有存储桶

**What to build:** 部署者配好一个私有的 R2 存储桶和 age 公钥、装好 cron 以后，数据库每天自动加密备份到云端，保留 30 天；手动备份就是运行同一个脚本。用户在隐私说明和删除确认里能看到「备份中的副本最多 30 天后清除」。见 `../spec.md` 和 ADR-0012。

**Blocked by:** 无

**Status:** ready-for-agent

### `eidolon backup`

- [ ] 用 `VACUUM INTO`（或在线备份 API）把数据库导出成一个一致的临时副本，不停服务；对副本跑 `PRAGMA integrity_check`，不是 `ok` 就不上传、以失败退出
- [ ] 压缩后用 age 公钥加密（选一个能在镜像里用的实现：Python 库或 `age` 可执行文件，写明理由），上传到 `EIDOLON_BACKUP_S3_*` 配置的存储桶，对象名里带 UTC 时间戳；临时文件无论成败都删掉
- [ ] 删掉 30 天前的备份：上传失败也照删，但永远保留最新的一份。`eidolon.s3.Bucket` 补上删除对象，列出对象时要有最后修改时间，或者按对象名里的时间戳来判断
- [ ] 成功后，配了 `EIDOLON_BACKUP_PING_URL` 就访问一次；访问失败只记警告，不改变退出码
- [ ] 退出码分别对应：成功、配置不全、导出或完整性检查失败、上传失败、删除过期备份失败。和 `story sync`、`stand` 的风格一致
- [ ] 测试：用假的 S3（或 `httpx.MockTransport`）覆盖上传、删除过期备份、保留最新一份（只剩超过 30 天的备份时也不删）、完整性检查失败时不上传；生成的备份文件用测试私钥能解密、解压，打开以后数据和原库一致

### `deploy/db-backup.sh`

- [ ] 照 `deploy/story-sync.sh` 的写法：`docker compose exec -T backend eidolon backup`，输出追加到 `logs/db-backup.log`（日志里以「==== 开始」「==== 结束：退出码 N（含义）」包住每次运行），`flock` 防重叠，`PYTHONIOENCODING=utf-8`，后端没在运行时以单独的退出码结束

### 配置与文档

- [ ] `.env.example` 加上 `EIDOLON_BACKUP_S3_ENDPOINT/BUCKET/ACCESS_KEY_ID/SECRET_ACCESS_KEY/REGION`、age 公钥、`EIDOLON_BACKUP_PING_URL`，注释说明存储桶必须是私有的，不要和立绘共用
- [ ] `docs/deploy.md`「备份」一节重写：建 R2 私有存储桶和只能读写它的 API 令牌、生成 age 密钥对（私钥离线保存，丢了备份就全废了）、另外保存 `EIDOLON_SECRET_KEY`、每天一次的 crontab、退出码表、心跳；新增「从备份恢复」：下载、在自己的机器上解密、停后端、替换卷里的 `eidolon.db` 并删掉 `-wal`/`-shm`、启动，建议首次配置后演练一次，写明回滚到更早的备份会让这段时间里删除了数据的用户重新出现
- [ ] 隐私说明（`frontend/src/app/privacy/page.tsx`）和删除用户的确认（`DeleteAccount.tsx`）写明：线上数据立刻彻底删除，备份中的副本最多 30 天后清除
- [ ] 三份 README 的部署和特性说明补上一句备份

### 人工验收

- [ ] 用真实的 R2 存储桶跑一次 `deploy/db-backup.sh`，桶里出现备份；在本机用私钥解密、解压，用 `sqlite3` 打开能看到用户和剧情；照 deploy.md 恢复到本地的 compose 一次
