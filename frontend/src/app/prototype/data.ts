// 原型用的假数据，全部是示意内容。

export type Character = {
  id: string;
  name: string;
  avatar: string;
  /** 印象色，来自 characters.toml。 */
  color: string;
};

export type Message =
  | { id: string; from: "producer"; text: string; time: string }
  | { id: string; from: "her"; ja: string; zh: string; time: string };

export const characters: Character[] = [
  { id: "mano", name: "櫻木真乃", avatar: "/prototype/mano.jpg", color: "#ffbad6" },
  { id: "kogane", name: "月岡恋鐘", avatar: "/prototype/kogane.jpg", color: "#f84cad" },
  // 配色压力测试：深色印象色，没有头像。不在 characters.toml 里。
  { id: "hiori", name: "風野灯織", avatar: "", color: "#144384" },
];

export const conversations: Record<string, Message[]> = {
  mano: [
    { id: "m1", from: "producer", text: "今天工作辛苦了，真乃在做什么？", time: "15:42" },
    {
      id: "m2",
      from: "her",
      ja: "プロデューサーさん、今日はピーちゃんと公園でひなたぼっこしてたんです…ほわっ",
      zh: "制作人，今天我和小哔在公园晒太阳呢……呼哇",
      time: "15:43",
    },
    { id: "m3", from: "producer", text: "好可爱啊！小哔也一起享受阳光了吗？", time: "15:44" },
    { id: "m4", from: "her", ja: "うんっ！ピーちゃんも、ぽかぽかで気持ちよさそうでした", zh: "嗯！小哔也暖洋洋的，看起来很舒服", time: "15:44" },
  ],
  hiori: [
    { id: "h1", from: "producer", text: "灯织，今天的练习辛苦了。", time: "周一" },
    { id: "h2", from: "her", ja: "はい。…まだ、足りないところばかりですけど", zh: "是的。……不过还有很多不足的地方", time: "周一" },
  ],
  kogane: [
    { id: "k1", from: "producer", text: "恋鐘，下周的舞台准备得怎么样？", time: "昨天" },
    {
      id: "k2",
      from: "her",
      ja: "ふっふ～ん、うちに任せとって！ばっちり仕上げとるけんね！",
      zh: "哼哼～交给我吧！已经准备得妥妥的了！",
      time: "昨天",
    },
  ],
};

/** 回复用的台词，按顺序循环。 */
export const cannedReplies: Record<string, { ja: string; zh: string }[]> = {
  mano: [
    { ja: "ほわっ…そうなんですね。プロデューサーさんのお話、もっと聞きたいです", zh: "呼哇……原来是这样。我还想多听听制作人说的话" },
    { ja: "えへへ…ありがとうございます。がんばりますっ", zh: "嘿嘿……谢谢您。我会加油的！" },
  ],
  hiori: [{ ja: "…ありがとうございます。次も、がんばります", zh: "……谢谢您。下次我也会努力的" }],
  kogane: [
    { ja: "んふふ～、プロデューサーもわかっとるね！", zh: "嗯哼哼～制作人也很懂嘛！" },
    { ja: "よかよか！うちがぜーんぶ任せとって！", zh: "好呀好呀！全都交给我吧！" },
  ],
};

export const microphones = [
  { id: "default", label: "默认 - 麦克风阵列（Realtek Audio）" },
  { id: "airpods", label: "AirPods Pro" },
  { id: "usb", label: "USB 电容麦克风" },
];

/** 通话中她正在说的这句。 */
export const liveLines: Record<string, { ja: string; zh: string }> = {
  mano: {
    ja: "プロデューサーさん、聞こえますか？…えへへ、声が聞けてうれしいです",
    zh: "制作人，听得见吗？……嘿嘿，能听到您的声音好开心",
  },
  hiori: { ja: "プロデューサー、聞こえていますか", zh: "制作人，听得到吗" },
  kogane: {
    ja: "もしもーし！プロデューサー、うちの声ちゃんと届いとる？",
    zh: "喂喂～！制作人，我的声音有好好传过去吗？",
  },
};

export const hearingSample = "嗯，听得很清楚，今天想跟你聊聊下周的";
