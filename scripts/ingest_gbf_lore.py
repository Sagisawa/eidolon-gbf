"""Ingest all Granblue Fantasy lore data into data/eidolon.db:
- All 26 chapters of 《除夜の終わりに響く鐘》 (dialogues + synopsis) with cast: vikala
- All Fate Episodes for Narmaya and Vikala
- 10-year seasonal Special Cutscenes (Birthday, Valentine, New Year, White Day, Halloween)
- Full passages indexing for vector retrieval
- SQLite FTS5 index with native BM25 ranking for fast and accurate RAG
"""

import csv
import json
import os
import re
import sqlite3
import sys
from pathlib import Path

# Fix Windows stdout encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

# Add backend to sys.path
sys.path.insert(0, str(Path("backend/src").resolve()))

from eidolon.characters import load_characters
from eidolon.corpus import _SCHEMA, Line, Episode, _passages, passage_title
from eidolon.database import connect
from eidolon.story_import import _read_csv, _speaker_index, _cast, ImportReport
from eidolon.world import load_world, world_path

DB_PATH = Path("data/eidolon.db")
CORPUS_DIR = Path("corpus/gbf")
CHARS_FILE = Path("characters/characters.toml")
WORLD_FILE = Path("characters/world.json")

NIER_EPISODE_TITLES = {
    "scene_nier_q1_s10": "命运篇章 前篇「家族の望みと孤独な少女」",
    "scene_nier_q2_s10": "命运篇章 第1话「死神との邂逅と甘美な契約」",
    "scene_nier_q3_s10": "命运篇章 第2话「契約の代償（歪んだ救済）」",
    "scene_fate_nier_ep1": "命运篇章 第3话「旅立ち（終焉の先へ）」",
    "scene_nier_flb_ep1": "命运篇章 最终上限解放「生と死の狭間」",
    "scene_nier_flb_ep2": "命运篇章 最终上限解放「死ニ至ル恋」",
    "scene_nier_daily_tea": "舰上日常「甲板とお茶の時間」",
    "scene_nier_battle_vow": "战斗誓言「死神の断罪と守護」",
    "scene_nier_monologue": "角色独白「愛の告白と執着の深淵」",
    "scene_nier_jealousy_deck": "舰上日常「甲板の影法師（嫉妬の疼き）」",
    "scene_nier_jealousy_gift": "舰上日常「贈り物の真意（独占の誓い）」",
    "scene_nier_crew_protect": "舰上日常「夜の巡回（団長室の守護者）」",
    "scene_nier_evoker_lobelia": "命运篇章「相容れぬ狂気（ロベリアとの対峙）」",
    "scene_nier_evoker_fate": "命运篇章「十賢者の宿命（救済の光）」",
    "scene_nier_arcarum_the_world": "命运篇章「世界の裁定者（ザ・ワールドとの対峙）」",
    "scene_nier_domain_awakening": "命运篇章「賢者の領域（愛の深化）」",
    "scene_nier_vow_ring": "特别剧情「久遠の指輪（魂の契り）」",
    "scene_nier_night_deck": "舰上日常「静寂の夜（二人の約束）」",
    "scene_nier_morning_call": "舰上日常「朝の目覚め（朝露と紅茶）」",
}

VARIANT_EPISODE_TITLES = {
    "scene_vajra_halloween_ep": ("特别剧情", "万圣特别剧情", "ヴァジラ 万圣限定篇「夜行百鬼・小悪魔忠犬とお菓子の誓い」 [season:halloween]"),
    "scene_vajra_summer_ep": ("特别剧情", "夏日特别剧情", "ヴァジラ 泳装限定篇「波打ち際のじゃれあいと水飛沫」 [season:summer]"),
    "scene_anila_summer_ep": ("特别剧情", "夏日特别剧情", "アニラ 泳装限定篇「潮風と羊の浮き輪・静かな夏の夜」 [season:summer]"),
    "scene_anila_yukata_ep": ("特别剧情", "夏日祭典特别剧情", "アニラ 浴衣限定篇「宵闇の縁日・林檎飴と花火の約束」 [season:summer]"),
    "scene_andira_summer_ep": ("特别剧情", "夏日特别剧情", "アンチラ 泳装限定篇「真夏の水鉄砲大乱闘とヤシの実」 [season:summer]"),
    "scene_mahira_holiday_ep": ("特别剧情", "圣诞特别剧情", "マキラ 圣诞限定篇「聖夜のからくりトナカイ橇とオルゴール」 [season:christmas]"),
    "scene_mahira_summer_ep": ("特别剧情", "夏日特别剧情", "マキラ 泳装限定篇「全自動砂城マシンと夏の海」 [season:summer]"),
    "scene_kumbhira_summer_ep": ("特别剧情", "夏日特别剧情", "クビラ 泳装限定篇「黄金ビキニとポポのビーチバレー」 [season:summer]"),
    "scene_catura_summer_ep": ("特别剧情", "夏日特别剧情", "シャトラ 泳装限定篇「水陸両用モーちゃん海辺のデート」 [season:summer]"),
    "scene_catura_holiday_ep": ("特别剧情", "圣诞特别剧情", "シャトラ 圣诞限定篇「雪夜のホットミルクと小さな願い」 [season:christmas]"),
    "scene_cindhara_super_ep": ("命运篇章", "十二神将浪漫奇谭", "シンダラ 战斗风格解放篇「スーパーシンダラ合体・猛虎の咆哮」"),
    "scene_cindhara_valentine_ep": ("特别剧情", "情人节特别剧情", "シンダラ 情人节限定篇「双子虎の苺チョコ大合戦」 [season:valentine]"),
    "scene_makora_valentine_ep": ("特别剧情", "情人节特别剧情", "マコラ 情人节限定篇「扇の向こうの紅潮・秘めたる本命チョコ」 [season:valentine]"),
    "scene_haira_summer_ep": ("特别剧情", "夏日特别剧情", "ハイラ 泳装限定篇「パラソルの下の堕落龍と冷たいかき氷」 [season:summer]"),
    "scene_song_yukata_ep": ("特别剧情", "夏日特别剧情", "ソーン 浴衣限定篇「夏夜の縁日・花火と紫陽花の約束」 [season:summer]"),
    "scene_seofon_summer_ep": ("特别剧情", "夏日特别剧情", "シエテ 泳装限定篇「灼熱のビーチボーイと飛剣フィッシング」 [season:summer]"),
    "scene_niyon_yukata_ep": ("特别剧情", "夏日特别剧情", "ニオ 浴衣限定篇「宵闇の微風・二人きりの風鈴」 [season:summer]"),
}

# Seasonal lines expansion data (Years 6-10 for Narmaya, Years 2-5 for Vikala)
NARMAYA_EXTRA_BIRTHDAY = [
    (6, "ナルメア 生日祝贺 第6年 [season:birthday]", [
        ("ナルメア", "団長ちゃん！今年もお誕生日、おめでとう！こうしてまた一緒に団長ちゃんが生まれた日をお祝いできて……お姉ちゃん、本当に胸がいっぱいだよ。", "团长酱！今年也祝你生日快乐！能像这样再次一起庆祝团长酱诞生的日子……姐姐心里真的很欣慰、很感动。"),
        ("ナルメア", "今日は団長ちゃんが主役なんだから、食べたいものも、行きたいところも、お姉ちゃんに甘えたいことも……ぜーんぶ言ってね？", "今天团长酱可是主角哦，想吃什么、想去哪里、想怎么向姐姐撒娇……统统都告诉姐姐好吗？"),
        ("ナルメア", "腕によりをかけて特製ケーキと和菓子を作ったから、まずは一緒に食べよ？お姉ちゃんが一口ずつ食べさせてあげる♪", "我特意拿出看家本领做了特制蛋糕和和果子，先来一起尝尝吧？姐姐一口一口喂你吃哦♪"),
    ]),
    (7, "ナルメア 生日祝贺 第7年 [season:birthday]", [
        ("ナルメア", "団長ちゃん！お誕生日おめでとうっ♪ふふっ、今日は年に一度の特別な日だからね……お姉ちゃんが団長ちゃんの言うこと、なんでも一つだけ聞いてあげる！", "团长酱！生日快乐呀♪呵呵，因为今天是每年仅有一次的特别日子嘛……姐姐今天可以听团长酱的任何一个要求哦！"),
        ("ナルメア", "……えっ、なんでもいいの？って？もちろん！お姉ちゃん、団长ちゃんのお願いなら絶対に断ったりしないよ。", "……咦，‘什么都可以吗’？当然啦！只要是团长酱的愿望，姐姐绝对不会拒绝的。"),
        ("ナルメア", "膝枕で耳かき？それとも……ぎゅーって抱きしめてほしい？ふふっ、遠慮しないで教えてね♪", "要躺在姐姐腿上掏耳朵？还是想要……紧紧地抱抱？呵呵，不用客气尽管告诉姐姐哦♪"),
    ]),
    (8, "ナルメア 生日祝贺 第8年 [season:birthday]", [
        ("ナルメア", "団長ちゃん、お誕生日おめでとう！今日はね、団長ちゃんには船長室でゆーっくり休んでてもらいたいの。", "团长酱，生日快乐！今天呢，姐姐希望团长酱能一直在团长室里好好休息。"),
        ("ナルメア", "騎空団のお仕事から家事洗濯、甲板のお掃除まで、ぜーんぶお姉ちゃんに任せて！", "骑空团的工作、家务洗衣、甲板打扫，统统都交给姐姐吧！"),
        ("ナルメア", "あ……でもね、そうすると夜に添い寝する時まで、団長ちゃんとお話しできなくなっちゃうのかな……？うぅ、やっぱりお仕事中もそばにいていい？", "啊……但是呢，要是这样的话，除了晚上一起睡觉之外，就不能经常和团长酱说话了对不对……？呜呜，果然工作的时候我也陪在你身边好不好？"),
    ]),
    (9, "ナルメア 生日祝贺 第9年 [season:birthday]", [
        ("ナルメア", "団長ちゃん、お誕生日おめでとう。君と出会ってから、たくさんの空を旅して、たくさんの季節を一緒に越えてきたね。", "团长酱，生日快乐。自从与你相遇以来，我们航行过了那么多片空域，一起度过了无数个春夏秋冬。"),
        ("ナルメア", "この手作りの御守り、旅の安全と団長ちゃんの幸せを祈って、一針一針心を込めて縫ったんだ。", "这个手作的护身符，是我为了祈求旅途平安和团长酱的幸福，一针一线倾注心意缝制的。"),
        ("ナルメア", "いつもみんなのために前を走る団長ちゃんが、今日も明日も、ずっと笑顔でいられますように……お姉ちゃんが全力で守るからね。", "希望总是为大家奋勇向前的团长酱，今天、明天，无论何时都能绽放笑容……姐姐一定会拼尽全力守护你的。"),
    ]),
    (10, "ナルメア 生日祝贺 第10年 [season:birthday]", [
        ("ナルメア", "団長ちゃん……お誕生日、本当におめでとう。出会ってからもう十年……あの日、自信がなくて自分の居場所を探していた私を、温かく迎え入れてくれたのは君だった。", "团长酱……生日真的非常快乐。相遇至今已经十年了……那一天，把毫无自信、苦苦寻找自己容身之所的我温柔迎入怀抱的，就是你。"),
        ("ナルメア", "君の『お姉ちゃん』として過ごした日々は、私の人生の何よりもかけがえのない宝物だよ。", "作为你的‘姐姐’度过的每一天，都是我人生中最珍贵无价的宝物。"),
        ("ナルメア", "これからもどんな強敵が立ち塞がろうと、私の胡蝶刃は団長ちゃんのために振るうわ。ずっとずっと……お姉ちゃんを頼りにしてね。", "今后无论遭遇怎样的强敌，我的胡蝶刃都只会为了团长酱而挥舞。要一直一直……依赖姐姐哦。"),
    ]),
]

NARMAYA_EXTRA_VALENTINE = [
    (6, "ナルメア 情人节赠礼 第6年 [season:valentine]", [
        ("ナルメア", "団長ちゃん、ハッピーバレンタイン！ふふっ、今年はお姉ちゃん特製の蝶々形抹茶生チョコレートだよ。", "团长酱，情人节快乐！呵呵，今年姐姐特制了蝴蝶形状的抹茶生巧克力哦。"),
        ("ナルメア", "最高級の宇治抹茶を使って、カカオのほろ苦さと甘みがとろけるように調整したの。はい、あーんして？", "用了最高级的宇治抹茶，精心调配了可可的微苦与甘甜入口即化。来，张开嘴，啊——？"),
    ]),
    (7, "ナルメア 情人节赠礼 第7年 [season:valentine]", [
        ("ナルメア", "ハッピーバレンタイン、団長ちゃん！はい、これ……今年の本命チョコだよ。", "情人节快乐，团长酱！来，给……这是今年的真心本命巧克力哦。"),
        ("ナルメア", "金箔をあしらった三段仕立てのチョコ細工でね、団長ちゃんへの『大好き』の気持ちを全部詰め込んだの。", "缀有点点金箔的三层巧克力工巧，里面装满了对团长酱所有的爱意。"),
    ]),
    (8, "ナルメア 情人节赠礼 第8年 [season:valentine]", [
        ("ナルメア", "団長ちゃん、バレンタインのチョコ、受け取ってくれる？今年はハート形の真ん中に、胡蝶刃の刃先で『いつもありがとう』って彫ってみたの。", "团长酱，今年的情人节巧克力，愿意收下吗？今年在心形正中央，用胡蝶刃刀尖刻下了‘一直以来谢谢你’。"),
        ("ナルメア", "ちょっと照れくさいけれど……私の心はいつも団長ちゃんだけのものだからね。", "虽然有点害羞……但姐姐的心永远都只属于团长酱一个人哦。"),
    ]),
    (9, "ナルメア 情人节赠礼 第9年 [season:valentine]", [
        ("ナルメア", "団長ちゃん、ハッピーバレンタイン！今日はお部屋でチョコレートフォンデュを用意してみたの！", "团长酱，情人节快乐！今天我在房间里准备了巧克力火锅哦！"),
        ("ナルメア", "イチゴや和菓子の求肥にとろーりチョコを絡めて……はい、フーフーしてあげるから食べてみて？", "把草莓和和果子软糖裹上浓浓的融化热巧克力……来，姐姐帮你吹吹，尝一口吧？"),
    ]),
    (10, "ナルメア 情人节赠礼 第10年 [season:valentine]", [
        ("ナルメア", "団長ちゃん……十年目のバレンタインだね。この十年間、毎年君にチョコを渡せて本当に幸せだった。", "团长酱……这是第十年的情人节了呢。这十年来，每年都能把巧克力亲手递给你，我真的感到无比幸福。"),
        ("ナルメア", "言葉にするのは恥ずかしいけれど……世界で一番、団長ちゃんを愛してるよ。", "虽然亲口说出来会很害羞……但在整个世界里，姐姐最爱的人就是团长酱了。"),
    ]),
]

NARMAYA_EXTRA_NEWYEAR = [
    (5, "ナルメア 新年祝词 第5年 [season:newyear]", [
        ("ナルメア", "団長ちゃん、あけましておめでとう！初日の出、甲板から一緒に見られて綺麗だったね。", "团长酱，新年快乐！能一起在甲板上看新年初升的太阳，真的好美呀。"),
        ("ナルメア", "風が冷たいから、お姉ちゃんの羽織りの中に一緒に入ろ？お雑煮を食べて温まろうね。", "晨风很冷，快钻进姐姐的羽织和服里取暖吧？吃过年糕汤一起暖和暖和吧。"),
    ]),
    (6, "ナルメア 新年祝词 第6年 [season:newyear]", [
        ("ナルメア", "新年あけましておめでとう、団長ちゃん！今年のおせち料理はオクトーおじさまやフュンフちゃんも手伝ってくれたよ。", "新年快乐，团长酱！今年的新年御节料理，欧克托叔叔和芬芙酱也来帮忙了哦。"),
        ("ナルメア", "団長ちゃんが今年一年、無病息災でいられるようにお姉ちゃんが心を込めて作ったから、いっぱい食べてね！", "为了祈祷团长酱今年一整年无病无灾，姐姐倾注了全部心意，一定要多吃点哦！"),
    ]),
    (7, "ナルメア 新年祝词 第7年 [season:newyear]", [
        ("ナルメア", "団長ちゃん、あけましておめでとう！今年の初詣のために、団長ちゃんとお揃いの色合いの新しい着物を仕立ててみたの。", "团长酱，新年快乐！为了今年的新年初诣祈愿，我特意裁制了和团长酱色系相配的新和服哦。"),
        ("ナルメア", "似合ってるかな……？ふふっ、今日はお姉ちゃんと一緒に、初詣の屋台巡りに行こっか！", "好看吗……？呵呵，今天就和姐姐一起，去逛初诣的新春小吃摊吧！"),
    ]),
    (8, "ナルメア 新年祝词 第8年 [season:newyear]", [
        ("ナルメア", "謹賀新年、団長ちゃん！今朝はオクトーおじさまと一緒に新年の鏡餅をついたんだよ。", "谨贺新年，团长酱！今早我和欧克托叔叔一起打了新年的镜饼哦。"),
        ("ナルメア", "つきたてのお餅で三色団子とお汁粉を作ったから、冷めないうちに召し上がれ♪", "用刚出锅的热年糕做了三色团子和红豆年糕汤，趁热尝尝吧♪"),
    ]),
    (9, "ナルメア 新年祝词 第9年 [season:newyear]", [
        ("ナルメア", "団長ちゃん、あけましておめでとう。今朝の澄んだ空気の中で、胡蝶刃の手入れをしながら君の武運を祈っていたの。", "团长酱，新年快乐。在今晨清冽纯净的晨光中，我一边细心研磨保养着胡蝶刃，一边为你的武运祈祷。"),
        ("ナルメア", "どんな空の果てに行こうと、お姉ちゃんが君の盾となり矛となって守り抜くからね。", "无论我们要前往怎样的苍穹尽头，姐姐都会成为你的护盾与利刃守护到底。"),
    ]),
    (10, "ナルメア 新年祝词 第10年 [season:newyear]", [
        ("ナルメア", "あけましておめでとう、団長ちゃん！十回目の新年を君と迎えられたこと、神様に感謝しなくちゃね。", "新年快乐，团长酱！能和团长酱迎来第十次新春，真得好好感谢天神呢。"),
        ("ナルメア", "この十年間、いろんなことがあったけれど、団長ちゃんの手の温もりだけはずっと変わらない。ずっとお姉ちゃんのそばにいてね？", "这十年来经历了风风雨雨，但团长酱手心的温度却始终如一。要一直留在姐姐身边哦？"),
    ]),
]

VIKALA_EXTRA_BIRTHDAY = [
    (2, "ビカラ 生日祝贺 第2年 [season:birthday]", [
        ("ビカラ", "団長っち！お誕生日おめでとうーーっ☆ビッキー特製のチーズクラウン参上！今日は団長っちのためのバースデーパーティーだよ！", "团长！祝你生日快乐——☆奇迹维卡特制芝士王冠登场！今天可是专门为了团长举办的生日派对哦！"),
        ("ビカラ", "……あっ、耳、取れちゃった……団長さん、えっと……あの……これ、私が作ったチーズケーキです……受け取ってくれますか……？", "……啊，发箍掉下来了……团长，那个……这是我亲手烤的芝士蛋糕……你能收下吗……？"),
    ]),
    (3, "ビカラ 生日祝贺 第3年 [season:birthday]", [
        ("ビカラ", "団長っち、ハッピーバースデー！今年のビッキーパレードは団長っちの生まれた日を祝う特別仕様だよ！ドーシェも風船をいっぱいくっつけて準備万端！", "团长，生日快乐！今年的奇迹维卡大巡游是专门为了庆祝团长诞生日的特别版哦！多尔切也系满了彩色气球准备就绪！"),
        ("ビカラ", "……えへへ、耳を外した私も、団長さんの笑顔が一番大好きです。生まれてきてくれて、本当にありがとう……！", "……嘿嘿，摘下鼠耳的我，也最喜欢团长的笑容了。你能诞生在这个世界上，真的太谢谢你了……！"),
    ]),
    (4, "ビカラ 生日祝贺 第4年 [season:birthday]", [
        ("ビカラ", "団長っち！お誕生日おめでとーっ！今年のプレゼントはね、ビッキーが団長っちのためだけに作詞したハッピーバースデーソングだよ！", "团长！生日快乐——！今年的生日礼物呢，是奇迹维卡专门为团长一个人谱写的生日特别应援曲哦！"),
        ("ビカラ", "……歌い終わったら、耳を外してぎゅーってさせてね？団長さんの優しいにおい、私の一番安心する居場所なんだもん。", "……唱完之后，能让我摘下鼠耳扑进你怀里抱抱吗？团长身上温柔的气味，是我觉得最安心的避风港呢。"),
    ]),
    (5, "ビカラ 生日祝贺 第5年 [season:birthday]", [
        ("ビカラ", "団長っち、五回目のお誕生日おめでとう！思えばジョヤの事件から五年……あの時、自信がなくて泣き虫だった私を救ってくれたのは団長っちだったよ。", "团长，第五个生日快乐！回想起来从除夜之钟事件开始已经五年了……那时候，拯救了毫无自信、哭哭啼啼的我的，就是团长你。"),
        ("ビカラ", "耳をつけてる派手なビッキーも、隅っこで震えてるみすぼらしい私も、どっちも大好きだよって言ってくれたこと……一生忘れません。団長さん、大好き……！", "你说不管是戴着鼠耳耀眼的奇迹维卡，还是缩在角落发抖难看的我，两种人格你都一样深爱……这番话我一生都不会忘记。团长，我最喜欢你了……！"),
    ]),
]

VIKALA_EXTRA_VALENTINE = [
    (2, "ビカラ 情人节赠礼 第2年 [season:valentine]", [
        ("ビカラ", "団長っち！ハッピーバレンタイン！ビッキーの愛がギューッと詰まった特製チーズトリュフだよ！", "团长！情人节快乐！这是浓缩了奇迹维卡满满爱意的特制芝士松露巧克力哦！"),
        ("ビカラ", "……はっ、耳外さなきゃ……団長さん、部屋に来ちゃってごめんなさい……あの、これ、本命チョコです……団長さん以外の人には絶対に渡したくない、私の本当の気持ちです……！", "……呀，得把鼠耳摘下来……团长，特意跑到你的房间来对不起……那个，这是本命巧克力……除了团长以外的人我绝对不会送给任何人，这是我的真实心意……！"),
    ]),
    (3, "ビカラ 情人节赠礼 第3年 [season:valentine]", [
        ("ビカラ", "ハッピーバレンタイン、団長っち！今年のドーシェはパティシエ帽をかぶってお手伝いしてくれたんだよ！はい、チーズクリーム入りのフォンダンショコラ！", "情人节快乐，团长！今年的多尔切可是戴着糕点师小帽子一起帮忙的哦！来，这是包裹着浓郁芝士奶油的熔岩热巧克力！"),
        ("ビカラ", "……温かいうちに食べてね。団長さんの口元についたチョコ、私が拭いてあげても……いいですか？", "……趁热快吃吧。团长嘴角沾到的巧克力沫，由我来帮你擦掉……可以吗？"),
    ]),
    (4, "ビカラ 情人节赠礼 第4年 [season:valentine]", [
        ("ビカラ", "団長っち！バレンタインサプライズ☆このプレゼント箱、開けるとビッキー印のチョコ風船が飛び出す仕掛けなんだよ！", "团长！情人节大惊喜☆这个礼物盒打开的话，会飞出奇迹维卡特质的巧克力爱心气球哦！"),
        ("ビカラ", "……でも箱の底にはね、耳を外した私が書いた団長さんへのお手紙が入ってるの。後でふたりきりの時に読んでね……！", "……不过在盒子最底下，藏着摘下鼠耳的我写给团长的心意信。等之后只有我们两个人的时候再悄悄读好吗……！"),
    ]),
    (5, "ビカラ 情人节赠礼 第5年 [season:valentine]", [
        ("ビカラ", "団長さん……今日はバレンタインですね。北北東の神社から団長さんの船に乗って五年、私の心の中はいつも団長さんでいっぱいでした。", "团长……今天是情人节呢。从北北东神社登上团长的船已经五年了，我的心里无时无刻不被团长填满。"),
        ("ビカラ", "耳をつけて歌う自信をくれたのも、素顔の私を受け止めてくれたのも団長さんです。この手作りチョコと一緒に、私の全部を団長さんに捧げます……ずっとそばにいさせてください。", "给予我戴上鼠耳歌唱的自信、又毫无保留接纳素颜真实自我的，只有团长你。连同这份手作巧克力一起，我把我的全部都托付给团长……请让我一直留在你身边。"),
    ]),
]


def clean_text(s: str) -> str:
    # Remove HTML tags like <span ...>, <br>, etc.
    s = re.sub(r"<[^>]+>", "", s)
    return s.strip()


def compute_vector(text: str, dim: int = 1536) -> bytes:
    """Generate a deterministic normalized vector for text based on character 1-gram, 2-grams, and 3-grams."""
    import hashlib
    import math
    import struct

    vec = [0.0] * dim
    for ch in text:
        h = int(hashlib.md5(ch.encode("utf-8")).hexdigest()[:8], 16) % dim
        vec[h] += 1.0
    for i in range(len(text) - 1):
        bi = text[i:i+2]
        h = int(hashlib.md5(bi.encode("utf-8")).hexdigest()[:8], 16) % dim
        vec[h] += 2.0
    for i in range(len(text) - 2):
        tri = text[i:i+3]
        h = int(hashlib.md5(tri.encode("utf-8")).hexdigest()[:8], 16) % dim
        vec[h] += 3.0
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    vec = [x / norm for x in vec]
    return struct.pack(f"<{dim}f", *vec)


def main():
    print("=== 开始全量导入 GBF 史实剧情、活动、节日对话与检索索引 ===")
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    db = connect(DB_PATH)
    with db:
        db.executescript(_SCHEMA)
        # Drop and recreate FTS5 virtual tables with trigram tokenizer for CJK / BM25
        db.execute("DROP TABLE IF EXISTS episode_fts;")
        db.execute("DROP TABLE IF EXISTS world_fts;")
        db.execute("""
            CREATE VIRTUAL TABLE episode_fts USING fts5(
                episode_id UNINDEXED,
                character_id UNINDEXED,
                title,
                text,
                tokenize = 'trigram'
            );
        """)
        db.execute("""
            CREATE VIRTUAL TABLE world_fts USING fts5(
                kind UNINDEXED,
                title,
                text,
                tokenize = 'trigram'
            );
        """)

    chars = load_characters(CHARS_FILE)
    sp_idx = _speaker_index(chars.values())
    report = ImportReport()

    # Clear old data to rebuild cleanly
    with db:
        db.execute("DELETE FROM episodes")
        db.execute("DELETE FROM episode_cast")
        db.execute("DELETE FROM episode_lines")
        db.execute("DELETE FROM episode_passages")
        db.execute("DELETE FROM episode_fts")
        db.execute("DELETE FROM world_fts")

    total_episodes = 0
    total_lines = 0
    total_passages = 0

    # 1. Ingest all CSV files in corpus/gbf
    all_csvs = sorted(CORPUS_DIR.glob("**/*.csv"))
    print(f"扫描到剧本 CSV 文件总数: {len(all_csvs)}")

    for path in all_csvs:
        rel = path.relative_to(CORPUS_DIR)
        parent_dir = rel.parent.name
        source_id, lines = _read_csv(path)
        if source_id is None:
            source_id = f"csv/{rel.with_suffix('').as_posix()}"

        # Clean line HTML
        cleaned_lines = []
        for l in lines:
            ja_clean = clean_text(l.ja)
            zh_clean = clean_text(l.zh) if l.zh else None
            sp_clean = clean_text(l.speaker) if l.speaker else None
            if ja_clean:
                cleaned_lines.append(Line(sp_clean, ja_clean, zh_clean))

        if not cleaned_lines:
            continue

        # Determine category, source, title, cast
        cast = set(_cast(cleaned_lines, sp_idx))
        is_joya = "除夜の終わりに響く鐘" in str(rel)
        is_seasonal = "scene_s" in rel.stem

        char_prefix = None
        for cid in chars.keys():
            if cid in str(rel):
                char_prefix = cid
                break
        if not char_prefix:
            char_prefix = "narmaya"

        char_name = chars[char_prefix].name if char_prefix in chars else char_prefix

        if is_joya:
            category = "活动剧情"
            source = "除夜の終わりに響く鐘"
            # Extract chapter and scene title
            title = f"《除夜の終わりに響く鐘》{rel.stem}"
            # Ensure vikala is in cast for all 26 chapters
            cast.add("vikala")
        elif is_seasonal:
            category = "特别剧情"
            if "birthday" in rel.stem:
                source = "节日特别剧情 / 生日"
                num = re.search(r"scene_s(\d+)_birthday", rel.stem)
                year_n = num.group(1) if num else "1"
                title = f"{char_name} 生日祝贺 第{year_n}年 [season:birthday]"
            elif "valentine" in rel.stem:
                source = "节日特别剧情 / 情人节"
                num = re.search(r"scene_s(\d+)_valentine", rel.stem)
                year_n = num.group(1) if num else "1"
                title = f"{char_name} 情人节赠礼 第{year_n}年 [season:valentine]"
            elif "newyear" in rel.stem:
                source = "节日特别剧情 / 新春除夜"
                num = re.search(r"scene_s(\d+)_newyear", rel.stem)
                year_n = num.group(1) if num else "1"
                title = f"{char_name} 新年祝词 第{year_n}年 [season:newyear]"
            elif "white" in rel.stem:
                source = "节日特别剧情 / 白色情人节"
                num = re.search(r"scene_s(\d+)_white", rel.stem)
                year_n = num.group(1) if num else "1"
                title = f"{char_name} 白色情人节回礼 第{year_n}年 [season:whiteday]"
            elif "halloween" in rel.stem:
                source = "节日特别剧情 / 万圣节"
                num = re.search(r"scene_s(\d+)_halloween", rel.stem)
                year_n = num.group(1) if num else "1"
                title = f"{char_name} 万圣节特别对话 第{year_n}年 [season:halloween]"
            elif "christmas" in rel.stem:
                source = "节日特别剧情 / 圣诞节"
                num = re.search(r"scene_s(\d+)_christmas", rel.stem)
                year_n = num.group(1) if num else "1"
                title = f"{char_name} 圣诞特别对话 第{year_n}年 [season:christmas]"
            else:
                source = "节日特别剧情"
                title = rel.stem
            cast.add(char_prefix)
        elif "zodiacs" in rel.stem or "twelve_generals" in str(rel):
            category = "特别剧情"
            source = "十二神将同盟"
            if "deck_festival" in rel.stem:
                title = "十二神将新春演艺大会「甲板除夕大祝宴」"
            elif "onsen_vacation" in rel.stem:
                title = "十二神将初诣温泉旅行「湯けむり大騒動と星空の誓い」"
            else:
                title = f"十二神将集结特别篇「{rel.stem}」"
            ALL_ZODIACS = ["vikala", "anila", "andira", "mahira", "vajra", "kumbhira", "catura", "cindhara", "makora", "haira", "indara", "sanchira"]
            for zid in ALL_ZODIACS:
                cast.add(zid)
        elif "eternals" in rel.stem or "eternals" in str(rel):
            category = "特别剧情"
            source = "十天衆同盟"
            if "grand_tournament" in rel.stem:
                title = "十天衆巅峰演武「全空最強の模擬戦」"
            elif "deck_banquet" in rel.stem:
                title = "十天衆甲板大祝宴「星空の下の誓杯」"
            else:
                title = f"十天衆特别篇「{rel.stem}」"
            ALL_ETERNALS = ["uno", "song", "sarasa", "quatre", "funf", "seox", "seofon", "eahta", "niyon", "tien"]
            for eid in ALL_ETERNALS:
                cast.add(eid)
        elif VARIANT_EPISODE_TITLES.get(rel.stem):
            category, source, title = VARIANT_EPISODE_TITLES[rel.stem]
            cast.add(char_prefix)
        elif NIER_EPISODE_TITLES.get(rel.stem):
            title = NIER_EPISODE_TITLES[rel.stem]
            if "特别剧情" in title or "舰上日常" in title or "战斗誓言" in title or "角色独白" in title:
                category = "特别剧情"
                source = "舰上日常与羁绊"
            else:
                category = "命运篇章"
                source = "暗-妮亚"
            cast.add(char_prefix)
        elif "daily" in rel.stem or "battle" in rel.stem:
            category = "特别剧情"
            source = "舰上日常与羁绊"
            if "daily" in rel.stem:
                title = f"{char_name} 舰上日常「青空と甲板のひととき」"
            else:
                title = f"{char_name} 战斗誓言「十天の誓いと出陣」"
            cast.add(char_prefix)
        elif rel.stem.startswith("scene_") and ("_q" in rel.stem or "_fate_" in rel.stem or "_flb_" in rel.stem or "_transcendence_" in rel.stem):
            category = "命运篇章"
            source = f"{char_name} 命运篇章"
            if "_transcendence_" in rel.stem:
                title = f"{char_name} 命运篇章 限界超越「苍穹の極致」"
            elif "_flb_" in rel.stem:
                title = f"{char_name} 命运篇章 最终上限解放「真・天星覚醒」"
            elif "_fate_" in rel.stem:
                title = f"{char_name} 命运篇章 招募入团「大空への旅立ち」"
            elif "_q1_" in rel.stem:
                title = f"{char_name} 命运篇章 前篇「天星器の導きと風」"
            elif "_q2_" in rel.stem:
                title = f"{char_name} 命运篇章 第1话「強者への問いかけ」"
            elif "_q3_" in rel.stem:
                title = f"{char_name} 命运篇章 第2话「団長との絆」"
            else:
                title = f"{char_name} 命运篇章「{rel.stem}」"
            cast.add(char_prefix)
        else:
            category = "命运篇章"
            source = parent_dir
            title = rel.stem
            if not cast:
                cast.add(char_prefix)

        total_episodes += 1
        total_lines += len(cleaned_lines)

        ep = Episode(source_id, category, source, title, frozenset(cast), tuple(cleaned_lines), "csv")

        # Save to database
        with db:
            db.execute(
                """INSERT OR REPLACE INTO episodes (id, category, source, title, imported_from, imported_at)
                   VALUES (?, ?, ?, ?, 'csv', datetime('now'))""",
                (ep.id, ep.category, ep.source, ep.title),
            )
            db.execute("DELETE FROM episode_cast WHERE episode_id = ?", (ep.id,))
            for cid in ep.cast:
                db.execute("INSERT INTO episode_cast (episode_id, character_id) VALUES (?, ?)", (ep.id, cid))
            db.execute("DELETE FROM episode_lines WHERE episode_id = ?", (ep.id,))
            for seq, l in enumerate(ep.lines):
                db.execute(
                    "INSERT INTO episode_lines (episode_id, seq, speaker, ja, zh) VALUES (?, ?, ?, ?, ?)",
                    (ep.id, seq, l.speaker, l.ja, l.zh),
                )

            # Generate passages
            passages = _passages(ep)
            db.execute("DELETE FROM episode_passages WHERE episode_id = ?", (ep.id,))
            for p_seq, p_text in enumerate(passages):
                total_passages += 1
                vec_blob = compute_vector(p_text)
                db.execute(
                    "INSERT INTO episode_passages (episode_id, seq, text, model, embedding) VALUES (?, ?, ?, ?, ?)",
                    (ep.id, p_seq, p_text, "builtin-bm25-vector", vec_blob),
                )
                for cid in ep.cast:
                    db.execute(
                        "INSERT INTO episode_fts (episode_id, character_id, title, text) VALUES (?, ?, ?, ?)",
                        (ep.id, cid, ep.title, p_text),
                    )

    # 2. Ingest extra seasonal cutscenes (Years 6-10 for Narmaya, Years 2-5 for Vikala)
    extra_sets = [
        ("narmaya", "特别剧情", "节日特别剧情 / 生日", NARMAYA_EXTRA_BIRTHDAY),
        ("narmaya", "特别剧情", "节日特别剧情 / 情人节", NARMAYA_EXTRA_VALENTINE),
        ("narmaya", "特别剧情", "节日特别剧情 / 新春除夜", NARMAYA_EXTRA_NEWYEAR),
        ("vikala", "特别剧情", "节日特别剧情 / 生日", VIKALA_EXTRA_BIRTHDAY),
        ("vikala", "特别剧情", "节日特别剧情 / 情人节", VIKALA_EXTRA_VALENTINE),
    ]

    for char_id, cat, src, items in extra_sets:
        for year, ep_title, dialog_lines in items:
            source_id = f"custom_seasonal/{char_id}/{src.split('/')[-1].strip()}_y{year}"
            lines = [Line(sp, ja, zh) for sp, ja, zh in dialog_lines]
            cast = frozenset([char_id])
            ep = Episode(source_id, cat, src, ep_title, cast, tuple(lines), "json")

            total_episodes += 1
            total_lines += len(lines)

            with db:
                db.execute(
                    """INSERT OR REPLACE INTO episodes (id, category, source, title, imported_from, imported_at)
                       VALUES (?, ?, ?, ?, 'json', datetime('now'))""",
                    (ep.id, ep.category, ep.source, ep.title),
                )
                db.execute("DELETE FROM episode_cast WHERE episode_id = ?", (ep.id,))
                db.execute("INSERT INTO episode_cast (episode_id, character_id) VALUES (?, ?)", (ep.id, char_id))
                db.execute("DELETE FROM episode_lines WHERE episode_id = ?", (ep.id,))
                for seq, l in enumerate(ep.lines):
                    db.execute(
                        "INSERT INTO episode_lines (episode_id, seq, speaker, ja, zh) VALUES (?, ?, ?, ?, ?)",
                        (ep.id, seq, l.speaker, l.ja, l.zh),
                    )

                passages = _passages(ep)
                db.execute("DELETE FROM episode_passages WHERE episode_id = ?", (ep.id,))
                for p_seq, p_text in enumerate(passages):
                    total_passages += 1
                    vec_blob = compute_vector(p_text)
                    db.execute(
                        "INSERT INTO episode_passages (episode_id, seq, text, model, embedding) VALUES (?, ?, ?, ?, ?)",
                        (ep.id, p_seq, p_text, "builtin-bm25-vector", vec_blob),
                    )
                    db.execute(
                        "INSERT INTO episode_fts (episode_id, character_id, title, text) VALUES (?, ?, ?, ?)",
                        (ep.id, char_id, ep.title, p_text),
                    )

    # 3. Ingest World setting facts into world_fts for fast BM25 retrieval
    world = load_world(WORLD_FILE)
    if world:
        entries = world.entries()
        print(f"正在建立世界设定索引（歌曲/唱片/演出）: {len(entries)} 条")
        with db:
            for e in entries:
                db.execute("INSERT INTO world_fts (kind, title, text) VALUES (?, ?, ?)", (e.kind, e.title, e.text))

    print(f"\n=== 全量数据导入成功！ ===")
    print(f"总剧情段落数 (Episodes): {total_episodes}")
    print(f"总台词句数 (Lines): {total_lines}")
    print(f"总切片段落数 (Passages): {total_passages}")

    # Summary by character
    for cid in chars:
        cur = db.execute("SELECT COUNT(DISTINCT episode_id) FROM episode_cast WHERE character_id = ?", (cid,))
        ep_c = cur.fetchone()[0]
        cur2 = db.execute(
            "SELECT COUNT(*) FROM episode_passages p JOIN episode_cast c ON c.episode_id = p.episode_id WHERE c.character_id = ?",
            (cid,)
        )
        pas_c = cur2.fetchone()[0]
        print(f"  - 角色 [{chars[cid].name}] ({cid}): 可回想剧情 {ep_c} 段, 索引切片 {pas_c} 条")

    # Categories breakdown
    cur = db.execute("SELECT category, COUNT(*) FROM episodes GROUP BY category")
    print("\n剧情分类统计:")
    for cat, count in cur.fetchall():
        print(f"  - {cat}: {count} 段")

    # SQLite WAL Checkpoint discipline
    db.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    print("WAL checkpoint TRUNCATE completed successfully.")


if __name__ == "__main__":
    main()
