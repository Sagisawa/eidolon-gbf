# 11: 写 spec.md 并切出实现 ticket

Type: task
Blocked by: 09, 10
Status: open

## Question

把地图「Decisions so far」里的全部决定汇总写成 `.scratch/shadcn-redesign/spec.md`，内容包括：视觉规范以 `DESIGN.md` 为准，只引用、不重复；人工验收清单（「页面 × 浅色/深色 × 关键状态」），每行标明所属的波；组件纪律；各波的范围和完成条件。然后按「实现波次的切分」（`09-wave-slicing.md`）的五波，切成可以直接交给 agent 的实现 ticket，写清每张的文件范围、依赖关系和分到的验收清单行。

这张 ticket 完成后，地图就到达终点。

补充（来自「新的组件纪律」，`10-component-discipline.md`）：底座波要多加两项，一是在 `frontend/AGENTS.md` 写纪律一节，二是在 CI 加 grep 脚本。清理波改 AGENTS.md 时只删 Astryx 部分，`grep @astryxdesign` 并进同一个脚本。
