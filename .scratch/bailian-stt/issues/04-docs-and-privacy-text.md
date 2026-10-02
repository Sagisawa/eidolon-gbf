# 04: 隐私说明和文档写上阿里云百炼

**What to build:** 用户看到的隐私说明、部署者看到的文档都改为语音识别两家可选。背景见 `../spec.md` 和 ADR-0010。

**Blocked by:** 03。只改文档和 `frontend/src/i18n/zh.ts` 的文案。

**Status:** ready-for-agent

## 要做的

- **隐私说明**（`zh.ts` 里「这些数据会交给哪些第三方处理」的「语音服务」）：固定文案，两家都列。大意：通话时你的声音会发给部署者选择的语音识别服务（Soniox 或阿里云百炼）识别成文字，角色的回复会发给 Fish Audio 合成语音；阿里云百炼不会用它训练模型，但会保存一段时间，存放在中国内地或新加坡，取决于部署者的账号。自带密钥那条 note 不动。
- **`.env.example`**：语音通话那一节加 `STT_PROVIDER`、`DASHSCOPE_API_KEY`、`BAILIAN_STT_MODEL`，写明：两家二选一；百炼的 key 北京、新加坡都行，系统自动判断；要先在百炼控制台开通所选模型；key 不能用时后端拒绝启动；北京有免费额度。加密自带密钥那行的服务列表改掉 Soniox 的写死。
- **`docs/deploy.md`**：语音通话需要的 key 改为「Fish Audio，加 Soniox 或阿里云百炼之一」。
- **README（中、英、日）**：功能表的自带密钥一行、架构图的 Call 边、服务表、致谢里加上阿里云百炼。服务表里写明公开部署选百炼时数据可能存放在中国内地（指向 ADR-0010）。
- 文案里统一写「阿里云百炼」（英文 Alibaba Cloud Model Studio，日文 Alibaba Cloud Model Studio），不写「千问」，模型名除外。

## 验收

- [ ] 仓库里除了历史 `.scratch` 和 ADR 以外，不再有「只能用 Soniox」的说法（grep `Soniox` 逐条看过）。
- [ ] `frontend/` 下测试和类型检查通过（`callEnd.test.ts` 里的 Soniox 用例是后端给的文字，可以保留）。
- [ ] **人工验收（留给用户）**：落地页的隐私说明读起来清楚。

## Comments
