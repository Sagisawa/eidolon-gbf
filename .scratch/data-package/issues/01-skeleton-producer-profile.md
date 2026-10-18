# 01: 数据包骨架：导出、导入制作人档案

**What to build:** 设置里多了一个「数据包」标签，和「登录方式」放在同一组。用户勾上「制作人档案」点「导出」，浏览器下载一个第 1 版格式的数据包（`manifest.json` 加 `data.json`）。在另一个部署或另一个账号上选这个文件，页面先读出里面有哪几类、列出勾选框，点「导入」后档案整份覆盖，页面显示一句结果。这张票只带制作人档案这一类，但格式、两个接口、同源代理、前端标签页、版本规则、事务都要从头打通，后面几张票往里加类别。见 `../spec.md` 的「数据包的格式」「版本规则」「导出接口」「导入接口」「网络这一路」「前端」几节。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `GET /api/account/data-package?include=profile`：要登录，回 zip，带 `Content-Disposition: attachment` 和带日期的英文文件名。zip 的第一个条目是不压缩的 `manifest.json`（`format: 1`、`exported_at`、`categories`、每类条数），然后是缩进排版、英文键名的 `data.json`。服务器先写临时文件再流式回给浏览器
- [ ] 没设过档案的用户导出时，`profile` 里各项为空（仍算勾了这一类）；`include` 里没有的类别，`data.json` 里没有对应的键，`categories` 里也没有
- [ ] `POST /api/account/data-package?include=profile`：要登录，请求体是 zip 本身，后端边读边写临时文件。`include` 和 `categories` 取交集；勾了档案就整份覆盖，包里没设的项清空、沿用默认
- [ ] 版本规则：`format` 比自己支持的新，回 422、错误码 `too_new`；zip 打不开、有多余条目、JSON 不合格式、时间解析不了，一律回 422、错误码 `broken`。时间解析后按库里的格式写回
- [ ] 导入的所有写入在一个事务里完成，中途出错全部回滚
- [ ] 结果按 spec 的形状回 `{conversations, photos, memories, profile, skipped}`，这张票里只有 `profile` 会有值，其余为 0 或空
- [ ] 导出、导入都不写运行记录，后台看不到；出错只写服务器日志，不带内容
- [ ] 同源代理流式转发请求体（`duplex: "half"`），不再整个读进内存；响应头带回 `content-disposition` 和 `content-length`。代理测试加一条
- [ ] 设置分类加 `data-package`，标签名「数据包」，和「登录方式」同组。导出这一半有四个勾选框，这张票里只有「制作人档案」能用（其余三类留给后面的票，先不显示也行），点「导出」浏览器跳到导出地址下载。下面一行小字说明设备上的设置不在里面
- [ ] 导入这一半：选文件后用一个小的 zip 库流式读出开头的 `manifest.json`，不把整个文件读进内存。读不出来提示坏包，`too_new` 直接提示让部署者升级，否则按 `categories` 列勾选框（默认全选）。点「导入」后 POST 文件，进行中按钮有状态；成功后显示一句结果，并刷新制作人档案
- [ ] 勾选框联动、按 `manifest.json` 列类别、判断 `too_new` 和坏包、结果拼成一句话、错误码对应文案，都放在一个纯函数模块里，有 vitest
- [ ] `docs/` 下新增数据包格式说明的第一版：zip 结构、`manifest.json`、`profile`、版本规则
- [ ] 后端测试（走对外接口）：在部署 A 设档案、导出，到部署 B（另一个 `database_path`）导入，读档案一致；B 上原来设了、包里没设的项被清空；不勾档案时 B 的档案不动；`too_new`、多余条目、坏 zip、时间格式不对都回 422，而且什么也没写进去；没登录不能导出、也不能导入；导出的只是调用者自己的档案
- [ ] 前端纪律检查通过；受影响的测试和类型检查通过（`scripts/affected-tests.sh`），CI 绿
