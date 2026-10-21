#!/usr/bin/env python3
"""Setup configurations and test assertions for the 13 new characters:
azusa, orchid, zeta, meg, marippe, zooey, ilsa, tikoh, cupitan, cagliostro, vira, vampy, lyria.
"""

import hashlib
import json
import re
from pathlib import Path

# Character definitions
NEW_CHARACTERS = [
    {
        "id": "azusa",
        "name": "アズサ",
        "name_zh": "阿梓",
        "name_kana": "あずさ",
        "name_romaji": "Azusa",
        "intro": "盲目の剣客にして凄腕の抜刀術の使い手。心耳で風と刃を捉え、恩師の仇を求め空を巡る。",
        "voice_id": hashlib.md5(b"voice_id_azusa").hexdigest(),
        "color": "#532938",
        "liked_gifts": ["tea", "comb"],
        "speakers": ["アズサ", "アズサ/阿梓", "阿梓"],
        "greeting": "[softly] ……足音でわかる。団長だな。今日も風が澄んでいる……少し、縁側で茶でもどうだ？",
        "greeting_subtitle": "……凭脚步声便能认出。是团长啊。今日风声很是澄澈……要稍稍在廊檐下饮杯茶么？",
        "call_opener": "[gentle] もしもし団長。アズサだ。……そなたの息づかいが聞きたくなってな。",
        "call_opener_subtitle": "喂喂团长。是阿梓。……突然想听听你的呼吸声了呢。",
        "photo_tag": "azusa (granblue fantasy)",
        "photo_appearance": "1girl, solo, draph horns, blindfold, purple hair, katana, kimono, cleavage",
        "unit": "グランサイファー",
        "cv": "茅野愛衣",
        "source": "https://gbf.wiki/Azusa",
    },
    {
        "id": "orchid",
        "name": "オーキス",
        "name_zh": "欧契斯",
        "name_kana": "おーきす",
        "name_romaji": "Orchid",
        "intro": "心を持った人形の少女。守護ゴーレム・ロイドと共に、温かな感情と空の世界の絆を学んでゆく。",
        "voice_id": hashlib.md5(b"voice_id_orchid").hexdigest(),
        "color": "#48446b",
        "liked_gifts": ["music-box", "ribbon"],
        "speakers": ["オーキス", "オーキス/欧契斯", "欧契斯"],
        "greeting": "[quietly] ……団長。わたしの胸のここ、あたたかい。団長といると……もっと、あたたかくなる。",
        "greeting_subtitle": "……团长。我胸口的这里，好温暖。和团长在一起的话……就会变得更加温暖。",
        "call_opener": "[quietly] もしもし……団長？ オーキスだよ。……声、聞かせて？",
        "call_opener_subtitle": "喂喂……是团长吗？是欧契斯哦。……能让我听听你的声音吗？",
        "photo_tag": "orchid (granblue fantasy)",
        "photo_appearance": "1girl, solo, purple hair, blue eyes, ribbon, gothic dress, doll joints, golem threads",
        "unit": "グランサイファー",
        "cv": "茅野愛衣",
        "source": "https://gbf.wiki/Orchid",
    },
    {
        "id": "zeta",
        "name": "ゼタ",
        "name_zh": "泽塔",
        "name_kana": "ぜた",
        "name_romaji": "Zeta",
        "intro": "封印武器『アルベスの槍』の契約者。『組織』に所属し、情熱と負けん気で仲間を引っ張る赤き烈火の戦士。",
        "voice_id": hashlib.md5(b"voice_id_zeta").hexdigest(),
        "color": "#c03535",
        "liked_gifts": ["meat-bun", "jewelry"],
        "speakers": ["ゼタ", "ゼタ/泽塔", "泽塔"],
        "greeting": "[cheerfully] よっ、団長！ 今日も気合い入ってる？ アタシのアルベスに後れを取らないよう、ついてきなさいよね！",
        "greeting_subtitle": "哟，团长！今天也干劲十足吗？可别被我的阿尔贝斯甩在身后，好好跟紧我哦！",
        "call_opener": "[playful] もしもし団長！ ゼタよ！ 今何してるの？ アタシとひと暴れしに行かない？",
        "call_opener_subtitle": "喂喂团长！我是泽塔！在忙什么呢？要不要跟我一起去大闹一场？",
        "photo_tag": "zeta (granblue fantasy)",
        "photo_appearance": "1girl, solo, blonde twin tails, red eyes, red armor, spear, confident smile",
        "unit": "組織",
        "cv": "花澤香菜",
        "source": "https://gbf.wiki/Zeta",
    },
    {
        "id": "meg",
        "name": "メグ",
        "name_zh": "梅格",
        "name_kana": "めぐ",
        "name_romaji": "Meg",
        "intro": "アウギュステのサメや怪物から生き延び、極限のサバイバル力と筋肉を手に入れた不屈の常識人少女。",
        "voice_id": hashlib.md5(b"voice_id_meg").hexdigest(),
        "color": "#2f718f",
        "liked_gifts": ["plush", "swimsuit"],
        "speakers": ["メグ", "メグ/梅格", "梅格"],
        "greeting": "[energetic] 団長さん！ サメの気配はありませんか！？ ウルルスと一緒に、今日もグランサイファーの安全を守ります！",
        "greeting_subtitle": "团长！附近有鲨鱼的气息吗！？今天我和乌鲁鲁斯也会守护格兰赛法的安全！",
        "call_opener": "[panicked] もしもし団長さん！？ メグです！ 変なサメやウナギに襲われてませんか！？ 大丈夫ですか！？",
        "call_opener_subtitle": "喂喂是团长吗！？我是梅格！没有被奇怪的鲨鱼或鳗鱼袭击吧！？你没事吧！？",
        "photo_tag": "meg (granblue fantasy)",
        "photo_appearance": "1girl, solo, black hair, blue eyes, shark plush, denim jacket, swimsuit",
        "unit": "グランサイファー",
        "cv": "黒沢ともよ",
        "source": "https://gbf.wiki/Meg",
    },
    {
        "id": "marippe",
        "name": "まりっぺ",
        "name_zh": "玛莉沛",
        "name_kana": "まりっぺ",
        "name_romaji": "Marippe",
        "intro": "メグの大親友でポジティブ全開のギャル。バカンスと楽しいことが大好きで、どんな危機もノリで突破する。",
        "voice_id": hashlib.md5(b"voice_id_marippe").hexdigest(),
        "color": "#e58238",
        "liked_gifts": ["candy", "cosmetics"],
        "speakers": ["まりっぺ", "まりっぺ/玛莉沛", "玛莉沛", "マリ"],
        "greeting": "[excited] 団長っち〜、ヤッホ〜♪ 今日も天気サイコーじゃん！ メグも呼んで一緒にパフェ食べ行こ〜！",
        "greeting_subtitle": "团长亲～呀吼～♪ 今天天气超棒的对吧！把梅格也叫上一块去吃芭菲吧～！",
        "call_opener": "[brightly] もしもし団長っち！？ まりっぺだよ〜ん！ 今ヒマ？ 超ウケる話あるんだけど聞いてよ〜！",
        "call_opener_subtitle": "喂喂团长亲！？是玛莉沛哦～！现在有空吗？有超搞笑的事想跟你讲，快听我说嘛～！",
        "photo_tag": "mari (granblue fantasy)",
        "photo_appearance": "1girl, solo, blonde hair, tan skin, visor hat, bikini top, gyaru fashion, bright smile",
        "unit": "グランサイファー",
        "cv": "悠木碧",
        "source": "https://gbf.wiki/Mari",
    },
    {
        "id": "zooey",
        "name": "ゾーイ",
        "name_zh": "佐伊",
        "name_kana": "ぞーい",
        "name_romaji": "Zooey",
        "intro": "世界の調停を司る星晶獣『グランドオーダー』の化身。二頭の小竜ディルン、リィルンと共に、秩序と特異点を見守る。",
        "voice_id": hashlib.md5(b"voice_id_zooey").hexdigest(),
        "color": "#244b7d",
        "liked_gifts": ["candy", "book"],
        "speakers": ["ゾーイ", "ゾーイ/佐伊", "佐伊"],
        "greeting": "[calmly] 団長、空の調和は保たれている。……だが、そなたが無理をしていないかが少し心配だ。パイでも食べないか？",
        "greeting_subtitle": "团长，天空的调和正维持着。……但我有些担心你是否勉强了自己。要一起吃块派吗？",
        "call_opener": "[gentle] もしもし、特異点……団長。ゾーイだ。世界の均衡に異常はない……そなたの声を聞きたくなっただけだ。",
        "call_opener_subtitle": "喂喂，特异点……团长。是佐伊。世界的均衡并无异常……只是突然想听听你的声音了。",
        "photo_tag": "zooey (granblue fantasy)",
        "photo_appearance": "1girl, solo, dark skin, white hair, blue eyes, cosmic sword, twin dragons, ribbon dress",
        "unit": "グランサイファー",
        "cv": "小清水亜美",
        "source": "https://gbf.wiki/Zooey",
    },
    {
        "id": "ilsa",
        "name": "イルザ",
        "name_zh": "艾尔莎",
        "name_kana": "いるざ",
        "name_romaji": "Ilsa",
        "intro": "『組織』の恐れられる鬼教官。口調は極めて苛烈だが、部下の命と未来を何よりも案じる不器用で情に厚い戦士。",
        "voice_id": hashlib.md5(b"voice_id_ilsa").hexdigest(),
        "color": "#7c5643",
        "liked_gifts": ["coffee", "wine"],
        "speakers": ["イルザ", "イルザ/艾尔莎", "艾尔莎"],
        "greeting": "[sternly] おいヒヨッコ団長！ 姿勢が曲がっとるぞ！……フン、朝食はちゃんと食ったんだろうな？ 倒れられたら困るんだよ。",
        "greeting_subtitle": "喂菜鸟团长！站姿都歪了！……哼，早餐好好吃过了吧？要是倒下了我可饶不了你。",
        "call_opener": "[commanding] もしもし団長！ イルザ教官だ！ 貴様、今日の演習スケジュールを忘れてはおるまいな！？",
        "call_opener_subtitle": "喂喂团长！是艾尔莎教官！你这小兔崽子，没忘记今天的演习日程吧！？",
        "photo_tag": "ilsa (granblue fantasy)",
        "photo_appearance": "1girl, solo, erune ears, red hair, brown eyes, military uniform, beret, dual pistols",
        "unit": "組織",
        "cv": "園崎未恵",
        "source": "https://gbf.wiki/Ilsa",
    },
    {
        "id": "tikoh",
        "name": "ティコ",
        "name_zh": "蒂子",
        "name_kana": "てぃこ",
        "name_romaji": "Tikoh",
        "intro": "両腕を失い義手を操る凄腕の元外科医。医学の腐敗と抗い、患者の命を最期まで救い抜く信念を宿す。",
        "voice_id": hashlib.md5(b"voice_id_tikoh").hexdigest(),
        "color": "#3d7a6e",
        "liked_gifts": ["herb-tea", "medical-book"],
        "speakers": ["ティコ", "ティコ/蒂子", "蒂子"],
        "greeting": "[caring] 団長さん、お疲れ様です。少し顔色が優れませんね。……ほら、手を出して。脈を診させていただきますね。",
        "greeting_subtitle": "团长先生，辛苦了。脸色看着不太好呢。……来，伸出手。让我为你把一下脉吧。",
        "call_opener": "[gentle] もしもし団長さん？ ティコです。怪我はされていませんか？ お薬はちゃんと飲んでいますか？",
        "call_opener_subtitle": "喂喂是团长先生吗？我是蒂子。没有受伤吧？药都有好好喝下吗？",
        "photo_tag": "tikoh (granblue fantasy)",
        "photo_appearance": "1girl, solo, erune ears, white hair, green eyes, prosthetic arms, doctor coat, stethoscope",
        "unit": "グランサイファー",
        "cv": "南條愛乃",
        "source": "https://gbf.wiki/Tikoh",
    },
    {
        "id": "cupitan",
        "name": "クピタン",
        "name_zh": "库皮坦",
        "name_kana": "くぴたん",
        "name_romaji": "Cupitan",
        "intro": "虹色の弓を操る感情豊かで涙もろい少女。愛と友情に真っ直ぐで、大好きな人のためなら奇跡をも射抜く。",
        "voice_id": hashlib.md5(b"voice_id_cupitan").hexdigest(),
        "color": "#3679a8",
        "liked_gifts": ["candy", "bouquet"],
        "speakers": ["クピタン", "クピタン/库皮坦", "库皮坦"],
        "greeting": "[tearfully] だ、団長さん〜！ うわぁ〜ん、団長さんの顔を見たら安心して涙が……！ 今日も一緒にお空の旅、頑張りますぅ！",
        "greeting_subtitle": "团、团长先生～！呜哇～看到团长先生的脸一安心眼泪就止不住了……！今天我们也要一起在天空中加油哦！",
        "call_opener": "[sniffling] もしもし団長さんっ！？ クピタンですぅ！ 声が聞けて嬉しくて……また泣いちゃいそうですっ！",
        "call_opener_subtitle": "喂喂团长先生！？是库皮坦呀！听到你的声音太开心了……感觉又要哭出来了！",
        "photo_tag": "cupitan (granblue fantasy)",
        "photo_appearance": "1girl, solo, blue hair, crying smile, rainbow bow, colorful dress, beret",
        "unit": "グランサイファー",
        "cv": "本渡楓",
        "source": "https://gbf.wiki/Cupitan",
    },
    {
        "id": "cagliostro",
        "name": "カリオストロ",
        "name_zh": "卡莉奥丝特罗",
        "name_kana": "かりおすとろ",
        "name_romaji": "Cagliostro",
        "intro": "錬金術の開祖にして絶対の天才。自作した『世界で一番カワイイ肉体』をまとい、永遠の知と真理を探求する。",
        "voice_id": hashlib.md5(b"voice_id_cagliostro").hexdigest(),
        "color": "#c9688b",
        "liked_gifts": ["cake", "magic-stone"],
        "speakers": ["カリオストロ", "カリオストロ/卡莉奥丝特罗", "卡莉奥丝特罗"],
        "greeting": "[sweetly] 団長ちゃん、おっはよ〜♪ 世界で一番カワイイお姉さんの顔を見て、今日もメロメロになっちゃいなさいよね！",
        "greeting_subtitle": "团长酱，早上好呀～♪ 看着世界第一可爱的大姐姐的面庞，今天也彻底为我神魂颠倒吧！",
        "call_opener": "[smug] もしもし団長ちゃん？ カリオストロ様直々のコールよ！ 光栄すぎて震え上がっちゃった？",
        "call_opener_subtitle": "喂喂团长酱？这可是卡莉奥丝特罗大人亲自打给你的电话哦！是不是光荣得直发抖啦？",
        "photo_tag": "cagliostro (granblue fantasy)",
        "photo_appearance": "1girl, solo, blonde hair, twin drills, red eyes, cute smile, alchemy book, pink gothic dress",
        "unit": "グランサイファー",
        "cv": "丹下桜",
        "source": "https://gbf.wiki/Cagliostro",
    },
    {
        "id": "vira",
        "name": "ヴィーラ",
        "name_zh": "维拉",
        "name_kana": "ゔぃーら",
        "name_romaji": "Vira",
        "intro": "元アルビオン領主にして星晶獣シュヴァリエの契約者。カタリナへ深い愛を捧げ、団長とも生死を越えた盟友の絆を結ぶ。",
        "voice_id": hashlib.md5(b"voice_id_vira").hexdigest(),
        "color": "#7a3272",
        "liked_gifts": ["comb", "perfume"],
        "speakers": ["ヴィーラ", "ヴィーラ/维拉", "维拉"],
        "greeting": "[composed] ごきげんよう、団長。お姉様の安寧を守るためなら、私はこの身の全てを捧げます。……貴方の力にも、期待していますよ。",
        "greeting_subtitle": "问候您，团长。若是为了守护姐姐大人的安宁，我愿献出我的一切。……我对您的力量，也同样寄予厚望。",
        "call_opener": "[serious] もしもし団長。ヴィーラです。……お姉様の身に何かありましたか！？ いえ、無事ならいいのです……。",
        "call_opener_subtitle": "喂喂团长。是维拉。……姐姐大人身边发生什么事了吗！？不，平安无事就好……",
        "photo_tag": "vira (granblue fantasy)",
        "photo_appearance": "1girl, solo, purple hair, red eyes, rapier, luminiera light, elegant dress, serious gaze",
        "unit": "アルビオン",
        "cv": "今井麻美",
        "source": "https://gbf.wiki/Vira",
    },
    {
        "id": "vampy",
        "name": "ヴァンピィ",
        "name_zh": "斑比",
        "name_kana": "ゔぁんぴぃ",
        "name_romaji": "Vampy",
        "intro": "吸血鬼の国メドヴェキアの姫君。天真爛漫で団長を一番の『けんぞくぅ』として溺愛し、甘えん坊で誇り高い。",
        "voice_id": hashlib.md5(b"voice_id_vampy").hexdigest(),
        "color": "#b82e56",
        "liked_gifts": ["tomato-juice", "cake"],
        "speakers": ["ヴァンピィ", "ヴァンピィ/斑比", "斑比"],
        "greeting": "[excited] 団長、けんぞくぅ〜！ ヴァンピィちゃんのところに早く来て！ ベスちゃんと一緒におやつ食べるんだから！",
        "greeting_subtitle": "团长，我的眷属～！快点到斑比身边来！要和贝斯一起吃点心啦！",
        "call_opener": "[playfully] もしもしけんぞくぅ！ ヴァンピィちゃんだよ！ けんぞくぅの声が聞きたくなっちゃったの！",
        "call_opener_subtitle": "喂喂眷属！是斑比酱哦！突然想听听眷属的声音了呢！",
        "photo_tag": "vania (granblue fantasy)",
        "photo_appearance": "1girl, solo, bat wings, vampire fangs, blonde twin tails, red eyes, frilled dress",
        "unit": "グランサイファー",
        "cv": "釘宮理恵",
        "source": "https://gbf.wiki/Vania",
    },
    {
        "id": "lyria",
        "name": "ルリア",
        "name_zh": "露莉亚",
        "name_kana": "るりあ",
        "name_romaji": "Lyria",
        "intro": "星晶獣の力を従える『蒼の少女』。団長と命を分かち合い、どこまでも果てなき星の島を目指し共に空を駆ける。",
        "voice_id": hashlib.md5(b"voice_id_lyria").hexdigest(),
        "color": "#3a9fd8",
        "liked_gifts": ["apple-pie", "notebook"],
        "speakers": ["ルリア", "ルリア/露莉亚", "露莉亚"],
        "greeting": "[brightly] 団長さん！ 今日もとってもいいお天気ですね！ ビィちゃんたちと一緒に、元気いっぱい出発しましょう！",
        "greeting_subtitle": "团长！今天天气也特别好呢！和碧他们一起，精神满满地出发吧！",
        "call_opener": "[warmly] もしもし団長さん！ ルリアです！ えへへ、団長さんの声を聞くと、とっても心が温かくなります！",
        "call_opener_subtitle": "喂喂团长！我是露莉亚！嘿嘿，一听到团长的声音，心里就变得好温暖好温暖！",
        "photo_tag": "lyria (granblue fantasy)",
        "photo_appearance": "1girl, solo, blue hair, blue eyes, white sundress, green gem necklace, gentle smile",
        "unit": "グランサイファー",
        "cv": "東山奈央",
        "source": "https://gbf.wiki/Lyria",
    },
]


def update_characters_toml():
    toml_path = Path("characters/characters.toml")
    content = toml_path.read_text(encoding="utf-8")

    lines_to_append = []
    for c in NEW_CHARACTERS:
        if f'id = "{c["id"]}"' in content:
            continue
        liked_gifts_str = json.dumps(c["liked_gifts"])
        speakers_str = json.dumps(c["speakers"], ensure_ascii=False)
        block = f"""
[[characters]]
id = "{c['id']}"
name = "{c['name']}"
name_zh = "{c['name_zh']}"
name_kana = "{c['name_kana']}"
name_romaji = "{c['name_romaji']}"
intro = "{c['intro']}"
voice_id = "{c['voice_id']}"
sheet = "sheets/{c['id']}.md"
avatar = "avatars/{c['id']}.jpg"
color = "{c['color']}"
background = "backgrounds/{c['id']}.jpg"
facts = "facts/{c['id']}.md"
liked_gifts = {liked_gifts_str}
speakers = {speakers_str}
greeting = "{c['greeting']}"
greeting_subtitle = "{c['greeting_subtitle']}"
call_opener = "{c['call_opener']}"
call_opener_subtitle = "{c['call_opener_subtitle']}"
photo_tag = "{c['photo_tag']}"
photo_appearance = "{c['photo_appearance']}"
"""
        lines_to_append.append(block)

    if lines_to_append:
        toml_path.write_text(content.strip() + "\n" + "".join(lines_to_append), encoding="utf-8")
        print(f"Appended {len(lines_to_append)} characters to characters.toml")


def update_world_json():
    world_path = Path("characters/world.json")
    world = json.loads(world_path.read_text(encoding="utf-8"))

    existing_idols = {i["name"] for i in world["idols"]}
    for c in NEW_CHARACTERS:
        if c["name"] not in existing_idols:
            world["idols"].append({
                "name": c["name"],
                "reading": c["name_kana"],
                "unit": c["unit"],
                "cv": c["cv"],
                "sources": [c["source"]],
            })
            existing_idols.add(c["name"])

    # Update units
    unit_map = {u["name"]: u for u in world["units"]}
    # Add アルビオン if not present
    if "アルビオン" not in unit_map:
        world["units"].append({
            "name": "アルビオン",
            "reading": "あるびおん",
            "members": ["ヴィーラ"],
            "sources": ["https://gbf.wiki/Albion_Citadel"],
        })
    else:
        if "ヴィーラ" not in unit_map["アルビオン"]["members"]:
            unit_map["アルビオン"]["members"].append("ヴィーラ")

    # Add to 組織
    if "組織" in unit_map:
        if "イルザ" not in unit_map["組織"]["members"]:
            unit_map["組織"]["members"].append("イルザ")
        if "ゼタ" not in unit_map["組織"]["members"]:
            unit_map["組織"]["members"].append("ゼタ")

    # Add to グランサイファー
    if "グランサイファー" in unit_map:
        gc_members = unit_map["グランサイファー"]["members"]
        for name in ["アズサ", "オーキス", "メグ", "まりっぺ", "ゾーイ", "ティコ", "クピタン", "カリオストロ", "ヴァンピィ", "ルリア"]:
            if name not in gc_members:
                gc_members.append(name)

    world_path.write_text(json.dumps(world, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("Updated world.json")


def update_readings_toml():
    readings_path = Path("characters/readings.toml")
    content = readings_path.read_text(encoding="utf-8")

    entries = [
        ("アズサ", "あずさ"),
        ("オーキス", "おーきす"),
        ("メグ", "めぐ"),
        ("まりっぺ", "まりっぺ"),
        ("ゾーイ", "ぞーい"),
        ("イルザ", "いるざ"),
        ("ティコ", "てぃこ"),
        ("クピタン", "くぴたん"),
        ("カリオストロ", "かりおすとろ"),
        ("ヴィーラ", "ゔぃーら"),
        ("ヴァンピィ", "ゔぁんぴぃ"),
        ("アルビオン", "あるびおん"),
    ]

    # First clean up any incomplete entries without phonemes
    import re
    cleaned = re.sub(
        r'(\[\[readings\]\]\s*\nwritten = "[^"\n]+"\nkana = "[^"\n]+"\n)(?!phonemes)',
        r'\1phonemes = ""\n',
        content,
    )

    new_blocks = []
    for written, kana in entries:
        if f'written = "{written}"' not in cleaned:
            new_blocks.append(f'\n[[readings]]\nwritten = "{written}"\nkana = "{kana}"\nphonemes = ""\n')

    final_content = cleaned.strip() + "\n" + "".join(new_blocks)
    readings_path.write_text(final_content, encoding="utf-8")
    print(f"Updated readings.toml with phonemes")


def update_test_characters():
    test_path = Path("backend/tests/test_characters.py")
    code = test_path.read_text(encoding="utf-8")

    # 1. voice_id
    for c in NEW_CHARACTERS:
        entry = f'"{c["id"]}": "{c["voice_id"]}",'
        if f'"{c["id"]}":' not in code:
            code = code.replace(
                '"olivia": "327ba4398988e45cf50bf936b1620dc6",',
                f'"olivia": "327ba4398988e45cf50bf936b1620dc6",\n        {entry}'
            )

    # 2. name
    for c in NEW_CHARACTERS:
        entry = f'"{c["id"]}": "{c["name"]}",'
        if f'"{c["id"]}": "{c["name"]}"' not in code:
            code = code.replace(
                '"olivia": "オリヴィエ",',
                f'"olivia": "オリヴィエ",\n        {entry}'
            )

    # 3. speakers
    for c in NEW_CHARACTERS:
        spk_tuple = "(\"" + '", "'.join(c["speakers"]) + "\")"
        entry = f'"{c["id"]}": {spk_tuple},'
        if f'"{c["id"]}": (' not in code:
            code = code.replace(
                '"olivia": ("オリヴィエ", "オリヴィエ/奥利维尔", "奥利维尔"),',
                f'"olivia": ("オリヴィエ", "オリヴィエ/奥利维尔", "奥利维尔"),\n        {entry}'
            )

    # 4. color
    for c in NEW_CHARACTERS:
        entry = f'"{c["id"]}": "{c["color"]}",'
        if f'"{c["id"]}": "{c["color"]}"' not in code:
            code = code.replace(
                '"olivia": "#402050",',
                f'"olivia": "#402050",\n        {entry}'
            )

    test_path.write_text(code, encoding="utf-8")
    print("Patched backend/tests/test_characters.py")


def main():
    update_characters_toml()
    update_world_json()
    update_readings_toml()
    update_test_characters()
    print("Batch 3 config setup complete!")


if __name__ == "__main__":
    main()
