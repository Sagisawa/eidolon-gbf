# 05: 导入的防滥用上限

**What to build:** 导入有三道上限，用户碰到时各看到一句清楚的提示：数据包超过 200 MB 时马上被告知太大了（不等传完），并提示可以不带照片重新导出；同一时间已经有一个导入或导出在进行时，第二个被告知正在进行；当天（北京时间）已经成功导入 3 次时，被告知几点以后可以再导。见 `../spec.md` 导入接口里的「上限」和「网络这一路」里的 Caddy 一条。

**Blocked by:** 01

**Status:** ready-for-agent

- [ ] 后端边读请求体边数字节，超过 200 MB 立刻回 413；请求头的 `Content-Length` 已经超了的，一开始就回 413。`manifest.json` 和 `data.json` 解压后各自也有上限，超了按 `broken` 处理
- [ ] Caddy 只给导入这一个地址加 `request_body max_size 200MB`，别的不动；部署文档写明自己配反向代理的部署者也要放开这个地址
- [ ] 同一位用户同一时间只能有一个导入在跑，第二个回 409、错误码 `busy`；导出也一样（导出不限次数）。用进程里的按用户的锁
- [ ] 每天（北京时间，用 `affinity.day_of` 划天）最多成功导入 3 次：只有成功的才算，全部去重、什么也没新加的也算；坏包、太大、`too_new`、`busy` 不算。超了回 429，带 `retry_at`（下一个北京时间 0 点），照现有的 `OverLimit` 回法
- [ ] 记次数的新表按用户记每次成功导入的时间，登记进用户数据，删用户时一起删；后台不显示
- [ ] 200 MB、3 次写成常量，不进后台配置
- [ ] 前端：太大（前端选文件时就能按文件大小先拦一次）、`busy`、次数用完（带几点）各一句提示，放进票 01 的纯函数模块，有 vitest
- [ ] 后端测试（走对外接口，上限在测试里调小，不造真的 200 MB）：超过上限回 413 且什么也没写；第二个并发导入回 409；第 4 次成功导入回 429 并带下一个北京时间 0 点，过了 0 点又能导；失败的导入不占次数；删用户后导入次数表里没有他的行
- [ ] 受影响的测试和类型检查通过（`scripts/affected-tests.sh`），CI 绿

## Comments

### 票 01 交接

- 导入路由（`data_package_api.import_data_package`）现在边读 `request.stream()` 边写临时文件，没有计数：在那个循环里数字节、超了回 413；`Content-Length` 先查一次。
- 失败文案在 `zh.ts` 的 `copy.settings.dataPackage.failures`，按后端回的 `code` 取（`ApiError.code`，`importFailureMessage`）；`busy`、太大、次数用完照这个加。429 的 `retry_at` 已由 `api.ts` 的 `json()` 拼进 message，但 `importFailureMessage` 认得 `code` 时会换掉它，次数用完那句要自己带时刻。
- 导出目前不限并发；锁加在 `DataPackages` 外面还是里面自己定。
