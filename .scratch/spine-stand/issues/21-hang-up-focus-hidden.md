# 21: 挂断时焦点被藏进 aria-hidden 的通话层

**What to build:** 挂断（以及收起通话层）时，焦点先移出通话层，再给通话层设 `aria-hidden`/`inert`，读屏用户不会停在一个被藏起来的按钮上。

**Status:** needs-triage

发现于 ticket 20 的验收（2026-10-01，Playwright 的 Chromium）：每次点「挂断」，控制台都有：

> Blocked aria-hidden on an element because its descendant retained focus. The focus must not be hidden from assistive technology users.

焦点在「挂断」按钮上，祖先是通话层的 `<section>`（`frontend/src/components/conversations/CallLayer.tsx` 里 `aria-hidden={isCollapsed}`、`inert={isCollapsed}`）。和立绘无关，挂断时一直都这样。

- [ ] 挂断、收起通话层时，焦点回到对话页上合适的位置（例如打电话键），控制台不再报这条警告。
