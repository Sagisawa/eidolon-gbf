// 落地页的验收脚本（.scratch/landing-page/spec.md「Testing Decisions」第 5 条）：人工运行，不进 vitest。
// 沿用原型分支的测量脚本（prototype/landing-page 的 scripts/landing-prototype-measure.mjs）。
//
//   npm run build && BACKEND_URL=http://localhost:8000 npm run start   # 构建版，不用 dev
//   node scripts/landing-check.mjs [origin] [runs]                      # 默认 http://localhost:3000，3 轮
//
// 检查这几项，全部通过时退出码为 0：
//   1. `/` 的分流：不带会话是落地页；带有效会话重定向到 `/conversations`；带过期会话仍是落地页。
//      `/about` 带有效会话不重定向，入口是「继续」，链到 `/conversations`；canonical 指向 `/`。
//      有效会话用开发登录取（后端要开 EIDOLON_DEV_LOGIN=1，会建一位叫 landing-check 的用户），
//      或者把一个有效会话的 cookie 值放进环境变量 LANDING_SESSION。两者都没有时跳过这几项。
//   2. 手机 4G 节流下的 LCP 不超过 2.5 秒（取几轮的中位数），LCP 元素是标题文字（#lp-title）。
//   3. 落地页自身的首屏 JS 压缩后不超过 50 KB，不含框架基线。基线是 `.next/build-manifest.json` 的
//      rootMainFiles 和 polyfillFiles（每页都有的 Next + React，约 161 KB），所以要对着这份构建跑；
//      测别处的部署时用 LANDING_MANIFEST 指向那份构建的 build-manifest.json。
//
// 节流照 Lighthouse 移动端默认：RTT 150 ms、下行 1.6 Mbps、上行 750 Kbps、CPU 4 倍降速；
// 视口 390×844、DPR 3、触屏。每轮新开上下文，不带缓存。

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { chromium } from "playwright";

const origin = (process.argv[2] ?? "http://localhost:3000").replace(/\/$/, "");
const runs = Number(process.argv[3] ?? 3);
const LCP_BUDGET_MS = 2500;
const OWN_JS_BUDGET_KB = 50;

const frontend = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const manifestPath = process.env.LANDING_MANIFEST ?? path.join(frontend, ".next", "build-manifest.json");

const results = [];
function report(name, ok, detail) {
  results.push({ name, ok });
  console.log(`${ok === null ? "跳过" : ok ? "通过" : "失败"}  ${name}${detail ? `：${detail}` : ""}`);
}

const browser = await chromium.launch();

// —— 1. 分流

/** 打开 `pathname`，返回最后停在哪个地址、是不是落地页、右上角入口。 */
async function visit(context, pathname) {
  const page = await context.newPage();
  await page.goto(`${origin}${pathname}`, { waitUntil: "domcontentloaded" });
  const url = new URL(page.url());
  const isLanding = (await page.locator("#lp-title").count()) > 0;
  const entry = isLanding ? page.locator(".lp-top a, .lp-top button").first() : null;
  const seen = {
    path: url.pathname,
    isLanding,
    entryText: entry ? (await entry.innerText()).trim() : null,
    entryHref: entry ? await entry.getAttribute("href") : null,
    canonical: isLanding ? await page.locator('link[rel="canonical"]').getAttribute("href").catch(() => null) : null,
  };
  await page.close();
  return seen;
}

/** 一个带有效会话的上下文；拿不到时是 null。 */
async function signedInContext() {
  const context = await browser.newContext();
  if (process.env.LANDING_SESSION) {
    await context.addCookies([{ name: "eidolon_session", value: process.env.LANDING_SESSION, url: origin }]);
    return context;
  }
  const res = await context.request.post(`${origin}/api/auth/dev-login`, {
    data: { name: "landing-check" },
    headers: { origin },
  });
  if (res.ok()) return context;
  await context.close();
  return null;
}

{
  const visitor = await browser.newContext();
  const seen = await visit(visitor, "/");
  report("不带会话打开 /，是落地页", seen.path === "/" && seen.isLanding, `停在 ${seen.path}`);
  report("访客的入口是「登录」", seen.entryText === "登录", seen.entryText ?? "没有入口");
  const about = await visit(visitor, "/about");
  report("/about 的 canonical 指向 /", about.canonical === "/" || about.canonical === `${origin}/`, about.canonical ?? "没有");
  await visitor.close();

  const expired = await browser.newContext();
  await expired.addCookies([{ name: "eidolon_session", value: "landing-check-expired", url: origin }]);
  const stale = await visit(expired, "/");
  report("带过期会话打开 /，仍是落地页", stale.path === "/" && stale.isLanding, `停在 ${stale.path}`);
  await expired.close();

  const user = await signedInContext();
  if (user) {
    const home = await visit(user, "/");
    report("带有效会话打开 /，重定向到 /conversations", home.path === "/conversations", `停在 ${home.path}`);
    const back = await visit(user, "/about");
    report(
      "带有效会话打开 /about，不重定向，入口是「继续」，链到 /conversations",
      back.path === "/about" && back.entryText === "继续" && back.entryHref === "/conversations",
      `停在 ${back.path}，入口「${back.entryText}」→ ${back.entryHref}`,
    );
    await user.close();
  } else {
    report("带有效会话的分流", null, "后端没开开发登录，也没有 LANDING_SESSION");
  }
}

// —— 2、3. 手机 4G 下的 LCP 和首屏 JS

let baseline = null;
try {
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  baseline = new Set([...manifest.rootMainFiles, ...manifest.polyfillFiles].map((f) => `/_next/${f}`));
} catch {
  console.log(`（读不到 ${manifestPath}，量不了落地页自身的首屏 JS）`);
}

const measures = [];
for (let n = 0; n < runs; n++) {
  const context = await browser.newContext({
    viewport: { width: 390, height: 844 },
    deviceScaleFactor: 3,
    isMobile: true,
    hasTouch: true,
  });
  const page = await context.newPage();
  const cdp = await context.newCDPSession(page);
  await cdp.send("Network.enable");
  await cdp.send("Network.setCacheDisabled", { cacheDisabled: true });
  await cdp.send("Network.emulateNetworkConditions", {
    offline: false,
    latency: 150,
    downloadThroughput: (1.6 * 1024 * 1024) / 8,
    uploadThroughput: (750 * 1024) / 8,
  });
  await cdp.send("Emulation.setCPUThrottlingRate", { rate: 4 });

  const requests = new Map();
  cdp.on("Network.requestWillBeSent", (e) => requests.set(e.requestId, { url: e.request.url, t: e.timestamp }));
  cdp.on("Network.responseReceived", (e) => {
    const r = requests.get(e.requestId);
    if (r) r.type = e.type;
  });
  cdp.on("Network.loadingFinished", (e) => {
    const r = requests.get(e.requestId);
    if (r) r.bytes = e.encodedDataLength;
  });

  await page.addInitScript(() => {
    window.__lcp = [];
    new PerformanceObserver((list) => {
      for (const e of list.getEntries()) window.__lcp.push({ t: e.startTime, id: e.element?.id ?? null, text: e.element?.textContent?.slice(0, 30) });
    }).observe({ type: "largest-contentful-paint", buffered: true });
  });

  await page.goto(`${origin}/`, { waitUntil: "load", timeout: 120000 });
  await page.waitForTimeout(1500);
  const lcp = (await page.evaluate(() => window.__lcp)).at(-1) ?? null;
  const loadEnd = await page.evaluate(() => performance.getEntriesByType("navigation")[0].loadEventEnd);

  // 首屏 JS = load 事件之前请求的脚本；之后的（空闲时加载的光层、点了才加载的登录面板）不算。
  const all = [...requests.values()];
  const loadAt = Math.min(...all.map((r) => r.t)) + loadEnd / 1000;
  const initial = all.filter((r) => r.type === "Script" && r.bytes && r.t <= loadAt);
  const own = baseline ? initial.filter((r) => !baseline.has(new URL(r.url).pathname)) : [];
  const kB = (xs) => +(xs.reduce((a, r) => a + r.bytes, 0) / 1024).toFixed(1);
  measures.push({ lcp, initialKB: kB(initial), ownKB: kB(own), own: own.map((r) => new URL(r.url).pathname) });
  await context.close();
}
await browser.close();

const sorted = [...measures].sort((a, b) => (a.lcp?.t ?? Infinity) - (b.lcp?.t ?? Infinity));
const median = sorted[Math.floor(sorted.length / 2)];
const lcpMs = median.lcp?.t ?? NaN;
report(`手机 4G 下的 LCP 不超过 ${LCP_BUDGET_MS} ms（${runs} 轮的中位数）`, lcpMs <= LCP_BUDGET_MS, `${lcpMs.toFixed(0)} ms`);
report(
  "LCP 元素是标题文字",
  measures.every((m) => m.lcp?.id === "lp-title"),
  measures.map((m) => m.lcp?.id || m.lcp?.text || "无").join("、"),
);
if (baseline) {
  const ownKB = Math.max(...measures.map((m) => m.ownKB));
  report(
    `落地页自身的首屏 JS 不超过 ${OWN_JS_BUDGET_KB} KB（压缩后，不含框架基线）`,
    ownKB <= OWN_JS_BUDGET_KB,
    `${ownKB} KB，整页 ${measures[0].initialKB} KB；${measures[0].own.join(" ")}`,
  );
} else {
  report("落地页自身的首屏 JS", null, "没有框架基线");
}

process.exit(results.some((r) => r.ok === false) ? 1 : 0);
