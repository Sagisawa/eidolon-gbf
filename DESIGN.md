---
name: Eidolon-SC
description: 和 283 事务所的偶像说说话。制作人的手帐：冷白复印纸，天蓝横线，事务所深蓝墨水，她的印象色。
colors:
  office-ink: "#1c2a4a"
  office-ink-night: "#a9c6f5"
  night-ink: "#e3e9f5"
  copy-paper: "#fbfcfe"
  night-paper: "#14171d"
  night-surface: "#1f232c"
  popover-white: "#ffffff"
  night-popover: "#262b36"
  sky-rule: "#d6e6fb"
  night-rule: "#243049"
  margin-line: "#8bbaeb"
  night-margin-line: "#3a5580"
  pencil-grey: "#5d6b85"
  night-pencil-grey: "#9aa6bd"
  hang-up-red: "#c8283c"
  night-overlay-edge: "#61799c"
typography:
  title:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 600
  body:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 400
  japanese-line:
    fontFamily: "M PLUS 1p, Noto Sans SC, system-ui, sans-serif"
    fontSize: "1.0625rem"
    fontWeight: 400
  status:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "0.875rem"
    fontWeight: 500
    fontFeature: "\"tnum\" 1"
  label:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
rounded:
  inner: "6px"
  element: "12px"
  container: "18px"
  page: "42px"
  full: "9999px"
spacing:
  "0-5": "2px"
  "1": "4px"
  "1-5": "6px"
  "2": "8px"
  "3": "12px"
  "4": "16px"
  "5": "20px"
  "6": "24px"
  "8": "32px"
  "12": "48px"
components:
  conversation-header:
    backgroundColor: "{colors.copy-paper}"
    textColor: "{colors.office-ink}"
    typography: "{typography.title}"
    padding: "12px 16px"
  bubble-producer:
    backgroundColor: "{colors.office-ink}"
    textColor: "{colors.copy-paper}"
    typography: "{typography.body}"
  bubble-producer-night:
    backgroundColor: "{colors.office-ink-night}"
    textColor: "{colors.night-paper}"
  bubble-her:
    textColor: "{colors.office-ink}"
    typography: "{typography.japanese-line}"
  call-button:
    rounded: "{rounded.full}"
  call-note:
    textColor: "{colors.office-ink}"
    typography: "{typography.status}"
    padding: "8px 20px"
  call-round-control:
    rounded: "{rounded.full}"
    size: "64px"
  call-hang-up:
    backgroundColor: "{colors.hang-up-red}"
    textColor: "{colors.popover-white}"
    rounded: "{rounded.full}"
    size: "64px"
  conversation-list-column:
    backgroundColor: "{colors.copy-paper}"
    width: "320px"
---

# Design System: Eidolon-SC

## Overview

**Creative North Star: "The Producer's Notebook"（制作人的手帐）**

界面是制作人在 283 事务所用的本子。纸是冷白的复印纸，不是奶油纸；消息区铺着天蓝横线和一条更深的装订边距线；制作人的字只用一种墨水，事务所深蓝。属于她的一切（她的气泡、选中行、便利贴、电话键、头像描边、通话层）都用她的印象色，而且只用 `frontend/src/lib/imageColor.ts` 按明暗两种模式推导并校验过对比度的那一套颜色。

系统建立在 Astryx（v0.6）之上：主题 `eidolon-notebook`（源文件 `frontend/src/theme/notebookTheme.ts`，经 `npm run theme:build` 预构建到 `frontend/src/theme/built/`）钉死纸面、墨水和横线颜色，替换图标为 Lucide，并修补 Astryx 默认值在某一模式下不达标的地方；她的颜色不在主题里，而是由 `herVars()`（`frontend/src/theme/herVars.ts`）注入到单个对话的子树。组件形状沿用 Astryx 默认，只换颜色。纸感克制：没有纹理、没有手绘图标、没有手做的气泡尾巴。

通话层是本子上展开的一整张她颜色的纸：她的背景图全幅铺开，上面压一层从她的颜色到深色的纱，白字才读得清；没有背景图时就是一整张渐变，头像背后透一点原色。配了立绘的角色，她本人站在这张纸上：手机上从底部升起，电脑上铺满整层、字幕放进底部的对话框，像原作剧情那样。收起后，页首留一张略斜的便利贴。状态靠线形表达，不靠绿条或徽标。

**Key Characteristics:**
- 冷白复印纸 + 天蓝横线（32px 行距）+ 装订边距线，只铺在消息区。
- 一种墨水：正文、制作人气泡、主题强调色都是事务所深蓝。
- 她的颜色成对取用（light/dark），每一对都有对比度契约测试。
- Astryx 默认形状，颜色覆盖；Lucide 图标注册到 Astryx 语义名。
- 线形状态：实线 = 通话中，虚线 = 正在呼叫，删除线 = 已结束。
- 日语原文大一号、用 M PLUS 1p；中文字幕小一号跟在下面。

## Colors

冷调的纸与墨水构成全部中性色；唯一的彩色是当前这位偶像的印象色，按对话局部注入。

### Primary
- **Office Navy Ink（事务所深蓝墨水）**（`office-ink`）：浅色模式的 `--color-accent` 与 `--color-text-primary`。所有正文、标题、制作人气泡的底色都是它。主题把它钉死，因为 Astryx 生成的色板会把强调色提亮。
- **Night Periwinkle Ink（夜间墨水）**（`office-ink-night`）：深色模式的 `--color-accent`，因此也是深色模式下制作人气泡的底色（上面的字用 `night-paper`）。
- **Night Ink（夜间正文）**（`night-ink`）：深色模式的 `--color-text-primary`。

### Secondary: 她的印象色（per character, derived）
不是固定色值，而是 `imageColorScale(官方色)` 从 `characters.toml` 的印象色推出的一组 light/dark 成对颜色（保持色相，按 OKLCH 调明度与彩度，逐对校验 WCAG 对比度）。经 `herVars()` 以 `light-dark()` 注入（`--her-call-*` 除外：通话层永远是深色，只注入一份）：

- **paper**（`--her-paper`，同时覆盖 `--color-accent-muted`）：她的气泡、对话列表选中行、麦克风选择中的选中行。浅 L 0.955 / 深 L 0.30。上面的正文用墨水色（≥ 4.5）。
- **paperMuted**（`--her-paper-muted`）：paper 上的次要字（中文字幕、选中行描述），≥ 4.8，给细笔画留余量。
- **note / noteRule**（`--her-note`、`--her-note-rule`）：便利贴底色（浅 L 0.92 / 深 L 0.36）与其上的状态下划线（≥ 3）。
- **mark**（`--her-mark`）：头像的 2px 描边；官方色在纸面上达到 3:1 就用官方色，否则调到达标。
- **button.bg / button.fg**（`--her-button`、`--her-button-fg`）：她颜色的圆形电话键，图标 ≥ 4.5。浅色模式底色是原色；深色模式下底色取 `mark.dark`，保证按钮和页面对比度 ≥ 3（深色印象色不会消失在深色页面上）。
- **accent / onAccent**（覆盖 `--color-accent`、`--color-text-accent`、`--color-icon-accent`、`--color-on-accent`）：对话子树里 Astryx 组件的强调填色（例如发送键）及其上的字。
- **call.top / call.deep / call.glow / call.rule**（`--her-call-*`）：通话层渐变的上沿（74% 白字 ≥ 4.5）、底部（白字 ≥ 7）、头像背后的原色光晕（30% 混合，只作装饰）、状态线与头像描边（在上沿和底部都 ≥ 3）。

### Tertiary
- **Hang-up Red（挂断红）**（`hang-up-red`）：两种模式都用的 `--color-error`，只给挂断、「挂断并离开」这类危险操作。Astryx 默认的深色红配白字只有 3.8:1，所以在主题里覆盖。

### Neutral
- **Cool Copy Paper（冷白复印纸）**（`copy-paper`）/ **Night Paper**（`night-paper`）：`--color-background-body`，页面、页首、列表栏的实底。
- **Night Surface**（`night-surface`）：深色模式的 `--color-background-surface` / `--color-background-card`，弹层比纸面高一层。浅色模式下两者等于纸面。
- **Popover White**（`popover-white`）/ **Night Popover**（`night-popover`）：`--color-background-popover`，菜单与浮层。
- **Sky Rule（天蓝横线）**（`sky-rule` / `night-rule`）：`--color-border-blue`，消息区横线，也是列表栏与对话栏之间的分隔线。
- **Margin Line（装订边距线）**（`margin-line` / `night-margin-line`）：`--color-border-emphasized`，比横线深一档的竖线。
- **Pencil Grey（铅笔灰）**（`pencil-grey` / `night-pencil-grey`）：`--color-text-secondary`，时间戳、列表描述、免责声明。
- **Night Overlay Edge**（`night-overlay-edge`）：只在深色模式出现的弹层边线（对话框、底部面板、浮层），与 `night-surface`、`night-popover` 都 ≥ 3:1（`notebookTheme.test.ts` 校验）。

### Named Rules
**The Paired Colour Rule.** 任何她颜色的底色或前景都只能取自 `imageColorScale()` 的成对值（经 `herVars()` / `ld()`），绝不直接把官方原色写成字色或底色。新增一种用法，就在 `imageColor.ts` 加一对颜色，并在 `imageColor.test.ts` 的 `pairs()` 里加上它的对比度要求；契约覆盖 5 位官方色和 216 色网格。

**The One Ink Rule.** 全站只有一种墨水。正文、标题和制作人的气泡用同一个事务所深蓝；她的颜色只属于她的东西，不用来写制作人的字或系统界面。

**The Scoped Colour Rule.** 她的颜色只注入到这段对话的子树（`herVars(character.color)`），从不写进主题或 `:root`。需要在子树里仍用制作人墨水时，读 `--office-ink`（`PageShell` 在页面根上从 `--color-accent` 取下，对话子树覆盖 accent 之前）。

**The Theme Patches Defaults Rule.** Astryx 默认值在某一模式下不达标时，在主题里修：`tokens` 覆盖颜色，`components` 按稳定类名 `.astryx-<key>` 的键（`dialog`、`bottom-sheet`、`popover`）加样式。不在调用处逐个打补丁。

## Typography

**Body Font:** Noto Sans SC（`--font-zh`，回退 PingFang SC、Microsoft YaHei、system-ui）
**Japanese Font:** M PLUS 1p（`--font-ja`，回退到正文字体）

**Character:** 中文界面用端正、中性的黑体；她说的日语用笔画圆润一些的 M PLUS 1p，一眼能分出「她的原话」和「字幕」。

### Hierarchy
- **Title**（600，1.0625rem）：页首的「对话」、角色名（`Heading level={1}` 压到 `--text-large-size`）、通话层里的角色名。标题统一 semibold。
- **Japanese Line**（400，1.0625rem，M PLUS 1p）：她的日语原文，气泡里和通话层里都用 `Text type="large" weight="normal"`，外面包 `<Ja>`（`lang="ja"`，换字体）。通话层里居中、`text-wrap: balance`，最宽 34em。
- **Body**（400，0.875rem）：制作人的消息、列表名、通话层里的中文字幕。
- **Status**（500，0.875rem，等宽数字）：通话计时、「正在呼叫…」「通话已结束」、便利贴文字，配线形状态。
- **Label**（400，0.75rem）：气泡里的中文字幕（`Text type="supporting"`，paperMuted 色）、时间戳、圆形控制键下的标签、免责声明。
- **后台（/admin）**：数据密集，层级要比其余页面多一级。页标题 h1 用 Heading 默认的 heading-1（600，1.5rem）；组标题 h2 是 Title（`SettingsSection`）；组里的小节 h3 和正文同字号、靠 semibold 区分；表头 Label 字号、500、铅笔灰（主题 `table-header-cell` 覆盖）；数字卡的数字 600、1.25rem、等宽数字，不和页标题抢。说明文字最宽 42em（`PROSE_WIDTH`）。

### Named Rules
**The Original-Then-Subtitle Rule.** 她的一句话永远是两行：日语原文在上、大一号、M PLUS 1p、标 `lang="ja"`；中文字幕在下、小一号、次要色。字幕不能比原文大，也不能单独出现来代替原文。

## Layout

- **宽屏（≥ 768px）**：两栏。左侧对话列表默认 320px，与右栏之间一条 1px `sky-rule` 竖线；拖动这条竖线可以在 240–480px 之间调宽窄，悬停时出现 Astryx `ResizeHandle` 的握条，尺寸记在这台设备上。右侧对话栏填满。通话层绝对定位盖住对话栏，列表仍可见。没选角色时右栏居中一句次要色标题。
- **窄屏（< 768px）**：一次一栏，列表或对话；页首有返回键。通话层固定定位铺满整屏。
- **页首**：实底纸色，`12px 16px` 内边距，元素间距 12px；头像、名字（填满）、她颜色的电话键、更多菜单；下边一条 1px `--color-border` 分隔线（列表栏页首同样）。窄屏上返回键和电话键不小于 44px。
- **消息区**：唯一铺横线纸的区域。横线间距 32px（`--spacing-8`），1px `sky-rule`；边距线在距起始边 16px 处，1px `margin-line`。消息间距 16px，从顶部开始排。
- **输入栏**：Astryx 自带的 `ChatComposer`，放在 `ChatLayout` 的 composer 槽里，实底，不透出横线。宽屏上拖动它的上沿可以调输入框空着时的高度（一行到消息区的一半，记在这台设备上），字多了照旧往上长；窄屏不能调。
- **通话层**：内边距 20px / 16px；上排收起键、居中「语音通话」、「只看文字」开关；中部垂直居中头像、名字、状态、台词（间距 16–24px）；底部三枚圆形控制键，间距 32px，上下各 24px。有立绘时中部换成立绘版布局（见「Call layer」）。
- 间距全部取 Astryx 的 `--spacing-*` 令牌（2、4、6、8、12、16、20、24、32、40、44、48px；44px 即 `--spacing-11`，是手机上的触控下限）。更大的尺寸由令牌相乘得到，例如圆形控制键 `calc(var(--spacing-8) * 2)`。

- **后台（/admin）**：侧栏在 768px 以上常驻。每页一个 `AdminPage` 页框（页首加限宽内容列：看板、用户列表 1200px，配置、用户详情 960px），下面各组用 `SettingsSection`。内容区放不下表格时，表格换成 `List` 行（名字在左、要紧的数字在行尾、其余进副行），不横向滚动：三四列的小表在视口 1024px 以上用表格，七列的服务健康、按模型的花费和用户表要到 1280px（`useWide`）。

**The Paper-Only-Where-She-Writes Rule.** 横线纸只是消息区的地面。页首、输入栏、列表栏、弹层都是实底，不铺横线。

## Elevation & Depth

整体是平的纸面，靠色调分层；阴影只给两样「真的离开纸面」的东西。浅色模式下弹层靠 Astryx 默认阴影就够；深色模式下弹层和背后几乎同色，所以弹层改用更亮一层的底（`night-surface`、`night-popover`）并加 1px `night-overlay-edge` 边线。

### Shadow Vocabulary
- **Sticky note lift**（`box-shadow: 0 2px 8px var(--color-shadow)`）：只给页首的通话便利贴。
- **Call portrait**（`box-shadow: 0 0 0 4px var(--her-call-rule), 0 12px 40px var(--color-shadow)`）：通话层大头像的描边与柔和投影。
- **Avatar ring**（`box-shadow: 0 0 0 2px var(--her-mark)`）：页首和列表里她的头像描边；这是描边，不是投影。

### Named Rules
**The Flat Paper Rule.** 纸面上的东西不投影；只有贴上去的便利贴和展开的通话层头像有阴影，而且都是柔和阴影，不用硬偏移阴影。

**The Night Edge Rule.** 深色模式下每个弹层都要比纸面高一层色调并带 `night-overlay-edge` 边线；浅色模式下这条边线为透明。

## Shapes

形状全部是 Astryx 默认，主题只调了半径基数（`radius: { base: 4, multiplier: 1.5 }`），得到 inner 6px、element 12px、container 18px、page/chat 42px。气泡用 `ChatMessageBubble` 自带的形状，没有尾巴、没有索引签，只覆盖底色和字色。圆形只有三处：她颜色的电话键、通话层的三枚控制键（`--radius-full`）、头像。便利贴是唯一的直角、带 -1.2° 倾斜的纸片，顶上一条 48×16px、+2° 的半透明胶带。

## Components

### Buttons
- **Shape:** Astryx 默认（`--radius-element`，12px）；电话键和通话控制键为正圆。
- **Primary:** Astryx `Button variant="primary"`，在对话子树里填她的 accent，字用 onAccent。
- **Secondary / Ghost:** 返回、收起、更多菜单用 ghost；「回到对话」用 secondary。
- **在通话层上:** `MediaTheme mode="dark"` 把 accent 换成白色，所以结束页的主操作（「重拨」「去设置自带密钥」）是白底；secondary 的底（`--color-neutral`）换成和圆形键一样的 16% 白，否则系统是浅色时会取到浅色模式的值，几乎看不见。
- **Her call button（电话键）:** `IconButton` 正圆，底 `--her-button`，图标 `--her-button-fg`，无边框。通话中同一个键变成「回到通话」。
- **Destructive:** 挂断与「挂断并离开」用 `hang-up-red`，白字。

### Chat bubbles
- **Producer:** 右侧，底为制作人墨水（`--office-ink`），字为纸色。深色模式下是 `office-ink-night` 底、`night-paper` 字。
- **Hers:** 左侧，带她的头像；底 `--her-paper`，正文墨水色；内容是日语原文 + 中文字幕两行（见 Typography）。
- **Metadata:** 时间戳在气泡下方，Label 字号，铅笔灰。

### Conversation list
- Astryx `List` / `ListItem` 行，不用卡片包。每行：带她 mark 描边的头像、名字、最后一句（她的中文字幕，或「你：…」）、时间。
- **Selected:** 行底铺她的 `paper`，次要字换成 `paperMuted`（`listRow(color, selected)`，同时给每行注入她的 `mark`）。通话中该行描述换成「通话中 mm:ss」/「正在呼叫…」。
- 底部固定一行免责声明，Label 字号。

### Inputs / Fields
- **Composer:** Astryx `ChatComposer` 原样使用；发送键取对话子树的 accent。
- **Switch:** 「只看文字」用 Astryx `Switch size="sm"`；在通话层里把 `--color-background-surface` 换成白色，圆钮才和她的颜色拉得开。

### Overlays
- **AlertDialog**（离开对话前确认挂断）、**BottomSheet**（切换麦克风，高度随内容）、**MoreMenu / Popover**：Astryx 默认，遵守 The Night Edge Rule。麦克风选择的当前项同样铺她的 paper（`listRow()`），写「正在使用」。
- **换衣装**（对话页页首 `OutfitIcon`，她有立绘时才有）：宽屏 **Dialog**（左边全身大预览、右边卡片 `Grid`），窄屏 **BottomSheet**（高度 tall，大预览在上面、随列表一起滚动）。每张卡是一个 `Card`：缩略图、卡名（固定两行）、铺满卡宽的「私服 / 演出」`SegmentedControl`，只有一套的是灰掉的「只有一套」，所有卡一样高。正在预览的卡同样铺她的 paper（`listRow()`），不另加描边；大预览的底是她的 paper。卡片是缩略图画廊，不是数据行，所以不用 `List`。

### Call layer（通话层，signature）
- 强制深色（`color-scheme: dark` + `MediaTheme mode="dark"`）。次要字是 74% 白，与 `CALL_MUTED` 一致。
- **有背景图时**（`characters.toml` 的 `background`，经 `/api/characters/{id}/background`）：图片 `cover` 居中铺满，上面压一层纱 `linear-gradient(180deg, call.top 82% 0%, call.deep 94% 62%, call.deep 100%)`，没有光晕。对比度契约只覆盖纯色的 call.top / call.deep；纱留出的 6–18% 透出图片，所以换上新图后要在通话层上目测台词和计时是否仍清楚。
- **没有背景图时**：`linear-gradient(180deg, call.top 0%, call.deep 62%)`，叠一个中心在 50% 38% 的径向光晕（call.glow 30%）。
- **有立绘时**（`/api/characters` 的 `stand` 不为 null）：一打电话就用立绘版布局，立绘晚到或加载失败都不切回头像版，字幕位置在通话中途不跳。立绘是一块透明底的 WebGL 画布，叠在背景图和纱之上、文字和按钮之下，不接收点击；不再显示大头像。
  - **手机「大立绘」**（占满整屏时）：立绘占通话层下方 78% 的高度，贴着头顶、到膝；名字（Heading）、状态和计时、字幕都在上方居中。
  - **电脑「半身 ADV」**：立绘铺满整层，贴着头顶、到腰，取景宽度不窄于身体的约 70%；名字、状态和计时、字幕放进底部的**对话框**：`--radius-container` 圆角，底为 72% 的 call.deep，一圈 `--border-width` 的 call.rule 细线，内边距 `--spacing-4`，左上角是 call.rule 色、medium 字重的名字。结束页也在对话框里。
  - **底部渐变**：两种布局都在底部 45% 的高度上压一层 `linear-gradient(180deg, transparent 0%, call.deep 88% 55%, call.deep 100%)`，圆形键和对话框落在衣服上也看得清。
  - **出现**：加载中只露出背景图和纱，不放转圈，也不放占位剪影；到了用 0.3 秒（`--duration-medium-min`）淡入。手机上同时从下方 12% 处升起（`--duration-medium` + `--ease-standard`）；`prefers-reduced-motion` 时只原地淡入。
  - **对比度**：对话框和手机上方的字落在半透明的底和立绘上，`imageColor.test.ts` 的契约管不到；换角色、换默认衣装后要在两种宽度下目测名字、计时和字幕是否仍清楚。
  - **失败**：runtime 或素材加载不到、浏览器不支持 WebGL 时去掉画布，保持立绘版布局，只显示背景图和纱，不提示用户；下一通电话再试。
- **Motion:** 像折纸一样整张从页首拉下：`clip-path: inset(0 0 100% 0)` ↔ `inset(0)`，`--duration-medium`（410ms）+ `--ease-standard`（`cubic-bezier(0.24, 1, 0.4, 1)`）；收起是同一动作反过来，Esc 也能收起；`prefers-reduced-motion` 时无过渡。收起时 `visibility` 在动画结束后才切到 hidden，收起的通话层 `inert` 并 `aria-hidden`；展开时焦点移进通话层，底下的页首和对话 `inert`。结束页上 Esc 是回到对话。收起时焦点在通话层里的话，先送回页上再藏起通话层：通话还在进行（⌄ 或 Esc 收起）落在通话便利贴上，回车或空格就能再展开；通话结束了（挂断，或结束页上「回到对话」/Esc）落在页首的电话键上；焦点在便利贴上时通话结束、便利贴消失，也退回电话键。焦点已经在通话层外面时不动。
- **Round controls:** 拨打中只有挂断可用，麦克风静音和切换麦克风置灰。64px 正圆，底为 16% 白、无边框、白色图标，按下（麦克风静音）时变成实白底 + call.deep 图标；挂断在中间，用 destructive 红。每枚下方一行 Label。
- **Ended:** 删除线状态「通话已结束」、原因标题、说明、是否计入限额，以及「回到对话」+ 主操作两个按钮。

### Call note（通话便利贴，signature）
- 通话层收起时贴在页首和消息区之间的一条实底纸色窄带上、居中：底 `--her-note`，墨水色 Status 字，`8px 20px` 内边距，-1.2° 倾斜，一条半透明胶带（55% 纸色，外圈 60% 的 `--color-border-blue`，上移 8px），Sticky note lift 阴影。点击展开通话层。
- 文字带下划线状态：实线 = 通话中（「通话中 mm:ss · 点击返回」），虚线 = 正在呼叫。

### Icons
- 全部来自 `lucide-react`。界面图标经 `frontend/src/theme/icons.ts` 以语义别名导出（`PhoneIcon`、`HangUpIcon`、`MicIcon`、`MicOffIcon`、`MicSwitchIcon`、`CollapseIcon`、`BackIcon`、`TrashIcon`、`OutfitIcon`，后台导航的 `DashboardIcon`、`ConfigIcon`、`UsersIcon`）；Astryx 内部图标在主题 `icons`（`frontend/src/theme/astryxIcons.ts`）里换成对应的 Lucide 图标（arrowUp 和 stop 即输入栏的发送键和停止键，以及 check、chevron*、close、error、info、menu（AppShell 窄屏下的导航按钮）、microphone、moreHorizontal、success、warning）。Astryx 用到而没有注册的图标名会回退到它自带的图标，用上新的 Astryx 组件时要检查它调用了哪些图标名。

**The Line-State Rule.** 通话状态只用线形表达，线色是她的 rule 色（纸面上 `noteRule`，通话层上 `call.rule`），2px 粗、6px 偏移：实线下划线 = 通话中，虚线下划线 = 正在呼叫，删除线 = 已结束。

**The Library Icon Rule.** 图标只从 Lucide 取，并注册到 Astryx 的语义名；不手绘 SVG，不用字符或 emoji 当图标。

## Do's and Don'ts

### Do:
- **Do** 通过 `herVars(character.color)` 把她的颜色注入对话子树，并只使用 `--her-*` 与被覆盖的 `--color-accent*` 变量。
- **Do** 每新增一种她颜色的「底色 + 前景」组合，都在 `imageColor.ts` 里成对定义并加进 `imageColor.test.ts` 的对比度契约（正文 ≥ 4.5，小字 ≥ 4.8，图形 ≥ 3，通话层底部白字 ≥ 7）。
- **Do** 用 Astryx 组件的默认形状，只覆盖颜色；气泡用 `ChatMessageBubble`，输入栏用 `ChatComposer`，行用 `List` / `ListItem`。
- **Do** 在主题里修补某一模式下不达标的 Astryx 默认值：令牌覆盖，或按 `.astryx-<key>` 键写组件覆盖。
- **Do** 让横线纸（32px 横线 + 16px 处边距线）只铺在消息区，页首和输入栏用实底。
- **Do** 用实线 / 虚线 / 删除线表达通话中 / 正在呼叫 / 已结束。
- **Do** 把她的日语包在 `<Ja>` 里（`lang="ja"`，M PLUS 1p），大一号在上，中文字幕小一号在下。

### Don't:
- **Don't** 把官方印象色直接当字色或底色写进样式；也不要在 `:root` 或主题里写某位角色的颜色。
- **Don't** 手绘 SVG 图标或手做气泡尾巴；不要在她的消息旁放颜色索引签。
- **Don't** 用中性灰底 + 绿色通话条的聊天软件默认样式，也不要用奶油纸或重纹理做纸感。
- **Don't** 在横线纸以外的区域（页首、输入栏、弹层）铺横线。
- **Don't** 给纸面上的卡片、气泡、行加阴影；阴影只属于便利贴和通话层头像。
- **Don't** 在通话层有背景图时去掉那层纱，或把纱调得更透；白字的可读性全靠它。
