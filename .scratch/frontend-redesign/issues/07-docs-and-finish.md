# 07: 文档和收尾验收

**What to build:** 把重做后的界面写进文档，并对正式界面做一次完整的设计验收。

**Blocked by:** 03, 04, 05, 06

**Status:** ready-for-agent

- [ ] README（中、英、日三语）里关于界面和通话的描述更新：通话层、收起、麦克风静音、只看文字、切换麦克风；旧的「静音」说法全部替换
- [ ] `PRODUCT.md` 的 Capabilities：前端改为 Next.js + Astryx，不再是「没有 UI 组件库」；页面列表按新的路由更新
- [ ] `DESIGN.md` 与实现核对一遍，有出入以实现为准更新
- [ ] 用 impeccable 对正式界面做收尾审查（浅色、深色，手机、电脑），处理审查结论
- [ ] 如果维护者已经提供了背景图，放进 `characters/backgrounds/` 并在 `characters.toml` 填上，确认通话层显示正常

## Comments
