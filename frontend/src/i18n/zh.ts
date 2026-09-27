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
    menu: "更多操作",
    memories: "记忆",
    settings: "设置",
    /** 最后一句是制作人自己说的。 */
    you: (text: string) => `你：${text}`,
    neverTalked: "还没有对话",
    nothingSaidYet: "新的对话，还没有说话",
    yesterday: "昨天",
    monthDay: (month: string, day: string) => `${month}月${day}日`,
    fullDate: (year: string, month: string, day: string) => `${year}/${month}/${day}`,
    loading: "正在载入对话列表",
    loadFailed: "对话列表没能载入",
    retry: "重试",
    disclaimer: "非官方粉丝作品，与版权方无关；角色由 AI 扮演。",
  },
  conversation: {
    back: "返回对话列表",
    menu: "更多操作",
    newConversation: "新对话",
    textOnly: "只看文字",
    call: (name: string) => `和${name}通话`,
    callTooltip: "语音通话",
    hangUp: "挂断",
    calling: "正在呼叫…",
    inCall: "通话中 · 直接说话即可",
    placeholder: "用中文或日语说点什么",
    emptyTitle: (name: string) => `和${name}打个招呼吧`,
    emptyDescription: "打字，或者点右上角的电话和她通话。",
    replying: (name: string) => `${name}正在回复`,
    hearing: "正在听你说",
    loading: "正在打开对话",
    loadFailed: "对话没能打开",
    notFound: "没有这位角色",
    backToList: "回到对话列表",
    signIn: "去登录",
    /** 失败时说明这次算不算进限额（CONTEXT.md「限额」「回合」）。 */
    notCounted: "这次没有计入限额。",
  },
  call: {
    leaveTitle: (name: string) => `会挂断和${name}的通话`,
  },
};
