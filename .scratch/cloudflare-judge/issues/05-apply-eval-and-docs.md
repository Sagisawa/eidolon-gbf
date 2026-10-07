# 05: 按 eval 结果定数值，更新文档

**What to build:** 把 04 的实测结论落进代码和文档。

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] 阈值表填上按 eval 定的数值：各模型的三个检索阈值和情绪最低概率。在本 ticket 的 Comments 里写明每个数是怎么从分布里选出来的。
- [ ] `CLOUDFLARE_JUDGE_MODEL` 的默认值按结果确定（`clef-flash`，或者在它的检索判断明显不行时改成 `clef`）。
- [ ] 如果 04 确认会截断：所有服务商的 state 都把「制作人最新的一句话」放在最前面，重跑 Jev 和 Clef 的 eval，确认没有变差，并把前后对比写进 Comments。没有截断就不动。
- [ ] `.env.example` 和三份 README（`README.md`、`README.en.md`、`README.ja.md`）：
  - `JUDGE_PROVIDER` 怎么选；
  - Cloudflare 的凭证怎么拿；
  - 两款模型的区别和价格；
  - 免费额度大约够多少次判断，公开部署应开 Workers Paid；
  - 情绪变量改了名；
  - 如果 04 确认 OpenRouter 可行，写明改 `JEV_MODEL=cloudflare/clef-flash` 也能用上 Clef（没有免费额度）；
  - 致谢里加上 Cloudflare。
- [ ] 全部测试通过，pyright 和 ruff 无错误。
