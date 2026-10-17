# 01: 调研：NovelAI 官方图像 API 现状

Type: research
Status: open
Blocked by: none

## Question

以 NovelAI 官方文档和官方发布为准（2026-10），把接图像 API 要知道的事实查清：

- 现在有哪些图像模型（V4.5 Full / Curated 之后有没有更新的），各自的模型标识、适合什么、默认参数；哪些已经下线或不推荐。
- 接入点和鉴权：生成图像的 URL、请求方法、`Authorization` 怎么带（持久 API token 怎么拿），请求体的完整结构，特别是 V4 系列的 `v4_prompt` / `v4_negative_prompt`、多角色描述（char captions）、角色参考图（character reference）、vibe transfer、质量标签和 UC 预设、尺寸、步数、采样器、种子。
- 返回格式（zip 里的 PNG？流式？），错误码和限流的样子。
- 费用：Opus 档免费生成的确切条件（尺寸、步数、张数），超出时扣多少 Anlas；查余额的接口。
- 并发：一个账号能不能同时跑几张，排队还是直接报错。
- 内容：官方有没有内容过滤或安全开关；全年龄要靠我们自己守的话，官方推荐怎么写负面词。
- 条款：Terms of Service 是否允许把一个订阅（或它的 API token）用在面向公众的服务、让多个用户共用；用户自带自己的 token 有没有问题。
- 库：官方有没有 SDK；社区常用的库（例如 Python 的 novelai-python、novelai-api）维护状况如何，值不值得引入，还是直接发 HTTP。
- 模型对《偶像大师 闪耀色彩》角色的认识：官方有没有说明训练数据里的角色 tag 怎么用（danbooru 角色名 tag 的写法）。

结论写成 `.scratch/photos/research/novelai-api.md`，每条事实附出处链接；查不到的明说查不到。
