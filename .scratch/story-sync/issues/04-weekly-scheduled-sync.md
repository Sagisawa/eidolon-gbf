# 04: 每周定时同步的部署

**What to build:** 管理员按部署文档装好一次后，服务器每周自动更新 SCTranslationData 并运行同步，结果追加到日志；不用再手动重新克隆和分两步导入。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] 生产环境的 compose 为原始剧本缓存目录和活动名对照表增加挂载，缓存在容器重建后保留
- [ ] 新增定时脚本：`git pull` SCTranslationData（目录不存在时先克隆），然后通过 `docker compose exec` 运行 `eidolon story sync`，输出和退出码追加到日志
- [ ] `docs/deploy.md` 说明如何安装主机上的 cron（每周一次），首次全量补齐大约需要一到两小时，以及日志在哪里看
- [ ] `docs/deploy.md` 中原来「手动克隆再导入」的步骤改为指向同步命令，保留手动导入作为备用
- [ ] 在本地用 compose 走通一次：先同步出原文剧情，再放入对应的汉化版 CSV 重新同步，确认汉化版取代了原文剧情
