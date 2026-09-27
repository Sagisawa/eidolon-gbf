# 05: 通话中切换麦克风

**What to build:** 通话层的「切换麦克风」打开一个设备列表，选中后当场换成那个麦克风，通话不断；这个设备同时成为以后通话的默认麦克风。设置页里的麦克风选择改名为「默认麦克风」。不做输出设备切换。规则见 `../spec.md`「通话层」。

**Blocked by:** 04

**Status:** ready-for-agent

- [ ] 实现 `frontend/src/lib/microphone.ts` 里的 `updateMic()`（现在是空实现）：换掉 WebRTC 发送的音轨，不重新协商，不断开通话；静音状态保持
- [ ] 设备列表用 Astryx `BottomSheet`，当前设备标明「正在使用」，选中行用她的 `paper` 色和 `paperMuted` 次要字
- [ ] 选中的设备写进通话偏好（`callPreferences.ts`），下次通话默认用它；设备被拔掉时退回系统默认，并提示
- [ ] 设置页文案改为「默认麦克风」
- [ ] 测试：偏好的读写与回退；真实通话中切换一次，确认对方能继续听到

## Comments
