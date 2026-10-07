# 04: 用真实 key 跑 eval，实测 Cloudflare

**What to build:** 人工拿真实 key 做 agent 做不了的实测，把结果贴回本 ticket 的 Comments，05 据此定数值。

**Blocked by:** 02, 03

**Status:** ready-for-human

- [ ] 审核 `backend/eval/judge.toml` 的期望结果（如果 03 里还没审）。
- [ ] 准备凭证：Cloudflare API token（Workers AI Read + Edit）和 account id（步骤见 `../research.md` 第 8 节）。
- [ ] 启动检查：故意填错 token、填错 account id 各一次，确认报错指向的是对的那一项；再填对的，确认正常启动。
- [ ] `eidolon eval judge` 分别跑 Jev（现有 OpenRouter key）、Clef、Clef-flash，各存一份 JSON。
- [ ] 截断：看长上文用例在 Clef 系列上是否明显变差；也可以看 `usage.input_tokens` 是否被截在约 2K。
- [ ] OpenRouter：用现有的 key，设 `JEV_MODEL=cloudflare/clef-flash` 跑几条，确认 `/systemone` 接不接受。
- [ ] 在 VPS 上测一次到 `api.cloudflare.com` 的延迟（例如跑一次 eval 看平均延迟，或者 curl）。
- [ ] 真实对话：`JUDGE_PROVIDER=cloudflare` 下做几轮文字对话和一次通话，确认闲聊不检索、问起经过会回忆、立绘的情绪会变化。
- [ ] 把三家的汇总、截断结论、OpenRouter 结论和 VPS 延迟写进 Comments。

## Comments
