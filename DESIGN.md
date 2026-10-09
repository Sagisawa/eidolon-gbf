---
name: Eidolon-SC
description: 和 283 事务所的偶像说说话。制作人的手机：中性灰白的 LINE 式 IM，她的对话铺着她颜色的壁纸，制作人的话用事务所深蓝墨水。
colors:
  producer-ink: "#1c2a4a"
  producer-ink-night: "#a9c6f5"
  on-producer-ink: "#fbfcfe"
  on-producer-ink-night: "#14171d"
  background: "oklch(1 0 0)"
  background-night: "oklch(0.145 0 0)"
  foreground: "oklch(0.145 0 0)"
  foreground-night: "oklch(0.985 0 0)"
  muted: "oklch(0.97 0 0)"
  muted-night: "oklch(0.269 0 0)"
  her-bubble-night: "oklch(0.3 0.01 260)"
  hang-up-red: "#c8283c"
typography:
  list-title:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "1.25rem"
    fontWeight: 700
  header-name:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "17px"
    fontWeight: 600
  row-name:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 600
  body:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "15px"
    fontWeight: 400
  japanese-line:
    fontFamily: "LINE Seed JP, Noto Sans SC, system-ui, sans-serif"
    fontSize: "16px"
    fontWeight: 400
  subtitle:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "0.75rem"
    fontWeight: 400
  meta:
    fontFamily: "Noto Sans SC, PingFang SC, Microsoft YaHei, system-ui, sans-serif"
    fontSize: "11px"
    fontWeight: 400
rounded:
  control: "0.625rem"
  bubble: "22px"
  bubble-inner: "calc(0.625rem * 0.8)"
  full: "9999px"
components:
  conversation-list-column:
    backgroundColor: "{colors.background}"
    width: "340px"
  list-avatar:
    size: "56px"
  bubble-producer:
    backgroundColor: "{colors.producer-ink}"
    textColor: "{colors.on-producer-ink}"
    rounded: "{rounded.bubble}"
    typography: "{typography.body}"
  bubble-her:
    backgroundColor: "{colors.background}"
    textColor: "{colors.foreground}"
    rounded: "{rounded.bubble}"
    typography: "{typography.japanese-line}"
  bubble-avatar:
    size: "36px"
  composer-field:
    backgroundColor: "{colors.muted}"
    rounded: "{rounded.bubble}"
  call-dock-control:
    rounded: "{rounded.full}"
    size: "56px"
  call-hang-up:
    backgroundColor: "{colors.hang-up-red}"
    textColor: "#ffffff"
    rounded: "{rounded.full}"
    height: "56px"
---

# Design System: Eidolon-SC

## Overview

**Creative North Star: "The Producer's Phone"（制作人的手机）**

界面是制作人手机上的 IM。外框是中性的灰白，和一款克制的 LINE 一样：浅色底、扁平、细分隔线、对方头像在左、圆润的气泡、密而干净的对话列表。手机本身没有颜色；有颜色的只有她：进了她的对话，背景是她色相的一层极淡的壁纸；打起电话，整屏是她。制作人的话只用一种墨水，事务所深蓝。

隐喻只定基调，不落到装饰上：没有纸纹、横线、胶带、手绘图标，也不照搬 LINE 的功能（已读、贴图、LINE 绿都不做）。

系统建立在 shadcn/ui（底层 Base UI，样式 `base-nova`）和 Tailwind v4 之上（ADR-0015）。主题以 shadcn 的 neutral（纯灰、彩度 0）为底，只覆盖少数有理由的变量，覆盖值都有对比度测试。她的颜色不在主题里：由 `frontend/src/lib/imageColor.ts` 按明暗两种模式推导并校验对比度，再以 CSS 变量注入单个对话的子树。

**Key Characteristics:**
- 中性灰白外框，浅色、深色模式跟随系统。
- 她的颜色只在少数几处出现（见 The Her-Colour-Only-Here Rule），成对取用并有对比度契约测试。
- 制作人的墨水只写制作人的话（The Producer's Ink Rule）。
- 平面：平面上的东西不投影，只有浮层有阴影。
- 22px 圆角气泡，没有尾巴；同一个人连着发的几条成一组。
- 日语原文用 LINE Seed JP、在上；中文字幕小一号、在下。

## Colors

全部中性色来自 shadcn neutral；彩色只有两种：制作人的墨水，和当前这位偶像的印象色（按对话局部注入）。

### Primary: 制作人的墨水
- **Producer Ink（事务所深蓝墨水）**（`producer-ink` `#1c2a4a`，字用 `on-producer-ink` `#fbfcfe`）：浅色模式下制作人气泡的底。
- **Producer Ink Night**（`producer-ink-night` `#a9c6f5`，字用 `on-producer-ink-night` `#14171d`）：深色模式下制作人气泡的底。
- 只用在制作人气泡上，不是主题的 `--primary`，也不是正文色。

### Secondary: 她的印象色（per character, derived）
不是固定色值，而是 `imageColorScale(官方色)` 从 `characters.toml` 的印象色推出的一组 light/dark 成对颜色（保持色相，按 OKLCH 调明度与彩度，逐对校验 WCAG 对比度），以 `light-dark()` 注入对话子树（`--her-call-*` 除外：通话层永远是深色，只注入一份）：

- **wall**（`--her-wall`）：对话壁纸，她色相的极淡底（浅 L ≈ 0.955、C ≈ 0.018；深 L ≈ 0.2、C ≈ 0.016）。上面的 `--foreground` 和 `--muted-foreground`（时间戳、日期条）都 ≥ 4.5。
- **accent / onAccent**：对话子树里覆盖 shadcn 的 `--primary` / `--primary-foreground`，给子树里的 primary 按钮。注意浅色印象色（例如真乃 `#ffbad6`）的 accent 为了让白字达到 4.5 会压暗成灰紫，大面积填底前先看效果。
- **mark**（`--her-mark`）：子树里的 `--ring`、页首电话键的图标；官方色在底色上达到 3:1 就用官方色，否则调到达标。
- **button.bg / button.fg**（`--her-button`、`--her-button-fg`）：发送键和未读数的底与图标、数字，前景 ≥ 4.5，按钮和背景 ≥ 3。原型里未读数是 mark 底配白字，黄色、浅粉这类印象色上白字读不清，所以改用这一对。
- **call.top / call.deep / call.glow / call.rule**（`--her-call-*`）：通话层的渐变和线（见 Call layer）。
- `paper`、`paperMuted`、`note`、`noteRule` 这几对是上一版（选中行、便利贴）留下来的，新界面不再用 paper 铺选中状态；`note` 的去留等通话层收起状态定稿后再定，用不上就删。

### Tertiary
- **Hang-up Red（挂断红）**（`hang-up-red` `#c8283c`）：覆盖 shadcn 的 `--destructive`，两种模式都保证白字 ≥ 4.5。只给挂断、「挂断并离开」和确认框里真正执行删除、封禁的那一下。

### Neutral
- shadcn neutral 的 `--background`、`--foreground`、`--muted`、`--muted-foreground`、`--border`、`--card`、`--popover` 原样使用。系统文字（标题、列表名、说明）一律 `--foreground` / `--muted-foreground`，不是墨水色。
- 她的气泡在深色模式下用 `her-bubble-night`（`oklch(0.3 0.01 260)`），比壁纸高一层。
- 主题只覆盖有理由的变量（`--destructive`、深色浮层边线等），每个覆盖值都写进主题对比度测试（替代原来的 `notebookTheme.test.ts`）：`--muted-foreground` 在 `--background` 和 `--muted` 上 ≥ 4.5，`--destructive` 上的白字 ≥ 4.5，深色浮层边线和浮层底、页面底都 ≥ 3。

### Named Rules
**The Paired Colour Rule.** 任何她颜色的底色或前景都只能取自 `imageColorScale()` 的成对值，绝不直接把官方原色写成字色或底色，也不在调用处用相对颜色语法临时推色。新增一种用法，就在 `imageColor.ts` 加一对颜色，并在 `imageColor.test.ts` 的 `pairs()` 里加上它的对比度要求；契约覆盖 5 位官方色和 216 色网格。

**The Producer's Ink Rule.** 事务所深蓝只代表「制作人自己的话」：只用在制作人气泡上。系统界面的字用中性前景色；她的颜色不用来写制作人的字。

**The Her-Colour-Only-Here Rule.** 她的颜色只出现在：对话壁纸、电话键图标、发送键、未读数、通话层，以及对话子树里 primary 按钮和焦点环。选中状态（对话列表的选中行、麦克风选择的当前项、换衣装正在预览的卡）一律铺中性的 `bg-muted`。新增一处她的颜色，先改这条规则。

**The Scoped Colour Rule.** 她的颜色只注入到这段对话的子树，从不写进主题或 `:root`。子树里覆盖的是 `--primary`、`--primary-foreground`、`--ring` 和 `--her-*`。浮层（对话框、菜单、底部面板）通过 portal 渲染到子树外面，需要她的颜色时要在浮层内容上再注入一次。

**The Own-the-Source Rule.** shadcn 组件是仓库里自己的源码（`components/ui/`）。默认值在某一模式下不达标或不合适时，改那个组件文件或主题变量，不在调用处逐个打补丁。

## Typography

**Body Font:** Noto Sans SC（回退 PingFang SC、Microsoft YaHei、system-ui）
**Japanese Font:** LINE Seed JP（`next/font` 的 `LINE_Seed_JP`，400/700，回退到正文字体）

**Character:** 中文界面用端正、中性的黑体；她说的日语用 LINE Seed JP，笔画圆润，一眼能分出「她的原话」和「字幕」。

### Hierarchy
- **List title**（700，1.25rem）：对话列表顶部的「对话」大标题。
- **Header name**（600，17px）：对话页页首的角色名。
- **Row name**（600，15px）：列表行的角色名。
- **Japanese line**（400，16px，LINE Seed JP）：气泡里她的日语原文，外面包 `<Ja>`（`lang="ja"`，换字体）。通话层里 17px、居中、`text-wrap: balance`。
- **Body**（400，15px）：制作人的消息、输入框。
- **Preview**（400，13px，muted）：列表行的最后一句，单行截断。
- **Subtitle**（400，0.75rem，muted）：气泡里的中文字幕；通话层里 0.875rem、80% 白。
- **Meta**（400，10–11px，muted，等宽数字）：时间戳、列表时间、未读数、日期条。
- **后台（/admin）**：待「后台视觉原型」定稿后补。

### Named Rules
**The Original-Then-Subtitle Rule.** 她的一句话永远是两行：日语原文在上、大一号、LINE Seed JP、标 `lang="ja"`；中文字幕在下、小一号、muted 色。字幕不能比原文大，也不能单独出现来代替原文。

## Layout

- **宽屏（≥ 768px）**：两栏。左侧对话列表 340px、白底（深色模式 `--background`），右边一条 `border-r` 细线；右侧对话栏填满。通话层绝对定位盖住对话栏，列表仍可见。没选角色时右栏居中一句 muted 标题。列表能不能拖拽调宽、按像素还是按百分比，待「后台视觉原型」里的 Resizable 问题定。
- **窄屏（< 768px）**：一次一栏，列表或对话；对话页首有返回键。通话层固定定位铺满整屏。
- **对话列表**：顶部「对话」大标题和更多菜单，下面一个 `bg-muted` 的搜索框；行内边距 `px-4 py-2.5`，头像 56px，名字和时间一行、最后一句和未读数一行。
- **对话页首**：高 56px，和壁纸同色、不加分隔线；返回键（窄屏）、名字（填满）、搜索、电话键、更多菜单。触控目标不小于 44px。
- **消息区**：铺她的壁纸。气泡之间 4px，换人或换组时多 8px；日期条居中，`bg-foreground/10` 胶囊。消息从顶部开始排。
- **输入栏**：实底 `--background`，上沿一条 `border-t`；左边「+」，中间 22px 圆角的 `bg-muted` 输入框（一行起、最多长到 8rem），右边圆形发送键。

**The Wallpaper Rule.** 她的壁纸只铺在对话区（页首和消息区同一张壁纸）。列表栏、输入栏、浮层都是实底，不透出壁纸。

## Elevation & Depth

整体是平的，靠色调和细线分层。浮层（对话框、菜单、底部面板、Popover）保留 shadcn 默认阴影；深色模式下浮层比页面高一层色调并带一条细边线。

### Named Rules
**The Flat Rule.** 平面上的东西（气泡、列表行、卡片、页首、输入栏、头像）都不投影，也不加描边环；只有浮层有阴影。

**The Night Edge Rule.** 深色模式下每个浮层都要比页面高一层色调并带边线，边线和浮层底、页面底都 ≥ 3:1；浅色模式下靠阴影就够。

## Shapes

- **控件**：shadcn 默认的 `--radius`（0.625rem）及其派生档（`rounded-sm` 到 `rounded-4xl`）。
- **气泡和输入框**：22px。
- **正圆**：头像、发送键、通话层的圆形控制键、挂断胶囊、未读数。
- 没有气泡尾巴、没有颜色索引签、没有倾斜或贴纸式的元素。

## Components

### Buttons
- shadcn `Button`。对话子树里 `default`（primary）填她的 accent，字用 onAccent；返回、搜索、更多菜单用 `ghost` 的 `icon-lg`。
- **电话键**：对话页首的 ghost 图标键，图标用她的颜色。通话中同一个键变成「回到通话」。
- **发送键**：正圆，底 `--her-button`，图标 `--her-button-fg`。
- **Destructive**：挂断红，白字。
- **后台（/admin）**：待「后台视觉原型」定稿后补。

### Chat bubbles
- **成组**：同一个人连着发的几条算一组（The Bubble Group Rule）。
- **Producer**：右侧，底为制作人墨水，字为 on-producer-ink，最宽 72%。
- **Hers**：左侧；浅色模式白底（`--background`），深色模式 `her-bubble-night`；正文 `--foreground`。内容是日语原文 + 中文字幕两行。最宽 `min(30rem, 72vw)`。头像 36px、名字（12px muted）只在一组的第一条出现，其余条目留出同样的头像宽度对齐。
- **时间戳**：只在一组最后一条气泡的外侧底部，Meta 字号。

**The Bubble Group Rule.** 同一个人连着发的几条成一组：头像和名字只出现在第一条，时间戳只出现在最后一条；组内相邻气泡靠内侧的角收成 `rounded-md`（第一条收下角、最后一条收上角、中间的上下都收）。

### Conversation list
- 行就是行，不用卡片包。每行：头像（56px，无描边）、名字、时间、最后一句（她的日语，或「你：…」）、未读数（`--her-button` 底、`--her-button-fg` 字的胶囊）。
- **Selected**：`bg-muted`；悬停 `bg-muted/60`。通话中该行描述换成「通话中 mm:ss」/「正在呼叫…」。
- 底部固定一行免责声明，Meta 字号。

### Overlays
- shadcn 的 `AlertDialog`（离开对话前确认挂断）、`Drawer` 或 `Sheet`（切换麦克风）、`DropdownMenu` / `Popover`（更多菜单），遵守 The Night Edge Rule。麦克风选择的当前项铺 `bg-muted`，写「正在使用」。
- **换衣装**：宽屏对话框、窄屏底部面板，结构沿用（大预览 + 卡片网格，每张卡有缩略图、卡名、「私服 / 演出」切换）；正在预览的卡铺 `bg-muted`，大预览的底是她的壁纸。

### Call layer（通话层，signature）
- 强制深色（`color-scheme: dark`），文字白色，次要字 80% 白。
- **底**（没有背景图、没有立绘时）：她的头像放大、`blur-3xl`，上面压一层从 25% 黑到 `color-mix(call.deep 85%, black)` 的渐变。
- **头部**：左上收起键（ghost，白色图标），右上「只看文字」带字胶囊（15% 白底）。
- **中部**：头像 112px、无描边；名字 26px bold；计时 0.875rem、等宽数字。
- **台词卡**：在底部，毛玻璃 `bg-white/12 backdrop-blur-md rounded-3xl`，最宽 34em，日语原文在上、字幕在下。
- **底栏**：一条毛玻璃胶囊，静音、切换麦克风是 56px 圆形图标键（按下静音时变成白底黑图标），挂断是带「挂断」二字的挂断红胶囊。
- 待「通话层的其他状态与立绘衔接」定稿后补：有背景图时的底、立绘（手机大立绘 / 电脑半身 ADV）、正在呼叫与按钮置灰、结束页、「只看文字」开启后的样子、收起后页首的提示（原来的通话便利贴）、展开收起的动效、通话状态怎么表达（原来的 Line-State Rule）。
- 焦点与可访问性的行为沿用上一版：展开时焦点移进通话层、底下 `inert`；收起时通话层 `inert` 并 `aria-hidden`，焦点送回页上的对应位置；`prefers-reduced-motion` 时无过渡。

### Icons
- 全部来自 `lucide-react`，按语义别名从一个文件导出（沿用 `PhoneIcon`、`HangUpIcon`、`MicIcon` 这类名字），组件里不直接散用 Lucide 原名。

**The Library Icon Rule.** 图标只从 Lucide 取；不手绘 SVG，不用字符或 emoji 当图标。

## Do's and Don'ts

### Do:
- **Do** 把她的颜色注入对话子树，并只使用 `--her-*` 和子树里被覆盖的 `--primary`、`--primary-foreground`、`--ring`。
- **Do** 每新增一种她颜色的「底色 + 前景」组合，都在 `imageColor.ts` 里成对定义并加进 `imageColor.test.ts` 的对比度契约（正文 ≥ 4.5，小字 ≥ 4.8，图形 ≥ 3，通话层底部白字 ≥ 7）。
- **Do** 修默认值时改 `components/ui/` 里的源码或主题变量，并把主题覆盖值写进对比度测试。
- **Do** 让壁纸只铺在对话区，列表栏、输入栏、浮层用实底。
- **Do** 把她的日语包在 `<Ja>` 里（`lang="ja"`，LINE Seed JP），大一号在上，中文字幕小一号在下。
- **Do** 界面文案遵守 `GLOSSARY.md`：列表叫「对话」，不叫「聊天」。

### Don't:
- **Don't** 把官方印象色直接当字色或底色写进样式；也不要在 `:root` 或主题里写某位角色的颜色。
- **Don't** 用她的颜色铺选中状态，或在规则清单以外的地方用她的颜色。
- **Don't** 用深蓝墨水写系统文字，或把它设成 `--primary`。
- **Don't** 用 LINE 绿，也不要加已读、贴图这类 LINE 的功能性元素。
- **Don't** 给气泡、列表行、卡片、页首、头像加阴影或描边环；阴影只属于浮层。
- **Don't** 做气泡尾巴、纸纹、横线、胶带这类装饰。
- **Don't** 在通话层上去掉压在底图上的那层渐变，或把它调得更透；白字的可读性全靠它。
