# 08: 全站加 CSP

**What to build:** 自带密钥存在浏览器里以后，前端一旦出现 XSS，脚本就能读到 key。全站加一个务实版的 CSP：只允许加载本站的脚本、只允许向本站发请求，页面照旧静态渲染，落地页的首屏速度不受影响。严格的 nonce 版不做，原因见 ADR-0017。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] Next 的全局响应头给所有页面加上 CSP，至少包括：`script-src 'self' 'unsafe-inline'; connect-src 'self'; object-src 'none'; base-uri 'self'; form-action 'self'; frame-ancestors 'none'`。其他指令（`default-src`、`img-src`、`media-src`、`font-src`、`worker-src` 等）按实际用到的来源补齐。
- [ ] 页面的渲染方式不变：构建输出里原来是静态的页面，加了 CSP 以后仍然是静态的。
- [ ] 逐项确认没有挡住正常功能：落地页（包括招呼的音频）、登录、对话页、立绘和 Spine、通话（WebRTC、TURN、通话提示音）、后台各页。
- [ ] 票里写好人工验证清单：用构建版前端（`next build` 加 `next start`），实际打一通电话、发一个回合、打开落地页和后台，看浏览器控制台里没有被 CSP 挡掉的请求。
