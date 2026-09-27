# 02: 印象色和通话层背景图：后端配置和接口

**What to build:** `characters/characters.toml` 里的 `color`（必填）和 `background`（可选）真正生效：后端加载时校验，角色接口把它们交给前端，背景图像头像一样可以获取。规则见 `../spec.md`「角色视觉」。

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [ ] `backend/src/eidolon/characters.py`：`color` 加进必填字段，格式必须是 `#rrggbb`，否则报 `CharacterConfigError` 并说明是哪位角色；`background` 可选，路径相对于配置文件，文件不存在时记一条警告并当作没有，和 `avatar` 的处理一致
- [ ] `/api/characters` 多返回 `color` 和 `background_url`（没有时为 null）；新增 `GET /api/characters/{id}/background`，行为和头像接口一致
- [ ] `characters/backgrounds/` 目录建好（可以只放 `.gitkeep`），与头像一样提交进私有仓库（ADR-0003 修订）
- [ ] 补测试：缺少 `color`、格式错误、背景图不存在、接口返回新字段
- [ ] `characters.toml` 顶部说明已写好（2026-09-27），核对与实现一致

## Comments
