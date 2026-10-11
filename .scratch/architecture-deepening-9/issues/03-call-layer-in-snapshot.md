# 03: 快照交出通话层画哪一通、收没收起

**What to build:** 通话层照旧这样：
- 这一页还没打过电话时不出现；
- 拨号和因故结束时，收起的通话层重新展开；
- 挂断后、看完结束页点「回到对话」后，照常滑下收起，收起的过程中画的是最后一刻的样子，立绘不换也不重新载入；
- 焦点照旧归位。

新加一条：通话结束以后，通话层不能再被展开。

现在「画哪一通」靠页面的 hook 在渲染时 setState 留住最后一刻，「通话层收着」页面又自己算了一遍；LiveConversation 里也有一半同样的规则（什么时候重新展开）。改成快照交出 `layer`，规则只在 LiveConversation 里。

背景见 `../spec.md`（「通话状态与快照」里的 `layer`）。

**Blocked by:** 02（`layer.call` 要带 `dial`，立绘的 key 才不会在收起动画中途变掉）

**Status:** ready-for-agent

## 已定的设计（2026-10-11 grilling，详见 spec）

- 快照里的 `collapsed` 换成 `layer: { call: ShownCall; collapsed: boolean } | null`。`ShownCall`（拨号中、通话中或因故结束）的定义从通话层组件搬进 LiveConversation 的 module。
- 拨号前为 null。通话状态变成拨号、接通或因故结束时，`layer.call` 就是这个状态。回到 idle 时（用户挂断，或看完结束页），`layer.call` 留着最后一刻，`collapsed` 为 true。
- 原有的规则搬到 `layer.collapsed` 上照旧：拨号和因故结束时重新展开；`collapse()` 只在通话进行中有效。新加：`expand()` 也只在通话进行中有效。
- 开新对话时不清 `layer`。
- 删掉 `useShownCall` 和页面上自己算的「通话层收着」；焦点归位的输入（通话层开着没有、通话条显示没有）改从 `layer` 和通话状态算。

## 验收

- [ ] `liveConversation.test.ts`：
  - 拨号前 `layer` 为 null；
  - 拨号时出现并展开；
  - 用户挂断后留着最后一刻，并且收起；
  - 看完结束页后留着结束页，并且收起；
  - 收起后，拨号、因故结束都会让它重新展开；
  - 通话结束后 `expand()` 不起作用；
  - 开新对话时不清。
- [ ] 已有的用例里，凡是断言 `collapsed` 的，改成断言 `layer.collapsed`。
- [ ] `useShownCall` 删掉，页面不再自己算「通话层收着」。
- [ ] `vitest`、`tsc`、`sh scripts/check-discipline.sh` 通过。
- [ ] 人工验收清单写进 Comments：在构建版前端里，手机宽度和电脑宽度各看一遍：
  - 进页面时没有通话层；
  - 拨号时通话层滑上来；
  - 通话中收起再展开；
  - 挂断后通话层滑下，画面停在挂断那一刻，立绘不换；
  - 结束页点「回到对话」后滑下；
  - 收起后因故结束，通话层重新展开；
  - 用键盘收起时，焦点落在通话条上；结束后焦点落在电话键上。

## Comments
