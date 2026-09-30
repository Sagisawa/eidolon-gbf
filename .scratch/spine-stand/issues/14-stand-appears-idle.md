# 14: 她出现在通话层上（待机）

**What to build:** 部署者给角色配好偶像编号、默认衣装和素材地址后，用户打电话时，通话层的背景图上就叠了一层穿默认衣装的立绘，只做待机的呼吸和眨眼。手机上是「大立绘」，电脑上是「半身 ADV」。素材加载不到、浏览器不支持 WebGL 时，退回现在的背景图，通话不受影响。规则和定义见 `../spec.md`（「渲染」「通话层」「配置与 API」「许可证与文档」几节）。

参考：原型在分支 `prototype/spine-stand`（立绘引擎、`CallLayer` 的 `stand` 插槽、`/prototype/stand` 页面），真机测量版在 `prototype/spine-stand-perf`。原型是一次性代码，要按 spec 重写，不要直接合并。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] **配置**：`characters.toml` 每位角色新增两个可选字段，偶像编号（`spine_manifest.json` 的 `idolId`）和默认衣装（能定位到一套衣装的写法，例如 `stand/<enzaId>`，由你定，写进部署文档）。格式不对时启动报错，照现有字段的校验方式做。
- [ ] **素材地址**：新增一个后端环境变量，填立绘素材的公开访问地址。`/api/characters` 每位角色多一个 `stand` 字段：偶像编号、默认衣装、素材地址三项都配好时，给出默认衣装的素材 URL（后续 18 会加衣装清单的 URL），否则为 `null`。前端 `Character` 类型同步修改。
- [ ] **runtime**：官方 spine-ts 3.6 的 `spine-webgl.js` 原样放进单独的 vendor 目录，附上它自己的 LICENSE，和一份记录来源、版本、校验和的 README。在 `.gitattributes` 里把这个目录标成 `-text`。在客户端用 `<script>` 加载，通过 `window.spine` 调用（ADR-0009）。
- [ ] **许可证**：项目许可证加一条 AGPL 第 7 节的附加许可，允许本项目和 Esoteric Software 的 Spine Runtimes 组合在一起、一起分发；README 声明 vendor 目录不受 AGPL 约束。
- [ ] **立绘引擎**（一个不依赖 React 的类）：载入一套衣装，每帧推进并绘制。这一张只播待机，身体 `wait`、表情 `face_wait`。必须做到：
  - 绕开剪裁 bug：每帧把剪裁的结束插槽改成范围内最后一个真的会画出来的插槽；范围内什么都不画时，这一帧摘掉剪裁附件。
  - 预乘 alpha：上传贴图前开启 `UNPACK_PREMULTIPLY_ALPHA_WEBGL`，绘制时 `premultipliedAlpha = true`。
  - 上下文恢复：重设预乘 alpha 的监听要在创建 `ManagedWebGLRenderingContext` 之前注册。恢复不了的，退回背景图。
  - 销毁时不调用 `loseContext()`，因为 React 开发模式下 effect 会执行两次。
  - 像素比取 `min(devicePixelRatio, 2)`；最多 60 帧，刷新率更高的屏幕上跳过多余的帧。
  - 收起通话层时暂停渲染，展开时接着画。
- [ ] **通话层**：角色有 `stand` 时，一打电话就用立绘版布局，中途不切换，加载失败时也保持：
  - **手机「大立绘」**：立绘从底部升起，贴着头顶、到膝；名字、计时和字幕在上方；底部压一层她颜色的深色渐变，保证按钮看得清。
  - **电脑「半身 ADV」**：立绘铺满通话层，贴着头顶、到腰，宽度不窄于身体的约 70%；名字、计时和字幕放在底部一个半透明的对话框里，底部同样压一层深色渐变。
  - 立绘叠在背景图和纱上面。加载中只显示背景图和纱，不放转圈，也不放占位剪影；到了用 0.3 秒淡入。
  - 减少动态效果时，手机上的升起入场改成原地淡入。
  - runtime 或素材加载不到、浏览器不支持 WebGL 时，保持立绘版布局，只显示背景图，不提示用户。
  - 角色没有 `stand` 时，和现在完全一样。
- [ ] 遵守 AGENTS.md 的 Astryx 规则：用组件布局，数值都用 token。
- [ ] **DESIGN.md**：改写「Call layer」一节，写入立绘版的两种布局、渐变和对话框。
- [ ] **开发时怎么看效果**：在开发文档或 `.env.example` 里写明，用一个开了 CORS 的本地静态服务器直接提供镜像的 `assets` 目录，把素材地址指过去。
- [ ] **测试**：配置解析测试（新字段可选、格式错误时报错）；API 测试（三项齐全时 `stand` 才有值）。
- [ ] **人工验证**：真乃和恋钟各打一次电话，手机和电脑两种宽度下构图都正确；在 Comments 里附截图说明。「花風Smiley」这套衣装的眼睛、睫毛、眉毛完整（剪裁 bug 已绕开）。把素材地址改成错的，退回背景图，通话照常。
- [ ] `uv run pytest`、`uv run pyright`、`npm test`、`npm run typecheck` 全部通过。
