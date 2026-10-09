<!-- BEGIN:nextjs-agent-rules -->

# This is NOT the Next.js you know

This version has breaking changes — APIs, conventions, and file structure may all differ from your training data. Read the relevant guide in `node_modules/next/dist/docs/` (resolved from this file's directory; in monorepos the `next` package may not be visible from the repo root) before writing any code. Heed deprecation notices.

This block is written and re-added by `next dev` — verify at `node_modules/next/dist/server/lib/generate-agent-files.js`. Removing it from a diff only re-creates the uncommitted change; committing it with your work keeps the tree clean.

<!-- END:nextjs-agent-rules -->

## shadcn 纪律（新代码）

前端正在从 Astryx 换成 shadcn/ui（底层 Base UI，样式 `base-nova`）加 Tailwind v4（`.scratch/shadcn-redesign/spec.md`，ADR-0015）。新写和重写的代码守下面这些规则；还没迁移的屏照旧按根目录 `AGENTS.md` 的 Astryx 说明。视觉规范以根目录 `DESIGN.md` 为准。

- **布局**：直接写 `<div>` 加 Tailwind 类，不自写 `Stack`/`Row` 原语。同样的结构在两屏以上出现、并且能用 `GLOSSARY.md` 或 `DESIGN.md` 里的词叫出名字，才抽成项目组件。
- **颜色**：只用具名主题变量。`--her-*`、挂断红等固定色在 `src/app/globals.css` 的 `@theme inline` 里注册成 Tailwind 颜色（`bg-her-wall`、`bg-hangup`）。任意值里不准出现颜色（`[var(--…)]`、hex、oklch、rgb、hsl 都不行）。新增固定色写进对比度测试（`src/theme/themeContrast.test.ts`）。
- **尺寸**：`DESIGN.md` frontmatter 里有名字的值（字号层级、气泡圆角、头像等）注册成 `@theme` token（如 `text-header`、`text-meta`、`rounded-bubble`），必须用 token。间距只用 Tailwind 刻度。任意值只用于一次性的布局约束（`max-w-[min(30rem,72vw)]`、`grid-cols-[…]`、`h-[80%]`）。
- **`components/ui/` 直接改**（Own-the-Source），改处加 `// eidolon: <原因>`。`shadcn add` 不带 `--overwrite`，更新组件先看 diff。
- **调用处不改外观**：调用处的 className 只管定位和排布。外观要变就到 `ui/` 组件加 variant/prop 或改那条带条件的类；禁止 `!` important；`group-data-[…]` 盖不住的情况同样这样处理。
- **目录和命名**：项目共用件放 `components/app/`，后台的放 `components/app/admin/`，文件名与旧版相同（PascalCase），新旧靠目录区分；清理波只删旧文件，不搬家不改名。各屏自己的组件（`conversations/`、`admin/` 下）在所属那一波就地重写。`ui/` 用 shadcn 的 kebab-case。
- **`cn`** 一律从 `@/lib/utils` 导入，`shadcn add` 生成的 `from "cn"` 当场改掉。
- **她的颜色**：用 `herVars(官方色)` 注入对话子树（覆盖 `--primary`、`--primary-foreground`、`--ring` 和 `--her-*`），不写进主题或 `:root`。浮层（Dialog、DropdownMenu、Drawer）渲染到 body，需要她的颜色时把 Content 的 `container` 指到子树里。选中状态一律中性 `bg-muted`。
- **机器检查**：不装 ESLint。`sh scripts/check-discipline.sh` 拦下 `from "cn"`（`lib/utils.ts` 除外）、任意值里的颜色（`-\[(#|oklch|rgb|hsl|var\(--)`）和 important 类（`!mt-2`、`hover:!bg-x`、`mt-2!`），CI 前端 job 在 `theme:check` 之后跑它。字号、圆角任意值的界线交给代码审查。
- **shadcn CLI**：本机 npm 全局配置了 `allow-scripts`，CLI 会报 `EALLOWSCRIPTS`；用 `NPM_CONFIG_USERCONFIG` 指向一份不带它的临时 npmrc 再跑 `npx shadcn@latest add …`。
