# 04: 迁移策略

Type: grilling
Blocked by: 02
Status: open

## Question

怎么从 Astryx 迁到 shadcn？是在 `feat/shadcn-redesign` 上一次换完再合并进 main，还是逐页替换、每波合并进 main、两套库短期并存？如果选择并存，靠什么隔离（CSS 层级、按路由分别加载样式）？线上部署（`git push vps`）在迁移期间要保证什么？
