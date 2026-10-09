# 12: 底座①：换字体，拍基准截图

**What to build:** 全站换上新字体：中文用 Noto Sans SC，她的日语台词用 LINE Seed JP（`next/font`，400/700）。页面结构和颜色都不动。同一个提交里新增截图脚本：参照 `stand-thumbnails.mts` 调用 Playwright Chromium 的写法，连本地真实后端和开发库，每页浅色、深色各拍一张，输出到被 gitignore 的目录。拍好的这套图就是后面底座提交和共用件提交的像素基准。这张 ticket 的提交里**只能有字体和截图脚本**，交付后停下来，请人确认字体效果。

属于第 1 波（底座），规格见 `../spec.md`「五个波次」「Testing Decisions」。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] 中文界面用 Noto Sans SC，`<Ja>` 里的日语用 LINE Seed JP；构建时「没有 fallback 度量」的提示可以忽略
- [ ] 截图脚本能对不依赖实时数据的页面（登录、法务、后台各页的静态部分）拍浅色、深色两套图，输出目录已加入 gitignore；通话层不进脚本
- [ ] 基准图已经拍好，存放位置写进交付说明
- [ ] 验收清单第 1 行：人工确认字体效果（agent 列出要看的页面，交给用户逐页看）
- [ ] `typecheck`、`test` 通过，`next build` 成功
- [ ] 开工前已把 main 合进 `feat/shadcn-redesign`，冲突在分支里解决
