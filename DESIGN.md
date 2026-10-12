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
  warning-amber: "oklch(0.666 0.179 58.318)"
  warning-amber-night: "oklch(0.769 0.188 70.08)"
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
  call-bar:
    height: "40px"
---

# Design System: Eidolon-SC

## Overview

**Creative North Star: "The Producer's Phone"（制作人的手机）**

界面是制作人手机上的 IM。外框是中性的灰白，和一款克制的 LINE 一样：浅色底、扁平、细分隔线、对方头像在左、圆润的气泡、密而干净的对话列表。手机本身没有颜色；有颜色的只有她：进了她的对话，背景是她色相的一层极淡的壁纸；打起电话，整屏是她。制作人的话只用一种墨水，事务所深蓝。

隐喻只定基调，不落到装饰上：没有纸纹、横线、胶带、手绘图标，也不照搬 LINE 的功能（已读、贴图、LINE 绿都不做）。

系统建立在 shadcn/ui（底层 Base UI，样式 `base-nova`）和 Tailwind v4 之上（ADR-0015）。主题以 shadcn 的 neutral（纯灰、彩度 0）为底，只覆盖少数有理由的变量，覆盖值都有对比度测试。她的颜色不在主题里：由 `frontend/src/lib/imageColor.ts` 按明暗两种模式推导并校验对比度，再以 CSS 变量注入单个对话的子树。

**适用范围**：这套规范管的是登录后的应用（对话列表、对话、通话层、设置、记忆、后台）。访客看到的落地页是另一个视觉世界（永远深色、棱镜分光、自己的字体和动效），不受这里的规则约束，只沿用印象色规则；落地页里的登录面板和行动按钮仍然按这里的规范来（ADR-0016）。

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
- **call.deep**（`--her-call-deep`）：通话层渐变和底部压暗的终点色、通话条的底；上面的白字 ≥ 7（见 Call layer）。
- 上一版留下的 `paper`、`paperMuted`、`note`、`noteRule` 和 `call.top`、`call.glow`、`call.rule` 新界面都用不上（选中状态铺中性底，便利贴换成了通话条，状态不再用线形表达），连同它们的对比度契约一起删掉。

### Tertiary
- **Hang-up Red（挂断红）**（`hang-up-red` `#c8283c`）：覆盖 shadcn 的 `--destructive`，两种模式都保证白字 ≥ 4.5。只给挂断、「挂断并离开」和确认框里真正执行删除、封禁的那一下。
- **Warning Amber（琥珀色）**（`warning-amber`，深色模式 `warning-amber-night`，主题变量 `--warning`）：只给后台服务健康里「出错偏多」的状态点。和挂断红一样，状态点在页面底和卡片底上 ≥ 3。

### Neutral
- shadcn neutral 的 `--background`、`--foreground`、`--muted`、`--border`、`--card`、`--popover` 原样使用。`--muted-foreground` 浅色模式从 0.556 压到 `oklch(0.52 0 0)`：原值在 `--muted` 上只有约 4.3:1，0.54 在她的壁纸上也只有约 4.4:1；深色模式原样。系统文字（标题、列表名、说明）一律 `--foreground` / `--muted-foreground`，不是墨水色。
- 她的气泡在深色模式下用 `her-bubble-night`（`oklch(0.3 0.01 260)`），比壁纸高一层。
- 主题只覆盖有理由的变量（`--destructive`、浅色的 `--muted-foreground`、深色浮层边线 `--overlay-edge`（深色 `oklch(0.556 0 0)`，浅色透明）），每个覆盖值都写进主题对比度测试（替代原来的 `notebookTheme.test.ts`）：`--muted-foreground` 在 `--background` 和 `--muted` 上 ≥ 4.5，`--destructive` 上的白字 ≥ 4.5，深色浮层边线和浮层底、页面底都 ≥ 3。

### Named Rules
**The Paired Colour Rule.** 任何她颜色的底色或前景都只能取自 `imageColorScale()` 的成对值，绝不直接把官方原色写成字色或底色，也不在调用处用相对颜色语法临时推色。新增一种用法，就在 `imageColor.ts` 加一对颜色，并在 `imageColor.test.ts` 的 `pairs()` 里加上它的对比度要求；契约覆盖 5 位官方色和 216 色网格。

**The Producer's Ink Rule.** 事务所深蓝只代表「制作人自己的话」：只用在制作人气泡上。系统界面的字用中性前景色；她的颜色不用来写制作人的字。

**The Her-Colour-Only-Here Rule.** 她的颜色只出现在：对话壁纸、电话键图标、发送键、未读数、通话层、通话条，以及对话子树里 primary 按钮和焦点环。选中状态（对话列表的选中行、麦克风选择的当前项、换衣装正在预览的卡）一律铺中性的 `bg-muted`。新增一处她的颜色，先改这条规则。

**The Scoped Colour Rule.** 她的颜色只注入到这段对话的子树，从不写进主题或 `:root`。子树里覆盖的是 `--primary`、`--primary-foreground`、`--ring` 和 `--her-*`。浮层（对话框、菜单、底部面板）通过 portal 渲染到子树外面，需要她的颜色时要在浮层内容上再注入一次。

**The Own-the-Source Rule.** shadcn 组件是仓库里自己的源码（`components/ui/`）。默认值在某一模式下不达标或不合适时，改那个组件文件或主题变量，不在调用处逐个打补丁。

## Typography

**Body Font:** Noto Sans SC（回退 PingFang SC、Microsoft YaHei、system-ui）
**Japanese Font:** LINE Seed JP（`next/font` 的 `LINE_Seed_JP`，只载 400，回退到正文字体）

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
- **后台（/admin）**：只用正文字体，字号比用户侧小一档，用 shadcn 组件自带的字号：
  - **Page title**（600，1.5rem，`text-2xl tracking-tight`）：每页的 h1。下面的说明 0.875rem、muted，最宽 42em。
  - **Card title**（500，1rem，`CardTitle`）：卡片标题；卡片说明 0.875rem、muted（`CardDescription`）。
  - **Stat**（600，1.5rem，等宽数字）：数字卡的数字；上面的标签用 `CardDescription`，下面的注释 0.75rem、muted。
  - **Body / table**（400，0.875rem）：表格、定义列表、表单。表头 500；行里的副行 0.75rem、muted。
  - **Caption**（400，0.75rem，muted）：数字卡分组的小标题（「此刻」「24 小时内」）、面包屑。
  - 数字一律 `tabular-nums`。

### Named Rules
**The Original-Then-Subtitle Rule.** 她的一句话永远是两行：日语原文在上、大一号、LINE Seed JP、标 `lang="ja"`；中文字幕在下、小一号、muted 色。字幕不能比原文大，也不能单独出现来代替原文。

## Layout

- **宽屏（≥ 768px）**：两栏。左侧对话列表 340px、白底（深色模式 `--background`），右边一条 `border-r` 细线；右侧对话栏填满。通话层绝对定位盖住对话栏，列表仍可见。没选角色时右栏居中一句 muted 标题。列表可以拖右边的线调宽：用 shadcn `Resizable`（react-resizable-panels v4），按像素约束（默认 320px，240–480px，`groupResizeBehavior="preserve-pixel-size"`，窗口变化时保持像素宽），`onResize` 的 `inPixels` 记进 localStorage，沿用现在 `useSavedSize` 的做法（挂载后在 layout effect 里恢复，避免水合不一致）。不自己写拖拽。
- **窄屏（< 768px）**：一次一栏，列表或对话；对话页首有返回键。通话层固定定位铺满整屏。
- **对话列表**：顶部「对话」大标题和更多菜单，下面一个 `bg-muted` 的搜索框；行内边距 `px-4 py-2.5`，头像 56px，名字和时间一行、最后一句和未读数一行。
- **对话页首**：高 56px，和壁纸同色、不加分隔线；返回键（窄屏）、名字（填满）、搜索、电话键、更多菜单。触控目标不小于 44px。
- **消息区**：铺她的壁纸。气泡之间 4px，换人或换组时多 8px；日期条居中，`bg-foreground/10` 胶囊。消息从顶部开始排。
- **输入栏**：实底 `--background`，上沿一条 `border-t`；左边「+」，中间 22px 圆角的 `bg-muted` 输入框（一行起、最多长到 8rem），右边圆形发送键。
- **设置页**：一栏，最宽 640px，手机和电脑同一个版式。
  - **四个标签**：档案、通话、自带密钥、登录与数据，一次只显示一组。当前标签记在地址参数 `tab` 里（`profile`、`call`、`own-keys`、`sign-in`），缺省或不认识的值打开档案；切换时替换当前历史记录、不滚动。切走的面板保持挂载。
  - **标签栏**：shadcn `Tabs` 的下划线样式（`variant="line"`），四个等宽、撑满一栏；选中态是中性的 `--foreground` 字和下划线，不用她的颜色。标签栏在内容的滚动区里吸在页首下面，铺实底 `--background`，下沿一条 `border-b`。
  - **节标题**：只有一节的标签页（通话、自带密钥）不写和标签同名的节标题，读屏靠标签面板读出它属于哪个标签；有几节的（档案、登录与数据）照旧每节一个标题。
  - **危险操作**：退出登录、退出所有设备、删除我的全部数据都放在「登录与数据」最底下，删除全部数据在最后；它的完整后果写在确认框里，节里只留一句。
  - **「关于 Eidolon-SC」**：不归哪一组，放在标签外面，作为内容的最后一块，跟着内容滚动。
  - **长说明**：外面只留最要紧的一两句，其余收进句末 ⓘ 弹出的 `Popover`（触发器 `openOnHover`：电脑上悬停打开，手机上点开），不用 `Tooltip`（不响应触摸，也不该装长段文字）。

- **后台（/admin）**：
  - **页框**：shadcn `Sidebar`（16rem），头部「后台」和「管理者：{name}」，菜单「看板 / 配置 / 用户」，底部「返回设置」；当前项用 `isActive`（中性底）。窄屏（< 768px）侧栏收进 Sheet。内容区顶上一条 48px 的页首：`SidebarTrigger` + 面包屑（Caption 字号），两者之间不加竖线。
  - **内容列限宽、靠中**：看板、用户列表最宽 1200px；配置、用户详情最宽 960px。内边距 `p-4 md:p-6`，块与块之间 `gap-6`。
  - **页首**：标题和说明在左，主要操作或范围切换（`Tabs`：24 小时 / 7 天 / 30 天 / 90 天）在右，可以折行。
  - **看板**：健康摘要和「数据截至」一行在页首下面；数字卡分两组（「此刻」1 张、「{范围}内」5 张），宽屏左右排（`1fr 5fr`），更窄时上下排，手机一行两张。服务健康、各张趋势图、结果表、通话时长、按角色、花费都各装一张 Card，宽屏两张一排。
  - **表格**：shadcn `Table`，默认密度，装在 Card 里。宽表（服务健康、用户、按模型）在 ≥ 1280px 显示，其他表在 ≥ 1024px 显示；更窄时换成 `divide-y` 的行：名字在左、状态或数字在行尾，其余放副行。排序沿用后端排序，点表头切换；不引入 TanStack Table（排序只有三档且都在后端，行展开只有单价表一处）。
  - **用户详情**：资料是一张 Card 里的两列定义列表（标签 Caption、值 Body），单独限额的按钮在 `CardFooter`；近期用量一张表；删除单独一张 Card，按钮在 `CardAction`。
  - **配置**：每一项一张 Card：标题旁边用 Badge 标状态（「已被后台覆盖」「覆盖没有生效」），右上角 `CardAction` 放「修改」。没有覆盖时内容是定义列表；有覆盖时是「项 / .env 的值 / 当前生效」的表，被盖掉的 .env 值划掉。点「修改」就在这张卡里展开表单（`FieldGroup`），全页同一时间只开一张；「恢复成 .env 的值」在 `CardFooter`。单价也是一张卡，「修改」在被修改的那一行下面展开。

**The Wallpaper Rule.** 她的壁纸只铺在对话区（页首和消息区同一张壁纸）。列表栏、输入栏、浮层都是实底，不透出壁纸。

## Elevation & Depth

整体是平的，靠色调和细线分层。浮层（对话框、菜单、底部面板、Popover）保留 shadcn 默认阴影；深色模式下浮层比页面高一层色调并带一条细边线。

### Named Rules
**The Flat Rule.** 平面上的东西（气泡、列表行、卡片、页首、输入栏、头像）都不投影；用户侧的这些东西也不加描边环。唯一的例外是后台的 shadcn `Card`：保留它默认的 `ring-1 ring-foreground/10` 细线来分块，这条线等同于分隔线，不是阴影。只有浮层有阴影。

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
- **后台（/admin）**：后台没有她的颜色，`default`（primary）就是 shadcn neutral 的黑底白字（深色模式反过来），只给表单的提交（「试调并保存」「保存」）。卡片上的「修改」、页首的「封禁」用 `outline`；行内操作（表格里的「封禁 / 解除封禁」「修改」）、「刷新」「取消」用 `ghost` 的 `sm`；「删除这位用户」这种打开确认框的入口也用 `outline`，只有确认框里真正执行的那一下用 `destructive`。

### Admin status & charts
- **状态**：服务健康只给出问题的项加点并加粗：出错偏多是琥珀色点，大量出错是 `--destructive` 点；正常、没有调用只写 muted 文字，不加点。用户和配置的状态用 Badge：「已封禁」`destructive`，「管理者」「已被后台覆盖」`secondary`，「单独限额：…」「覆盖没有生效」`outline`；「正常」只写 muted 文字。
- **图表**：手写 SVG 的 `TrendChart` 和比例条，柱子和条只用一种颜色 `--foreground`（浅色模式黑、深色模式白），网格线 `--border`，刻度和读数 muted；悬停的槽位铺 `bg-muted`，其余柱子降到 50% 不透明度。比例条的底是 `bg-muted`。不用墨水色，也不用 shadcn 的 `--chart-*`。
- 图表的尺寸按容器实际宽度画（`ResizeObserver`），不靠 `viewBox` 缩放，这样刻度字号不随栏宽变化。

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
- **页首**：左边「对话」大标题，右边两个 ghost `icon-lg` 图标键：GitHub 仓库链接（`GitHubIcon`，读屏名字「GitHub」，新标签页打开）和更多菜单。
- **顺序**：最近有过往来的在上面（开了新对话也算），从没聊过的在最后、按原作的偶像顺序；搜索结果同样排。一整列平铺，不按组合分段；一行换位置时直接跳过去，不做位移动画。
- **搜索框**：提示文字「搜索名字或组合」；日文原名、中文简体译名、假名、罗马字都能搜，输组合名列出整组。什么都没搜到时显示「没有找到这位偶像」。隐藏的人照样能搜到。
- **筛选按钮**：搜索框右边一个 ghost 图标键（`FilterIcon`，36px，和搜索框同高）。有人被隐藏时图标右上角一个 6px 小圆点，`bg-muted-foreground`，不用她的颜色也不用强调色；读屏名字带隐藏人数（「筛选列表，已隐藏 n 位」）。
- **筛选面板**：宽屏是挂在按钮下面、右对齐的 `Popover`，窄屏是从底部弹出的 `Drawer`（带拖动条）；判断宽窄用 `useWide`。头部左边标题「列表里显示谁」，右边 ghost 小按钮「全部显示」（没人隐藏时禁用，只清空隐藏、不动置顶）。下面按组合的官方顺序分组：组标题一行是三态勾选框（全勾、部分勾画横线、全不勾）加组合名（medium）；组内按官方顺序，每人一行缩进对齐到组名，勾选框、24px 头像、名字。没有组合的角色放在最后的「其他」组。清单可以滚动，勾选立即生效，没有确定键；不放搜索框和置顶开关。
- **行菜单**：右键、触屏长按、菜单键或 Shift+F10 打开 `ContextMenu`，两项：「置顶 / 取消置顶」「在列表中隐藏 / 在列表中显示」，按她当前的状态显示。中性色，遵守 The Night Edge Rule。长按打开菜单时不打开对话。
- **置顶**：置顶的排在所有人前面，她们之间也按最近往来排。时间右边一个 12px 图钉（`PinIcon`），`text-muted-foreground`；通话中不显示时间时图钉照样在。
- **隐藏**：没有搜索时隐藏的人不显示，但当前打开的和正在通话的那一行始终留着（离开她的对话后才消失）。有人被隐藏、搜索框为空时，列表最底下、免责声明上面一行「已隐藏 n 位」：Meta 字号、`text-muted-foreground`，整行可点（悬停 `bg-muted/60`），点了打开筛选面板。
- **全部隐藏**：所有人都被隐藏、又没有始终留下的人时，列表区是 `Empty`：标题「所有角色都隐藏了」，下面 outline 按钮「选择显示谁」打开筛选面板。

### Overlays
- shadcn 的 `AlertDialog`（离开对话前确认挂断）、`Drawer` 或 `Sheet`（切换麦克风）、`DropdownMenu` / `Popover`（更多菜单），遵守 The Night Edge Rule。麦克风选择的当前项铺 `bg-muted`，写「正在使用」。
- **换衣装**：宽屏对话框、窄屏底部面板，结构沿用（大预览 + 卡片网格，每张卡有缩略图、卡名、「私服 / 演出」切换）；正在预览的卡铺 `bg-muted`，大预览的底是她的壁纸。

### Call layer（通话层，signature）
- 强制深色（`color-scheme: dark`），文字白色，次要字 80% 白。
- **底**（没有背景图时，有没有立绘都一样）：她的头像放大、`blur-3xl`，上面压一层从 25% 黑到 `color-mix(call.deep 85%, black)` 的渐变。
- **头部**：左上收起键（ghost，白色图标），右上「只看文字」带字胶囊（15% 白底）。
- **中部**：头像 112px、无描边；名字 26px bold；计时 0.875rem、等宽数字。
- **台词卡**：在底部，毛玻璃 `bg-white/12 backdrop-blur-md rounded-3xl`，最宽 34em，日语原文在上、字幕在下。
  - **换段节奏**：一次只显示一段，只往前换、不退回，一段之内不做逐字高亮。有声音的回复跟着她的声音走：她开始念哪段（`segment-playing`）就换到哪段，开口前停在上一条回复最后显示的那段，没出声的段直接跳过；这段的文字还在到达的随到随补。回复已经记下、声音却停在半路一阵子没再响起（或者迟迟没有开始）时，剩下的段按估算的朗读时长放完，立绘的表情跟着台词卡换；被打断的回复停在打断时那段，等下一条回复开口再换。「只看文字」开始的回复没有声音，第一段一到就显示，之后每段停够估算的朗读时长、下一段也到了才换，中途关掉「只看文字」也照这个节奏放完；立绘的表情跟着台词卡换，不在文字到达时提前换；用户的话开启新回合后台词卡停在那段，新回复的第一段一到就直接换过去。估算节奏的常量在 `lib/linePacing.ts`。
- **底栏**：一条毛玻璃胶囊，静音、切换麦克风是 56px 圆形图标键（按下静音时变成白底黑图标），挂断是带「挂断」二字的挂断红胶囊。
- **有背景图时**（`characters.toml` 的 `background`；目前没有角色配）：背景图 `cover` 铺满、不模糊，压同一层渐变。对比度契约管不到图片，换上新图后要在通话层上目测台词和计时是否仍清楚。
- **状态行**（名字下面，0.875rem、80% 白、等宽数字）：呼叫中是「正在呼叫」加三个依次闪的小点；通话中是 `mm:ss`；结束后是挂断图标 +「通话已结束 · mm:ss」。只用文字和图标，不再用线形（取代上一版的 Line-State Rule）。
- **立绘**（`/api/characters` 的 `stand` 不为 null）：一打电话就用立绘版布局，立绘晚到或加载失败都不切回头像版，字幕位置在通话中途不跳。立绘是透明底的 WebGL 画布，叠在底图和渐变之上、文字和按钮之下，不接收点击。
  - 不显示 112px 大头像；名字（17px bold）和状态行缩进头部中间，夹在收起键和「只看文字」之间。台词卡和底栏的位置、样子与没有立绘时完全一样，压在她的衣服上。
  - **手机**：立绘占通话层下方 80% 的高度，取景贴着头顶、到膝（`knees`），到了从下方 12% 处升起并淡入。
  - **电脑**：立绘铺满头部以下的整层，取景贴着头顶、到腰（`waist`），原地淡入。
  - **底部压暗**：底部 50% 的高度上压一层 `linear-gradient(transparent, color-mix(call.deep 88%, transparent) 55%, call.deep)`，台词卡和底栏落在衣服上也看得清。
  - 加载中只露出底图和渐变，不放转圈或剪影；runtime、素材或 WebGL 不可用时去掉画布、保持立绘版布局，不提示用户，下一通电话再试（沿用上一版）。
- **正在呼叫**：静音和切换麦克风置灰（35% 不透明、不可点），只有挂断可用；「只看文字」照常可切换。没有立绘时头像外有两圈 20% 白的波纹向外扩散（2 秒一圈，`prefers-reduced-motion` 时不放）。台词卡在接通前不出现。
- **「只看文字」开启**：胶囊变成实白底、黑字（`aria-pressed`）；台词卡里上一句以 45% 不透明度留在当前这句上面，方便跟上。立绘不动嘴。
- **结束页**：收起键、「只看文字」和底栏都消失，立绘降到 40% 不透明度；台词卡的位置换成同样毛玻璃的结束卡，在剩余空间里垂直居中：原因标题（18px semibold）、说明（80% 白）、是否计入限额（Meta，60% 白），下面两个胶囊按钮「回到对话」（15% 白底）和主操作（白底黑字：重拨，或者超限额、自带密钥出错时「去设置自带密钥」）。
- **收起后：通话条**（取代上一版的通话便利贴）：对话页首下面一条 40px 高、铺满对话栏宽的条，底 `--her-call-deep`、白字；左边一个白色小圆点（呼叫中闪烁），接着「通话中 mm:ss」/「正在呼叫…」，右端「回到通话 ›」（80% 白）。整条是一个按钮，点了展开通话层。通话中页首的电话键改成实心图标、标签「回到通话」。
- **动效**：通话层从对话栏底部整张滑上来（`translateY(100%)` ↔ `0`），410ms + `cubic-bezier(0.24, 1, 0.4, 1)`；收起是同一动作反过来，Esc 也能收起；`visibility` 在收起动画结束后才切到 hidden。`prefers-reduced-motion` 时无过渡。
- 焦点与可访问性的行为沿用上一版：展开时焦点移进通话层、底下 `inert`；收起时通话层 `inert` 并 `aria-hidden`，焦点送回页上的对应位置：通话还在进行就落在通话条上（回车或空格再展开），通话结束了落在页首的电话键上。

### Icons
- 全部来自 `lucide-react`，按语义别名从一个文件导出（沿用 `PhoneIcon`、`HangUpIcon`、`MicIcon` 这类名字），组件里不直接散用 Lucide 原名。
- 品牌标志例外：Lucide 不收品牌标志，需要时照抄 simple-icons 的官方路径，不改形状，同样从那个文件导出。目前只有 `GitHubIcon`。

**The Library Icon Rule.** 图标只从 Lucide 取；不手绘 SVG，不用字符或 emoji 当图标。品牌标志是唯一的例外，只能用 simple-icons 的官方路径。

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
- **Don't** 给气泡、列表行、卡片、页首、头像加阴影；用户侧也不加描边环（后台 Card 的默认细线除外）。阴影只属于浮层。
- **Don't** 做气泡尾巴、纸纹、横线、胶带这类装饰。
- **Don't** 在通话层上去掉压在底图上的那层渐变，或把它调得更透；白字的可读性全靠它。
