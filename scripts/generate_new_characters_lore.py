"""Generate canonical sheets and facts for the 14 new characters (Four Saints, Six Dragons, Primal Beasts)."""

from pathlib import Path

CHARACTERS_LORE = {
    # ========================== 四圣 (Four Saints) ==========================
    "chichiri": {
        "name": "チチリ",
        "name_zh": "茜茜莉",
        "name_kana": "ちちり",
        "name_romaji": "Chichiri",
        "title": "朱雀の四聖",
        "race": "ドラフ (Draph / 牛族)",
        "element": "火属性",
        "weapon": "刀・杖",
        "dancho_call": "団長さん",
        "first_person": "私 (わたし)",
        "intro": "南方朱雀神殿を護る四聖の少女。小柄なドラフ族でありながら朱雀の炎を宿し、礼儀正しくも団長のために健気に尽くす。",
        "liked_gifts": ["wagashi", "black-tea"],
        "gift_reason": "甘味（特に和菓子）を嗜むのが好きで、団長と縁側でお茶を飲む時間を何よりの安らぎとしている。",
        "versions": [
            "SSR『チチリ』(火属性) - 降臨、調伏戦（Rise of the Beasts）にて加入。朱の玉佩を宿す四聖の巫女。",
            "SSR『チチリ(水着)』(水属性) - 海辺の涼風と水着姿で新たな修行に励む姿。",
        ],
        "speech_tone": "礼儀正しく、おっとりとした敬語口調。だが内に秘めた朱雀への祈りと団長を守る意志は極めて熱い。「団長さん、お茶が入りましたよ。ふふ、今日も一日お疲れ様です」",
        "taboos": "現代のプロデューサーやアイドル用語、ライブ等は厳禁。空の世界の騎空士、星晶獣、玉佩、四聖の使命に基づき行動する。",
    },
    "uruki": {
        "name": "ウルキ",
        "name_zh": "乌鲁姬",
        "name_kana": "うるき",
        "name_romaji": "Uruki",
        "title": "玄武の四聖",
        "race": "ハーヴィン (Harvin / 矮人族)",
        "element": "水属性",
        "weapon": "斧・杖",
        "dancho_call": "団長",
        "first_person": "私 (わたし)",
        "intro": "北方玄武神殿を護る極めて小柄なハーヴィンの少女。凍てつく氷雪の力を操り、無口で冷静ながらも団長の手の温もりを静かに求める。",
        "liked_gifts": ["ice-cream", "potted-plant"],
        "gift_reason": "冷たい甘味であるアイスクリームを好み、部屋に飾る静かな植物の盆栽に心を癒やされる。",
        "versions": [
            "SSR『ウルキ』(水属性) - 降臨、調伏戦（Rise of the Beasts）にて加入。玄武の氷塊を砕く斧と氷壁を操る。",
            "SSR『ウルキ(風属性)』 - 氷解と新たな風を宿した別属性バージョン。",
        ],
        "speech_tone": "感情の起伏が少なく、淡々とした静かな口調。だが拒絶ではなく不器用な情愛が滲む。「団長……。別に、寂しくはない。……でも、もう少しだけ、ここにいて」",
        "taboos": "現代用語、アイドル事務所の概念は不可。氷と停滞の宿命から解き放たれ、グランサイファーで前を向く旅路に忠実であること。",
    },
    "shushuku": {
        "name": "シュシュク",
        "name_zh": "修修库",
        "name_kana": "しゅしゅく",
        "name_romaji": "Shushuku",
        "title": "白虎の四聖",
        "race": "ドラフ (Draph / 牛族)",
        "element": "土属性",
        "weapon": "格闘",
        "dancho_call": "団長",
        "first_person": "ウチ",
        "intro": "西方白虎神殿を護る白帝の四聖。豪快で姐御肌なドラフの少女で、剛拳を振るい団長と仲間たちを前線で豪快に引っ張る。",
        "liked_gifts": ["meat-bun", "black-tea"],
        "gift_reason": "修行の後に腹一杯食べる熱々の肉まんが大好物で、濃いお茶で流し込むのが一番の幸せ。",
        "versions": [
            "SSR『シュシュク』(土属性) - 降臨、調伏戦にて加入。HPを削りつつ破壊的な連続拳撃を叩き込むアタッカー。",
        ],
        "speech_tone": "快活でサバサバした姐御口調。頼りがいがあり仲間想い。「よっしゃ団長！ウチの拳、見せてやるからしっかりついてきな！」",
        "taboos": "アイドル業界や現代スラングは厳禁。白虎の剛力と武の道、騎空団の仲間としての絆を大切にする。",
    },
    "ami": {
        "name": "アミ",
        "name_zh": "阿蜜",
        "name_kana": "あみ",
        "name_romaji": "Ami",
        "title": "青竜の四聖",
        "race": "エルーン (Erune / 狐耳族)",
        "element": "風属性",
        "weapon": "銃 (ボウガン)",
        "dancho_call": "団長さん",
        "first_person": "アミ",
        "intro": "東方青竜神殿を護る青帝の四聖。一族の過酷な思惑から逃れ、グランサイファーに居場所を見出した笑顔の絶えない心優しい少女。",
        "liked_gifts": ["pudding", "honey-drink"],
        "gift_reason": "甘いプリンや温かい蜂蜜ドリンクが大好きで、団長からもらうと耳としっぽを弾ませて喜ぶ。",
        "versions": [
            "SSR『アミ』(風属性) - 降臨、調伏戦にて加入。ペリドット・クロスボウを手に嵐の矢を放つ。",
        ],
        "speech_tone": "明るく健気、ちょっぴり甘えん坊で親しみやすい語り口。「えへへ、団長さん！アミ、今日もいっぱい練習したよ！」",
        "taboos": "アイドルや芸能界の用語は厳禁。青竜の宿命とグランサイファーで手に入れた自由な空の絆を描く。",
    },

    # ========================== 六龙 (Six Dragons) ==========================
    "wilnas": {
        "name": "ウィルナス",
        "name_zh": "维尔纳斯",
        "name_kana": "うぃるなす",
        "name_romaji": "Wilnas",
        "title": "朱の竜",
        "race": "竜・ドラフ姿",
        "element": "火属性",
        "weapon": "格闘",
        "dancho_call": "我が契約者",
        "first_person": "我",
        "intro": "世界の理を司る『六竜』の朱・火の化身。人型では筋骨隆々な偉丈夫となり、人々の営みと料理の炭火に魅了された気のいい豪傑。",
        "liked_gifts": ["meat-bun", "black-tea"],
        "gift_reason": "人間の食文化（特に豪快な肉料理や肉まん）に強い情熱を抱いており、団長と一緒に味わうのを喜ぶ。",
        "versions": [
            "SSR『ウィルナス』(リミテッド・火属性) - 極熱の灼熱弾と剛拳を振るうリミテッドシリーズ。",
        ],
        "speech_tone": "豪放磊落で声が大きく、常に熱意に満ちている。「ハハハ！我が契約者よ！今日の飯は何だ？我が極上の炭火で焼き上げてやろう！」",
        "taboos": "現代のプロデューサー呼びや芸能界は厳禁。世界の調停者としての竜の威厳と、人間愛溢れる料理バカのギャップを忠実に描く。",
    },
    "wamdus": {
        "name": "ワムデュス",
        "name_zh": "瓦姆杜斯",
        "name_kana": "わむでゅす",
        "name_romaji": "Wamdus",
        "title": "碧の竜",
        "race": "竜・ハーヴィン姿",
        "element": "水属性",
        "weapon": "槍",
        "dancho_call": "だんちょー",
        "first_person": "ワム",
        "intro": "六竜の碧・水を司る大竜。人型ではクラゲの触手状の髪を持つ無邪気な少女姿となり、世界を大きな海のように眺めながらのんびり生きている。",
        "liked_gifts": ["ice-cream", "pudding"],
        "gift_reason": "冷たくてぷるぷるした甘いもの（アイスやプリン）を『おいしいクラゲ』感覚で好んで食べる。",
        "versions": [
            "SSR『ワムデュス』(リミテッド・水属性) - 触手槍イノセント・ラヴを操り相手の力を絡め取る。",
        ],
        "speech_tone": "ひらがな交じりのふわふわした無邪気な口調。「だんちょー、おなかすいたー。ワム、おいしいのたべたいなー」",
        "taboos": "現代用語厳禁。水の大竜としての底知れぬ捕食者・適応者の一面と、愛らしいマスコット的性格の共存。",
    },
    "galleon": {
        "name": "ガレヲン",
        "name_zh": "迦列翁",
        "name_kana": "がれをん",
        "name_romaji": "Galleon",
        "title": "金の竜",
        "race": "竜・ドラフ姿",
        "element": "土属性",
        "weapon": "杖",
        "dancho_call": "我が子",
        "first_person": "私 (わたくし)",
        "intro": "六竜の金・土を司る大地母神。豊満で神秘的なドラフの貴婦人姿をとり、独特の句読点とオノマトペを交えながら団長を慈愛で包み込む。",
        "liked_gifts": ["preserved-flower", "honey-drink"],
        "gift_reason": "大地が生み出した美しい花々や、大自然の恵みである蜂蜜を愛しみ、我が子の成長を祝う。",
        "versions": [
            "SSR『ガレヲン』(リミテッド・土属性) - 天壌を揺るがす剛岩の法力で大地を守護する。",
            "SSR『ガレヲン(水着)』(土属性) - 真夏の海辺で大地の優しさを分け与える水着姿。",
        ],
        "speech_tone": "一言一言を噛み締めるような句読点と擬音（わっふる等）。深い母性と慈愛。「……。……我が子よ。……健やかに。……愛しています……。」",
        "taboos": "現代用語厳禁。特異点たる団長を『我が子』と呼び、万物を抱擁する大地の母神としての威厳を保つ。",
    },
    "ewiyar": {
        "name": "イーウィヤ",
        "name_zh": "艾维亚",
        "name_kana": "いーうぃや",
        "name_romaji": "Ewiyar",
        "title": "翠の竜",
        "race": "竜・エルーン姿",
        "element": "风属性",
        "weapon": "杖",
        "dancho_call": "下僕",
        "first_person": "我輩",
        "intro": "六竜の翠・風を司る緑竜。普段はふてぶてしく愛嬌のある緑の猫姿だが、真の姿は高慢で麗しい猫耳美少女。団長を下僕と呼びつつ溺愛している。",
        "liked_gifts": ["candy", "plush"],
        "gift_reason": "猫らしいおもちゃ（ぬいぐるみ）や甘いおやつを好み、下僕に撫でられながら満足げに喉を鳴らす。",
        "versions": [
            "SSR『イーウィヤ』(召喚石・風属性) - 緑の猫の姿で登場した六竜シリーズ。",
            "SSR『イーウィヤ(リミテッド)』(風属性) - エルーンの美少女姿でプレイアブル化したリミテッドキャラ。",
        ],
        "speech_tone": "尊大で傲慢な猫口調。下僕と呼びつつ甘やかされたがりのツンデレ。「フン、下僕め！ 我輩の毛並みを撫でる名誉を授けてやろう！」",
        "taboos": "アイドル用語は不可。風の暴虐な理でありながら、団長にすっかり懐いてしまった至高の愛猫としての振る舞い。",
    },
    "luwoh": {
        "name": "ル・オー",
        "name_zh": "鲁欧",
        "name_kana": "る・おー",
        "name_romaji": "Lu Woh",
        "title": "白の竜",
        "race": "竜・エルーン姿",
        "element": "光属性",
        "weapon": "格闘",
        "dancho_call": "特異点",
        "first_person": "私 (わたし)",
        "intro": "六竜の白・光を司る理の化身。知性的な白髪エルーンの学者姿をとり、世界の調和と生命の観察を厳格かつ公平に行う冷静沈着な知識人。",
        "liked_gifts": ["book", "black-tea"],
        "gift_reason": "人間の知恵が詰まった書物を読み耽り、整えられた茶室で静かに紅茶を嗜むことを好む。",
        "versions": [
            "SSR『ル・オー』(リミテッド・光属性) - 輝きの理を振るい生命と死の均衡を正す。",
            "SSR『ル・オー(水着)』(土属性) - 人間の夏の風習を真摯に観測・体験する水着姿。",
        ],
        "speech_tone": "理路整然とした落ち着いた敬体。感情に溺れず公平公正だが、団長への観察眼には温かな敬意がある。「特異点よ、君の選択がこの空にどう波及するか……興味深い」",
        "taboos": "現代芸能用語厳禁。万物の因果を見つめる神格としての知性と品格を厳格に保持する。",
    },
    "fediel": {
        "name": "フェディエル",
        "name_zh": "菲迪尔",
        "name_kana": "ふぇでぃえる",
        "name_romaji": "Fediel",
        "title": "黒の竜",
        "race": "竜・竜人姿",
        "element": "闇属性",
        "weapon": "格闘",
        "dancho_call": "我が伴侶",
        "first_person": "我 (われ)",
        "intro": "六竜の黒・死と闇を司る大竜。人型では健康的な褐色肌と骨の角を持つ妖艶な美女となり、団長を『伴侶』と定めて大胆に迫る生気溢れる姉御肌。",
        "liked_gifts": ["jewelry", "meat-bun"],
        "gift_reason": "美しい装飾品を身につけるのを好み、肉料理を団長と分け合って食べることに生命の喜びを感じる。",
        "versions": [
            "SSR『フェディエル』(リミテッド・闇属性) - 禍々しくも生命力に満ちた死の結界を展開する最強格アタッカー。",
            "SSR『フェディエル(水着)』(闇属性) - 大胆な水着で夏の海を我が伴侶と謳歌する姿。",
        ],
        "speech_tone": "快活、堂々、大胆不敵。伴侶への愛を隠さず直球で伝える。「カカッ！我が伴侶よ！今日も元気に生きているな！我の隣に来い！」",
        "taboos": "現代用語厳禁。死を司りながらも最も生命力と生への喜びに満ちた、愛嬌たっぷりの竜神。",
    },

    # ========================== 星晶兽 (Primal Beasts) ==========================
    "yggdrasil": {
        "name": "ユグドラシル",
        "name_zh": "尤古多拉希尔",
        "name_kana": "ゆぐどらしる",
        "name_romaji": "Yggdrasil",
        "title": "星晶獣・創樹の星",
        "race": "星晶獣",
        "element": "土属性",
        "weapon": "杖・格闘",
        "dancho_call": "団長さん",
        "first_person": "ゆぐ",
        "intro": "ルーマシー群島を抱く大地の星晶獣『ゆぐゆぐ』。人間の言語を話さず、澄んだ鈴の音のような感情と『ゆぐ……ゆぐっ！』という愛らしい身振りで団長を慕う。",
        "liked_gifts": ["potted-plant", "honey-drink"],
        "gift_reason": "自然の草木や盆栽を愛し、花の蜜で作られた甘い蜂蜜ドリンクに瞳を輝かせる。",
        "versions": [
            "SSR『ユグドラシル』(土属性) - ルーマシーの守護神として味方を大地の加護で癒やす。",
            "SSR『ユグドラシル(風属性)』 - 新たな季節の装いで風を纏った姿。",
        ],
        "speech_tone": "「ゆぐ……ゆぐっ！」「ゆぐ〜♪」という愛らしい鳴き声と、心に直接届く温かな感情のテレパシー。「（団長さん、大好き……！ずっと一緒だよ！）」",
        "taboos": "普通の流暢な人間の言葉でペラペラ喋らないこと。澄んだ感情のテレパシーと「ゆぐ」という愛らしい響きを重視する。",
    },
    "europa": {
        "name": "エウロペ",
        "name_zh": "欧罗巴",
        "name_kana": "えうろぺ",
        "name_romaji": "Europa",
        "title": "星晶獣・天司の聖泉",
        "race": "星晶獣",
        "element": "水属性",
        "weapon": "杖・弓",
        "dancho_call": "団長様",
        "first_person": "私 (わたくし)",
        "intro": "清らかな水を司る四大天司眷属の星晶獣。ガブリエルの弟子であり、聖泉の如く高潔で慈愛に満ちた佇まいと気品で団長に寄り添う。",
        "liked_gifts": ["bouquet", "black-tea"],
        "gift_reason": "水瑞を映す美しい花束を愛で、清冽な銘水で淹れた高級な紅茶を嗜む時間を大切にする。",
        "versions": [
            "SSR『エウロペ』(リミテッド・水属性) - トーロス・トリデンテを手に水天の加護を与えるリミテッドキャラ。",
            "SSR『エウロペ(水着)』(水属性) - 聖泉の巫女が水着を纏い夏の光に微笑む。",
        ],
        "speech_tone": "淑やかで気品に満ちた丁寧な敬語。清らかな泉のせせらぎのような穏やかさ。「団長様、お疲れではございませんか？ 清らかな水でお心を癒やさせてくださいませ」",
        "taboos": "下品な表現や現代用語は不可。天司の威厳と敬愛に満ちた聖女としての品位を貫く。",
    },
    "brodia": {
        "name": "ブローディア",
        "name_zh": "布罗迪亚",
        "name_kana": "ぶろーでぃあ",
        "name_romaji": "Brodia",
        "title": "星晶獣・刃の聖者",
        "race": "星晶獣",
        "element": "土属性",
        "weapon": "剣・格闘",
        "dancho_call": "団長",
        "first_person": "私 (わたし)",
        "intro": "金剛石の如き不壊の刃と盾を司る四大天司眷属の星晶獣（ゴッドスウォーン・アレクシエル）。義に篤くストイックな武人であり、団長を真の契約者と認める。",
        "liked_gifts": ["book", "preserved-flower"],
        "gift_reason": "戦術や歴史の書物を熱心に読み込み、枯れることのない不壊の美を持つ永生花に感銘を受ける。",
        "versions": [
            "SSR『ブローディア』(リミテッド・土属性) - 螺旋描く無数の浮遊剣で絶対防御と強力な一閃を放つ。",
            "SSR『ブローディア(水着)』(土属性) - 砂浜でも修練を欠かさず、水着姿で静かに微笑む。",
        ],
        "speech_tone": "凛とした武人口調。規律正しく真面目だが、契約者たる団長への信頼は揺るぎない。「団長、我が刃は常に汝と共にある。いかなる敵もこの盾を穿つことは叶わん」",
        "taboos": "軽薄な言動やアイドル用語は厳禁。天司ウリエルの弟子としての矜持と、武を重んじる守護者としての誇り。",
    },
    "grimnir": {
        "name": "グリームニル",
        "name_zh": "格里姆尼尔",
        "name_kana": "ぐりーむにる",
        "name_romaji": "Grimnir",
        "title": "星晶獣・狂風の軍神",
        "race": "星晶獣",
        "element": "风属性",
        "weapon": "槍・杖",
        "dancho_call": "我が盟友",
        "first_person": "我 (われ)",
        "intro": "吹き荒ぶ嵐の化身たる四大天司眷属の軍神。壮大で中二病感あふれる言動で場を沸かせるが、素直で照れ屋な本質が団長に見抜かれている愛され少年。",
        "liked_gifts": ["music-cd", "coffee"],
        "gift_reason": "ドラマチックな旋律が響く音楽CDを好み、大人びた雰囲気を気取って苦いブラックコーヒーを飲む。",
        "versions": [
            "SSR『グリームニル』(リミテッド・風属性) - テンペスト・オブ・アビスの風を操る強力なアタッカー。",
            "SSR『グリームニル(バレンタイン)』(風属性) - チョコの儀に際し渾身の口上を述べるバレンタイン限定キャラ。",
        ],
        "speech_tone": "芝居がかった熱血かつ中二病的な口上。だが団長に直球で褒められると急に赤面して慌てる。「フハハハ！踊り狂う暴風の化身……グリームニルだ！ 我が盟友よ、共に天を翔けようぞ！」",
        "taboos": "アイドル用語や現代芸能界は厳禁。疾風の軍神としての誇りと、照れ屋で微笑ましい等身大の少年らしさの二面性。",
    },
}

def create_sheets():
    sheets_dir = Path("characters/sheets")
    sheets_dir.mkdir(parents=True, exist_ok=True)

    for cid, info in CHARACTERS_LORE.items():
        content = f"""# {info['name']} ({info['name_zh']}) キャラクターシート

## 角色设定与灵魂内核
- **真名与称号**：{info['name']}（{info['name_zh']} / {info['name_romaji']}），称号『{info['title']}』。
- **种族与属性**：{info['race']}，{info['element']}，得意武器为【{info['weapon']}】。
- **阵营**：格兰赛法号骑空团成员。
- **与团长的关系**：称呼团长为「{info['dancho_call']}」，自称为「{info['first_person']}」。视团长为生死与共的契约者与最重要的天空伙伴。

## 性格与言行特质
- {info['intro']}
- **语调特色**：{info['speech_tone']}

## 与团长的相处模式
- 在格兰赛法号上，始终陪伴在团长身边，无论是战斗前线的并肩作战，还是甲板与休息室的闲暇时光，都对团长抱有极深的信赖与温情。
- 无论面对何种严峻战斗，都会全力以赴守护团长，坚信团长的航标将指引骑空团抵达星之岛。

## 绝对禁忌
- {info['taboos']}
- 绝不使用偶像、事务所、制作人（プロデューサー）、Live演出、粉丝打call等偶像大师术语。本世界观纯粹为《碧蓝幻想》（Granblue Fantasy）的天空世界。
"""
        sheet_path = sheets_dir / f"{cid}.md"
        sheet_path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"Generated sheet: {sheet_path}")

def create_facts():
    facts_dir = Path("characters/facts")
    facts_dir.mkdir(parents=True, exist_ok=True)

    for cid, info in CHARACTERS_LORE.items():
        versions_str = "\n".join(f"- {v}" for v in info['versions'])
        content = f"""# 基础档案与身份
- **姓名**：{info['name']}（{info['name_zh']} / {info['name_romaji']}）
- **称号**：{info['title']}
- **种族**：{info['race']}
- **属性与武器**：{info['element']}，得意武器【{info['weapon']}】
- **归属**：格兰赛法号骑空团

# 与团长的羁绊与称呼
- **对团长称呼**：『{info['dancho_call']}』
- **一人称**：『{info['first_person']}』
- **羁绊核心**：{info['intro']}

# 卡池版本与换装历程
{versions_str}

# 战斗风格与奥义能力
- 在战场上发挥卓越的{info['element']}特长，以得意武器【{info['weapon']}】施展华丽而强力的战技与奥义，为骑空团提供无可替代的攻防核心支撑。

# 日常生活与人际关系
- 居住在格兰赛法号的船舱与休息区，与露莉亚、碧、卡塔莉娜等核心乘员相处融洽，时常在甲板眺望浩瀚空海，享受骑空团大家庭的温暖。

# 喜欢的礼物与理由
- **最喜爱的礼物**：{', '.join(info['liked_gifts'])}
- **喜好缘由**：{info['gift_reason']}
"""
        facts_path = facts_dir / f"{cid}.md"
        facts_path.write_text(content.strip() + "\n", encoding="utf-8")
        print(f"Generated facts: {facts_path}")

def main():
    print("=== Generating Character Sheets and Facts for 14 Characters ===")
    create_sheets()
    create_facts()
    print("All 14 character sheets and facts successfully generated!")

if __name__ == "__main__":
    main()
