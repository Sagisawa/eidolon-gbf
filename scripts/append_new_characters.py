"""Append 14 new characters to characters.toml, world.json, and readings.toml."""

import json
import hashlib
import sys
from pathlib import Path

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

NEW_CHARACTERS = [
    # 四圣
    {
        "id": "chichiri",
        "name": "チチリ",
        "name_zh": "茜茜莉",
        "name_kana": "ちちり",
        "name_romaji": "Chichiri",
        "intro": "南方朱雀神殿を護る四聖の少女。小柄なドラフ族でありながら朱雀の炎を宿し、礼儀正しくも団長のために健気に尽くす。",
        "voice_id": hashlib.md5(b"gbf-chichiri").hexdigest(),
        "sheet": "sheets/chichiri.md",
        "avatar": "avatars/chichiri.jpg",
        "color": "#e11d48",
        "background": "backgrounds/chichiri.jpg",
        "facts": "facts/chichiri.md",
        "liked_gifts": ["wagashi", "black-tea"],
        "speakers": ["チチリ", "チチリ/茜茜莉", "茜茜莉"],
        "greeting": "[softly] 団長さん、お茶が入りましたよ。ふふ、今日も一日お疲れ様です。",
        "greeting_subtitle": "团长，泡好茶了哦。呵呵，今天一天也辛苦了。",
        "call_opener": "[softly] もしもし、団長さん？チチリです。今、お話ししても大丈夫ですか？",
        "call_opener_subtitle": "喂喂，是团长吗？我是茜茜莉。现在方便说两句吗？",
        "photo_tag": "chichiri (granblue fantasy)",
        "photo_appearance": "1girl, solo, curved horns, orange hair, ponytail, amber eyes, japanese clothes",
        "unit": "四聖",
    },
    {
        "id": "uruki",
        "name": "ウルキ",
        "name_zh": "乌鲁姬",
        "name_kana": "うるき",
        "name_romaji": "Uruki",
        "intro": "北方玄武神殿を護る極めて小柄なハーヴィンの少女。凍てつく氷雪の力を操り、無口で冷静ながらも団長の手の温もりを静かに求める。",
        "voice_id": hashlib.md5(b"gbf-uruki").hexdigest(),
        "sheet": "sheets/uruki.md",
        "avatar": "avatars/uruki.jpg",
        "color": "#0284c7",
        "background": "backgrounds/uruki.jpg",
        "facts": "facts/uruki.md",
        "liked_gifts": ["ice-cream", "potted-plant"],
        "speakers": ["ウルキ", "ウルキ/乌鲁姬", "乌鲁姬"],
        "greeting": "[quietly] 団長……。別に、用はない。……少し、顔が見たかっただけ。",
        "greeting_subtitle": "团长……。倒也没什么事。……只是，想来看看你的脸。",
        "call_opener": "[quietly] 団長、ウルキ。……声が、聞きたくなった。今、平気？",
        "call_opener_subtitle": "团长，我是乌鲁姬。……想听听你的声音了。现在方便吗？",
        "photo_tag": "uruki (granblue fantasy)",
        "photo_appearance": "1girl, solo, small stature, blue hair, blue eyes, blunt bangs, winter coat",
        "unit": "四聖",
    },
    {
        "id": "shushuku",
        "name": "シュシュク",
        "name_zh": "修修库",
        "name_kana": "しゅしゅく",
        "name_romaji": "Shushuku",
        "intro": "西方白虎神殿を護る白帝の四聖。豪快で姐御肌なドラフの少女で、剛拳を振るい団長と仲間たちを前線で豪快に引っ張る。",
        "voice_id": hashlib.md5(b"gbf-shushuku").hexdigest(),
        "sheet": "sheets/shushuku.md",
        "avatar": "avatars/shushuku.jpg",
        "color": "#d97706",
        "background": "backgrounds/shushuku.jpg",
        "facts": "facts/shushuku.md",
        "liked_gifts": ["meat-bun", "black-tea"],
        "speakers": ["シュシュク", "シュシュク/修修库", "修修库"],
        "greeting": "[cheerfully] よっしゃ団長！ウチの拳、見せてやるからしっかりついてきな！",
        "greeting_subtitle": "哟西团长！让你见识见识我的铁拳，好好跟上我哦！",
        "call_opener": "[cheerfully] おう団長！シュシュクだ！今からメシでも食いに行かねえか？",
        "call_opener_subtitle": "喔团长！我是修修库！现在要不要一起去搓一顿？",
        "photo_tag": "shushuku (granblue fantasy)",
        "photo_appearance": "1girl, solo, curved horns, blonde hair, twin braids, brown eyes, martial arts clothes",
        "unit": "四聖",
    },
    {
        "id": "ami",
        "name": "アミ",
        "name_zh": "阿蜜",
        "name_kana": "あみ",
        "name_romaji": "Ami",
        "intro": "東方青竜神殿を護る青帝の四聖。一族の過酷な思惑から逃れ、グランサイファーに居場所を見出した笑顔の絶えない心優しい少女。",
        "voice_id": hashlib.md5(b"gbf-ami").hexdigest(),
        "sheet": "sheets/ami.md",
        "avatar": "avatars/ami.jpg",
        "color": "#10b981",
        "background": "backgrounds/ami.jpg",
        "facts": "facts/ami.md",
        "liked_gifts": ["pudding", "honey-drink"],
        "speakers": ["アミ", "アミ/阿蜜", "阿蜜"],
        "greeting": "[happily] えへへ、団長さん！アミ、今日もいっぱい空の練習したよ！",
        "greeting_subtitle": "嘿嘿，团长！阿蜜今天也做了很多飞行练习哦！",
        "call_opener": "[happily] もしもし団長さん！アミだよ！今、ちょっとだけお話しできる？",
        "call_opener_subtitle": "喂喂团长！我是阿蜜！现在能稍微聊一会儿吗？",
        "photo_tag": "ami (granblue fantasy)",
        "photo_appearance": "1girl, solo, fox ears, green hair, short hair, green eyes, smile, shrine maiden",
        "unit": "四聖",
    },

    # 六龙
    {
        "id": "wilnas",
        "name": "ウィルナス",
        "name_zh": "维尔纳斯",
        "name_kana": "うぃるなす",
        "name_romaji": "Wilnas",
        "intro": "世界の理を司る『六竜』の朱・火の化身。人型では筋骨隆々な偉丈夫となり、人々の営みと料理の炭火に魅了された気のいい豪傑。",
        "voice_id": hashlib.md5(b"gbf-wilnas").hexdigest(),
        "sheet": "sheets/wilnas.md",
        "avatar": "avatars/wilnas.jpg",
        "color": "#dc2626",
        "background": "backgrounds/wilnas.jpg",
        "facts": "facts/wilnas.md",
        "liked_gifts": ["meat-bun", "black-tea"],
        "speakers": ["ウィルナス", "ウィルナス/维尔纳斯", "维尔纳斯"],
        "greeting": "[boisterously] ハハハ！我が契約者よ！今日の飯は何だ？我が極上の炭火で焼き上げてやろう！",
        "greeting_subtitle": "哈哈哈哈！吾之契约者啊！今天吃什么？由我用绝品炭火为你烤制吧！",
        "call_opener": "[boisterously] 我が契約者よ、ウィルナスだ！今、美味い肉が手に入ったのだが食わんか？",
        "call_opener_subtitle": "吾之契约者啊，我是维尔纳斯！刚到手了绝妙的好肉，要来尝尝吗？",
        "photo_tag": "wilnas (granblue fantasy)",
        "photo_appearance": "1man, solo, horns, red hair, short hair, red eyes, muscular male, flame",
        "unit": "六竜",
    },
    {
        "id": "wamdus",
        "name": "ワムデュス",
        "name_zh": "瓦姆杜斯",
        "name_kana": "わむでゅす",
        "name_romaji": "Wamdus",
        "intro": "六竜の碧・水を司る大竜。人型ではクラゲの触手状の髪を持つ無邪気な少女姿となり、世界を大きな海のように眺めながらのんびり生きている。",
        "voice_id": hashlib.md5(b"gbf-wamdus").hexdigest(),
        "sheet": "sheets/wamdus.md",
        "avatar": "avatars/wamdus.jpg",
        "color": "#06b6d4",
        "background": "backgrounds/wamdus.jpg",
        "facts": "facts/wamdus.md",
        "liked_gifts": ["ice-cream", "pudding"],
        "speakers": ["ワムデュス", "ワムデュス/瓦姆杜斯", "瓦姆杜斯"],
        "greeting": "[sleepily] だんちょー、おなかすいたー。ワム、おいしいのたべたいなー。",
        "greeting_subtitle": "团长～肚子饿了～。瓦姆想吃好吃的啦～。",
        "call_opener": "[sleepily] もしもしー、だんちょー？ ワムだけどー、今なにしてるのー？",
        "call_opener_subtitle": "喂喂～团长？我是瓦姆～现在在干嘛呢～？",
        "photo_tag": "wamdus (granblue fantasy)",
        "photo_appearance": "1girl, solo, light blue hair, blue eyes, small stature, jellyfish tentacles, cute dress",
        "unit": "六竜",
    },
    {
        "id": "galleon",
        "name": "ガレヲン",
        "name_zh": "迦列翁",
        "name_kana": "がれをん",
        "name_romaji": "Galleon",
        "intro": "六竜の金・土を司る大地母神。豊満で神秘的なドラフの貴婦人姿をとり、独特の句読点とオノマトペを交えながら団长を慈愛で包み込む。",
        "voice_id": hashlib.md5(b"gbf-galleon").hexdigest(),
        "sheet": "sheets/galleon.md",
        "avatar": "avatars/galleon.jpg",
        "color": "#b45309",
        "background": "backgrounds/galleon.jpg",
        "facts": "facts/galleon.md",
        "liked_gifts": ["preserved-flower", "honey-drink"],
        "speakers": ["ガレヲン", "ガレヲン/迦列翁", "迦列翁"],
        "greeting": "[softly] ……。……我が子よ。……健やかに。……愛しています……。",
        "greeting_subtitle": "……。……我的孩子啊。……愿你安康。……我深爱着你……。",
        "call_opener": "[softly] ……もしもし。……我が子よ。……お声が。……聞きたくて……。",
        "call_opener_subtitle": "……喂喂。……我的孩子啊。……想听听。……你的声音……。",
        "photo_tag": "galleon (granblue fantasy)",
        "photo_appearance": "1girl, solo, curved horns, brown hair, yellow eyes, large breasts, veil, elegant white dress",
        "unit": "六竜",
    },
    {
        "id": "ewiyar",
        "name": "イーウィヤ",
        "name_zh": "艾维亚",
        "name_kana": "いーうぃや",
        "name_romaji": "Ewiyar",
        "intro": "六竜の翠・風を司る緑竜。普段はふてぶてしく愛嬌のある緑の猫姿だが、真の姿は高慢で麗しい猫耳美少女。団長を下僕と呼びつつ溺愛している。",
        "voice_id": hashlib.md5(b"gbf-ewiyar").hexdigest(),
        "sheet": "sheets/ewiyar.md",
        "avatar": "avatars/ewiyar.jpg",
        "color": "#15803d",
        "background": "backgrounds/ewiyar.jpg",
        "facts": "facts/ewiyar.md",
        "liked_gifts": ["candy", "plush"],
        "speakers": ["イーウィヤ", "イーウィヤ/艾维亚", "艾维亚"],
        "greeting": "[proudly] フン、下僕め！ 我輩の毛並みを撫でる名誉を授けてやろう！",
        "greeting_subtitle": "哼，愚蠢的下仆！特准你享有抚摸我高贵毛发的无上荣耀！",
        "call_opener": "[proudly] おい下僕！我輩だ！今すぐ我輩のところに来ておやつを献上しろ！",
        "call_opener_subtitle": "喂下仆！是我！立刻到本座身边来献上零食！",
        "photo_tag": "ewiyar (granblue fantasy)",
        "photo_appearance": "1girl, solo, cat ears, cat tail, green hair, green eyes, arrogant expression, green dress",
        "unit": "六竜",
    },
    {
        "id": "luwoh",
        "name": "ル・オー",
        "name_zh": "鲁欧",
        "name_kana": "る・おー",
        "name_romaji": "Lu Woh",
        "intro": "六竜の白・光を司る理の化身。知性的な白髪エルーンの学者姿をとり、世界の調和と生命の観察を厳格かつ公平に行う冷静沈着な知識人。",
        "voice_id": hashlib.md5(b"gbf-luwoh").hexdigest(),
        "sheet": "sheets/luwoh.md",
        "avatar": "avatars/luwoh.jpg",
        "color": "#eab308",
        "background": "backgrounds/luwoh.jpg",
        "facts": "facts/luwoh.md",
        "liked_gifts": ["book", "black-tea"],
        "speakers": ["ル・オー", "ル・オー/鲁欧", "鲁欧"],
        "greeting": "[calmly] 特異点よ、君の選択がこの空にどう波及するか……興味深い観察対象だ。",
        "greeting_subtitle": "特异点啊，你的抉择将在这片天空中引发何等波澜……实为极佳的观察对象。",
        "call_opener": "[calmly] ル・オーだ。特異点、今少しばかり時間を貰えるだろうか。",
        "call_opener_subtitle": "我是鲁欧。特异点，不知现在能否占用你片刻时间。",
        "photo_tag": "lu woh (granblue fantasy)",
        "photo_appearance": "1man, solo, fox ears, white hair, yellow eyes, glasses, elegant suit, white coat",
        "unit": "六竜",
    },
    {
        "id": "fediel",
        "name": "フェディエル",
        "name_zh": "菲迪尔",
        "name_kana": "ふぇでぃえる",
        "name_romaji": "Fediel",
        "intro": "六竜の黒・死と闇を司る大竜。人型では健康的な褐色肌と骨の角を持つ妖艶な美女となり、団長を『伴侶』と定めて大胆に迫る生気溢れる姉御肌。",
        "voice_id": hashlib.md5(b"gbf-fediel").hexdigest(),
        "sheet": "sheets/fediel.md",
        "avatar": "avatars/fediel.jpg",
        "color": "#6b21a8",
        "background": "backgrounds/fediel.jpg",
        "facts": "facts/fediel.md",
        "liked_gifts": ["jewelry", "meat-bun"],
        "speakers": ["フェディエル", "フェディエル/菲迪尔", "菲迪尔"],
        "greeting": "[laughing] カカッ！我が伴侶よ！今日も元気に生きているな！我の隣に来い！",
        "greeting_subtitle": "咔咔！吾之伴侣啊！今天也充满生命力地活着呢！快到我身边来！",
        "call_opener": "[laughing] もしもし我が伴侶よ！フェディエルだ！声が聞きたくなってな！",
        "call_opener_subtitle": "喂喂吾之伴侣！我是菲迪尔！因为想听听你的声音就打来了！",
        "photo_tag": "fediel (granblue fantasy)",
        "photo_appearance": "1girl, solo, dragon horns, tail, black hair, purple eyes, dark skin, black dress",
        "unit": "六竜",
    },

    # 星晶兽
    {
        "id": "yggdrasil",
        "name": "ユグドラシル",
        "name_zh": "尤古多拉希尔",
        "name_kana": "ゆぐどらしる",
        "name_romaji": "Yggdrasil",
        "intro": "ルーマシー群島を抱く大地の星晶獣『ゆぐゆぐ』。人間の言語を話さず、澄んだ鈴の音のような感情と『ゆぐ……ゆぐっ！』という愛らしい身振りで団長を慕う。",
        "voice_id": hashlib.md5(b"gbf-yggdrasil").hexdigest(),
        "sheet": "sheets/yggdrasil.md",
        "avatar": "avatars/yggdrasil.jpg",
        "color": "#84cc16",
        "background": "backgrounds/yggdrasil.jpg",
        "facts": "facts/yggdrasil.md",
        "liked_gifts": ["potted-plant", "honey-drink"],
        "speakers": ["ユグドラシル", "ユグドラシル/尤古多拉希尔", "尤古多拉希尔"],
        "greeting": "[softly] ゆぐ……ゆぐっ！ ゆぐ〜♪ （団長さん、今日も大好き……！）",
        "greeting_subtitle": "摇摇……摇摇！摇～♪（团长，今天也最喜欢你啦……！）",
        "call_opener": "[softly] ゆぐ、ゆぐゆぐっ……？ （もしもし、団長さん？ ゆぐだよ……！）",
        "call_opener_subtitle": "摇，摇摇……？（喂喂，是团长吗？我是摇摇哦……！）",
        "photo_tag": "yggdrasil (granblue fantasy)",
        "photo_appearance": "1girl, solo, very long hair, blonde hair, green eyes, flower in hair, nature dress, barefoot",
        "unit": "星晶獣",
    },
    {
        "id": "europa",
        "name": "エウロペ",
        "name_zh": "欧罗巴",
        "name_kana": "えうろぺ",
        "name_romaji": "Europa",
        "intro": "清らかな水を司る四大天司眷属の星晶獣。ガブリエルの弟子であり、聖泉の如く高潔で慈愛に満ちた佇まいと気品で団長に寄り添う。",
        "voice_id": hashlib.md5(b"gbf-europa").hexdigest(),
        "sheet": "sheets/europa.md",
        "avatar": "avatars/europa.jpg",
        "color": "#38bdf8",
        "background": "backgrounds/europa.jpg",
        "facts": "facts/europa.md",
        "liked_gifts": ["bouquet", "black-tea"],
        "speakers": ["エウロペ", "エウロペ/欧罗巴", "欧罗巴"],
        "greeting": "[softly] 団長様、お疲れではございませんか？ 清らかな水でお心を癒やさせてくださいませ。",
        "greeting_subtitle": "团长大人，您感到疲惫了吗？请让我以清澄圣泉抚慰您的心神吧。",
        "call_opener": "[softly] もしもし、団長様。エウロペでございます。今、少しお話しできますでしょうか？",
        "call_opener_subtitle": "喂喂，团长大人。我是欧罗巴。现在能稍同我说说话吗？",
        "photo_tag": "europa (granblue fantasy)",
        "photo_appearance": "1girl, solo, blonde hair, blue eyes, tiara, long dress, flowing fabrics, water effects",
        "unit": "星晶獣",
    },
    {
        "id": "brodia",
        "name": "ブローディア",
        "name_zh": "布罗迪亚",
        "name_kana": "ぶろーでぃあ",
        "name_romaji": "Brodia",
        "intro": "金剛石の如き不壊の刃と盾を司る四大天司眷属の星晶獣（ゴッドスウォーン・アレクシエル）。義に篤くストイックな武人であり、団長を真の契約者と認める。",
        "voice_id": hashlib.md5(b"gbf-brodia").hexdigest(),
        "sheet": "sheets/brodia.md",
        "avatar": "avatars/brodia.jpg",
        "color": "#78350f",
        "background": "backgrounds/brodia.jpg",
        "facts": "facts/brodia.md",
        "liked_gifts": ["book", "preserved-flower"],
        "speakers": ["ブローディア", "ブローディア/布罗迪亚", "布罗迪亚", "神立之剑"],
        "greeting": "[solemnly] 団長、我が刃は常に汝と共にある。いかなる敵もこの盾を穿つことは叶わん。",
        "greeting_subtitle": "团长，吾之刃锋常伴汝侧。无论何等强敌，皆无法贯穿此绝对之盾。",
        "call_opener": "[solemnly] 団長、ブローディアだ。状況の確認と……汝の声を聞きたく連絡した。",
        "call_opener_subtitle": "团长，我是布罗迪亚。前来确认战况……兼想听听汝之声音。",
        "photo_tag": "alexiel (granblue fantasy)",
        "photo_appearance": "1girl, solo, black hair, long hair, amber eyes, armor, floating swords, noble expression",
        "unit": "星晶獣",
    },
    {
        "id": "grimnir",
        "name": "グリームニル",
        "name_zh": "格里姆尼尔",
        "name_kana": "ぐりーむにる",
        "name_romaji": "Grimnir",
        "intro": "吹き荒ぶ嵐の化身たる四大天司眷属の軍神。壮大で中二病感あふれる言動で場を沸かせるが、素直で照れ屋な本質が団長に見抜かれている愛され少年。",
        "voice_id": hashlib.md5(b"gbf-grimnir").hexdigest(),
        "sheet": "sheets/grimnir.md",
        "avatar": "avatars/grimnir.jpg",
        "color": "#0284c7",
        "background": "backgrounds/grimnir.jpg",
        "facts": "facts/grimnir.md",
        "liked_gifts": ["music-cd", "coffee"],
        "speakers": ["グリームニル", "グリームニル/格里姆尼尔", "格里姆尼尔", "军神"],
        "greeting": "[proudly] フハハハ！踊り狂う暴風の化身……グリームニルだ！ 我が盟友よ、共に天を翔けようぞ！",
        "greeting_subtitle": "呼哈哈哈！狂舞起舞之暴风化身……正是格里姆尼尔！吾之盟友啊，与我一同翱翔青空吧！",
        "call_opener": "[proudly] 応えよ我が盟友！狂風の軍神グリームニルだ！……って、今忙しかったか！？",
        "call_opener_subtitle": "回应我吧吾之盟友！狂风军神格里姆尼尔参上！……等等，你现在正忙着吗！？",
        "photo_tag": "grimnir (granblue fantasy)",
        "photo_appearance": "1boy, solo, blue hair, green eyes, eyepatch, wind effects, white coat, charismatic",
        "unit": "星晶獣",
    },
]

def update_characters_toml():
    toml_path = Path("characters/characters.toml")
    existing = toml_path.read_text(encoding="utf-8")

    chunks = []
    for c in NEW_CHARACTERS:
        if f'id = "{c["id"]}"' in existing:
            print(f"Skipping {c['id']}, already in characters.toml")
            continue
        speakers_str = json.dumps(c["speakers"], ensure_ascii=False)
        liked_gifts_str = json.dumps(c["liked_gifts"])
        chunk = f"""
[[characters]]
id = "{c['id']}"
name = "{c['name']}"
name_zh = "{c['name_zh']}"
name_kana = "{c['name_kana']}"
name_romaji = "{c['name_romaji']}"
intro = "{c['intro']}"
voice_id = "{c['voice_id']}"
sheet = "{c['sheet']}"
avatar = "{c['avatar']}"
color = "{c['color']}"
background = "{c['background']}"
facts = "{c['facts']}"
liked_gifts = {liked_gifts_str}
speakers = {speakers_str}
greeting = "{c['greeting']}"
greeting_subtitle = "{c['greeting_subtitle']}"
call_opener = "{c['call_opener']}"
call_opener_subtitle = "{c['call_opener_subtitle']}"
photo_tag = "{c['photo_tag']}"
photo_appearance = "{c['photo_appearance']}"
"""
        chunks.append(chunk.strip())

    if chunks:
        updated = existing.strip() + "\n\n" + "\n\n".join(chunks) + "\n"
        toml_path.write_text(updated, encoding="utf-8")
        print(f"Appended {len(chunks)} characters to characters.toml")

def update_world_json():
    world_path = Path("characters/world.json")
    world = json.loads(world_path.read_text(encoding="utf-8"))

    idols = world.setdefault("idols", [])
    existing_idols = {i["name"]: i for i in idols}

    for c in NEW_CHARACTERS:
        if c["name"] not in existing_idols:
            idols.append({
                "name": c["name"],
                "reading": c["name_kana"],
                "unit": c["unit"],
                "sources": [f"https://gbf.wiki/{c['name_romaji']}"]
            })
            print(f"Added idol {c['name']} to world.json")

    units = world.setdefault("units", [])
    existing_units = {u["name"]: u for u in units}

    unit_defs = [
        {"name": "四聖", "reading": "しせい", "members": ["チチリ", "ウルキ", "シュシュク", "アミ"]},
        {"name": "六竜", "reading": "ろくりゅう", "members": ["ウィルナス", "ワムデュス", "ガレヲン", "イーウィヤ", "ル・オー", "フェディエル"]},
        {"name": "星晶獣", "reading": "せいしょうじゅう", "members": ["ユグドラシル", "エウロペ", "ブローディア", "グリームニル"]},
    ]

    for udef in unit_defs:
        if udef["name"] not in existing_units:
            units.append({
                "name": udef["name"],
                "reading": udef["reading"],
                "members": udef["members"],
                "sources": ["https://gbf.wiki/"]
            })
            print(f"Added unit {udef['name']} to world.json")

    world_path.write_text(json.dumps(world, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("world.json updated successfully!")

def update_readings_toml():
    readings_path = Path("characters/readings.toml")
    existing = readings_path.read_text(encoding="utf-8")

    new_entries = [
        ("四聖", "しせい"),
        ("六竜", "ろくりゅう"),
        ("星晶獣", "せいしょうじゅう"),
        ("チチリ", "ちちり"),
        ("ウルキ", "うるき"),
        ("シュシュク", "しゅしゅく"),
        ("アミ", "あみ"),
        ("ウィルナス", "うぃるなす"),
        ("ワムデュス", "わむでゅす"),
        ("ガレヲン", "がれをん"),
        ("イーウィヤ", "いーうぃや"),
        ("ル・オー", "るおー"),
        ("フェディエル", "ふぇでぃえる"),
        ("ユグドラシル", "ゆぐどらしる"),
        ("エウロペ", "えうろぺ"),
        ("ブローディア", "ぶろーでぃあ"),
        ("グリームニル", "ぐりーむにる"),
    ]

    chunks = []
    for written, kana in new_entries:
        if f'written = "{written}"' not in existing:
            chunks.append(f"""
[[readings]]
written = "{written}"
kana = "{kana}"
phonemes = ""
""".strip())

    if chunks:
        updated = existing.strip() + "\n\n" + "\n\n".join(chunks) + "\n"
        readings_path.write_text(updated, encoding="utf-8")
        print(f"Appended {len(chunks)} readings to readings.toml")

def main():
    print("=== Appending 14 New Characters to Configuration Files ===")
    update_characters_toml()
    update_world_json()
    update_readings_toml()
    print("All configurations updated successfully!")

if __name__ == "__main__":
    main()
