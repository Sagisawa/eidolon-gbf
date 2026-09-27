// 简体中文界面文案。新界面上的每一句话都从这里取（经 `@/i18n` 的 copy），不在组件里写死。
// 按界面分组；带参数的句子写成函数，参数的位置由各语言自己决定。
// 术语以 CONTEXT.md 为准（对话、通话、通话层、麦克风静音、只看文字、印象色……）。

export const zh = {
  app: {
    name: "Eidolon-SC",
    description: "和 283 事务所的偶像说说话",
  },
  common: {
    back: "返回",
    close: "关闭",
    more: "更多",
    cancel: "取消",
  },
  conversationList: {
    title: "对话",
    noneSelected: "选一位偶像开始对话",
  },
  call: {
    leaveTitle: (name: string) => `会挂断和${name}的通话`,
  },
};
