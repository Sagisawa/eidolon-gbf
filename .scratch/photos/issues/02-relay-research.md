# 02: 调研：NovelAI 中转的常见协议

Type: research
Status: open
Blocked by: none

## Question

国内外常见的 NovelAI 中转（代理转售、聚合 API 平台）对外提供哪几种接法，各自什么样：

- 原样转发 NovelAI 官方接口：只换 base URL 和 key，路径、请求体、返回（zip）都不变？
- OpenAI images 兼容（`/v1/images/generations`）：模型名怎么写，NovelAI 特有的参数（负面词、多角色描述、尺寸、步数、种子）怎么塞，返回 `b64_json` 还是 `url`？
- OpenAI chat 兼容（`/v1/chat/completions`，图片以 markdown 链接或 base64 出现在回复里）？
- 其他常见形态（异步任务 + 轮询等）。
- 鉴权方式（Bearer、自定义头）、错误和限流怎么表现。
- 哪几种最普遍，我们支持哪几种就能覆盖绝大多数中转；中转常见的坑（返回的是临时 URL、会过期，参数被静默忽略等）。

结论写成 `.scratch/photos/research/relays.md`，每条附出处（平台文档链接）；只凭个别帖子的说法要注明。
