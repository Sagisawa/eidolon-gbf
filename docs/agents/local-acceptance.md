# 本地用 Playwright 验收

票里写「本地构建版上用 Playwright 验收」时照这里做。验收脚本是一次性的：放在 `frontend/scripts/_accept-*.mts`（这样才找得到 `playwright` 包），用 `node` 跑，验完删掉，不提交（规格「组件不写测试」）。截图写到 `.scratch/_accept/`，同样用完删掉。

## 起服务、停服务

前端跑构建版，不跑 `next dev`（dev 模式会卡）：

```sh
# 后端（:8000），.env 里要有 EIDOLON_DEV_LOGIN=1
cd backend && uv run --quiet --env-file=../.env eidolon serve
# 前端（:3000），在 frontend/ 下，先 npm run build
BACKEND_URL=http://localhost:8000 EIDOLON_STAND_ASSETS_URL=<同 .env> npm run start
```

两个都放后台跑。`EIDOLON_STAND_ASSETS_URL` 不带就看不到立绘（CSP 只许从这个地址加载）。停服务时，结束后台任务不够：`next start` 的子进程还占着 :3000，重新构建后它会继续服务旧页面。要按端口找到进程再结束（PowerShell：`Get-NetTCPConnection -LocalPort 3000 -State Listen` 拿 `OwningProcess`，再 `Stop-Process`），:8000 同理。改了前端代码要先停 :3000，再 `npm run build`，再起。

耗时长的活（`next build`、Playwright、后端完整 pytest）不要和别的 agent 同时跑，否则会卡住，一次只跑一个。

## 登录

用开发登录按名字登录。本地库里 `Sallyn` 是管理者。请求要带 `Origin`，后端会检查：

```ts
await context.request.post(`${origin}/api/auth/dev-login`, { data: { name: "Sallyn" }, headers: { origin } });
```

`frontend/scripts/screenshots.mts` 的 `signIn` 也是这么写的。

## 通话

Chromium 用假麦克风，上下文给麦克风权限：

```ts
const browser = await chromium.launch({
  args: ["--use-fake-ui-for-media-stream", "--use-fake-device-for-media-stream"],
});
const context = await browser.newContext({ viewport, permissions: ["microphone"] });
```

- 本地后端接不通：拨出去以后一直停在「正在呼叫…」。需要「通话中」的检查，都可以拿呼叫中代替（通话条、换页不挂、确认框）。接通后她的声音听起来怎么样，只能在真机上打电话听，在验收报告里留给用户。
- 页首电话键在对话打开前是禁用的，先等它可点再点：

  ```ts
  await page.waitForFunction(() => !document.querySelector('button[aria-label="和櫻木真乃通话"]')?.hasAttribute("data-disabled"));
  ```

- 通话层滑上来要 410ms，量位置、截图前先等一下。
- `page.goto` 是整页重载，会挂断通话。通话中换页要点页面上的链接和按钮（客户端跳转）。

### 造出结束卡

通话「因故结束」在本地也造得出来：拦下建立通话的请求 `/api/offer`，换成后端拒绝时的回答。

| 回答 | 结束卡 |
| --- | --- |
| `429`，`{"detail": "…"}` | 超限额（主操作「去设置自带密钥」） |
| `403`，`{"detail": "…", "own_llm_required": true}` | 必须自带 LLM |
| 其他错误状态 | 没接通（主操作「重拨」） |

先把请求挂起不回，等换到别的页面再放行，就能造出「在别的页面上因故结束」：

```ts
let held: Route | null = null;
await page.route("**/api/offer", (route) => void (held = route));
// …拨号、收起通话层、换到设置…
await held!.fulfill({ status: 429, contentType: "application/json", body: JSON.stringify({ detail: "这一小时的通话次数用完了" }) });
```
