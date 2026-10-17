# 03: 准备测试用的中转地址和 key

Type: task
Status: open
Blocked by: none

## Question

原型「外貌一致性」要真生成图片来看，需要能调用的接入点。用户手上有一个中转（地址和 key），没有官方订阅。

要用户做（HITL）：

1. 在仓库根目录建 `.env.novelai`（`.gitignore` 的 `.env.*` 会挡住它，不会进仓库），写：
   ```
   NOVELAI_RELAY_URL=<中转给的地址>
   NOVELAI_RELAY_KEY=<中转给的 key>
   ```
2. 如果中转给了文档或说明（支持哪些模型、哪种协议），把链接或原文贴进本票 `## Comments`。

然后代理（AFK）用一个最小请求探一下这个中转：是哪种协议（对照「NovelAI 中转的常见协议」）、支持哪些模型、返回什么格式、一张图多久。结果写进 `## Answer`，key 不写进任何文件。
