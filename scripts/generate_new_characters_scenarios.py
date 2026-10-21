"""Generate canonical scenario cutscenes for Four Saints, Six Dragons, and Primal Beasts."""

import csv
import sys
from pathlib import Path

# Fix Windows stdout encoding
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

BASE_DIR = Path("corpus/gbf")

CHAR_PROFILES = {
    # 四圣
    "chichiri": {
        "name": "チチリ",
        "power": "朱雀の炎",
        "weapon": "朱雀の刀杖",
        "origin": "南天朱雀神殿",
        "food": "和菓子と果実茶",
        "val_gift": "手作りの朱雀羽クッキー",
        "white_gift": "南国の花茶セット",
        "dancho": "団長",
        "tone": "羞怯纯真",
    },
    "uruki": {
        "name": "ウルキ",
        "power": "玄武の絶対零度",
        "weapon": "玄武の氷斧",
        "origin": "北天玄武神殿",
        "food": "熱いココアと古書",
        "val_gift": "氷晶を模したホワイトチョコ",
        "white_gift": "温かい手編みのマフラー",
        "dancho": "団長",
        "tone": "冷清理智三无",
    },
    "shushuku": {
        "name": "シュシュク",
        "power": "白虎の金剛力",
        "weapon": "白虎の神鋼拳",
        "origin": "西天白虎神殿",
        "food": "山盛りの大肉と肉まん",
        "val_gift": "巨大な虎形チョコロール",
        "white_gift": "特大骨付きローストビーフ",
        "dancho": "団長",
        "tone": "豪爽元气野性",
    },
    "ami": {
        "name": "アミ",
        "power": "青竜の狂嵐と迅雷",
        "weapon": "青竜の魔導銃",
        "origin": "東天青竜神殿",
        "food": "高級花茶と蜂蜜ドリンク",
        "val_gift": "気品ある青竜トリュフチョコ",
        "white_gift": "翡翠のしおりと茶葉",
        "dancho": "団長さん",
        "tone": "端庄优雅知性",
    },
    # 六龙
    "wilnas": {
        "name": "ウィルナス",
        "power": "朱の生命炎",
        "weapon": "爆砕の拳",
        "origin": "火の六竜神域",
        "food": "直火焼き特大ステーキ",
        "val_gift": "激辛ハバネロチョコケーキ",
        "white_gift": "豪快な骨付き肉盛り合わせ",
        "dancho": "契約者",
        "tone": "豪快磊落热血",
    },
    "wamdus": {
        "name": "ワムデュス",
        "power": "碧の深海渦流",
        "weapon": "碧竜の水母神槍",
        "origin": "水の六竜神域",
        "food": "冷たいアイスと甘いお菓子",
        "val_gift": "クラゲ形のぷるぷるチョコ",
        "white_gift": "高級特大パフェ",
        "dancho": "だんちょー",
        "tone": "软萌贪吃撒娇",
    },
    "galleon": {
        "name": "ガレヲン",
        "power": "金の大地重力",
        "weapon": "大地核晶の黄金杖",
        "origin": "土の六竜神域",
        "food": "大地の恵みの和菓子と銘茶",
        "val_gift": "金粉を散らした金剛チョコ",
        "white_gift": "手作りの陶器と茶器",
        "dancho": "我が子（団長）",
        "tone": "慈爱博大母性",
    },
    "ewiyar": {
        "name": "イーウィヤ",
        "power": "翠の超音速狂嵐",
        "weapon": "翠玉の風杖",
        "origin": "風の六竜神域",
        "food": "極上プリンと小魚",
        "val_gift": "高級キャットニップ風チョコ",
        "white_gift": "最高級の金缶詰とふかふかクッション",
        "dancho": "下僕（団長）",
        "tone": "傲娇猫咪神明",
    },
    "luwoh": {
        "name": "ル・オー",
        "power": "白の秩序聖雷",
        "weapon": "秩序の神聖拳套",
        "origin": "光の六竜神域",
        "food": "整然と淹れられたハーブティー",
        "val_gift": "幾何学的に完璧なホワイトチョコ",
        "white_gift": "秩序ある日課手帳と万年筆",
        "dancho": "契約者（団長）",
        "tone": "严谨克制圣职",
    },
    "fediel": {
        "name": "フェディエル",
        "power": "黒の冥府死炎",
        "weapon": "幽冥の格闘爪",
        "origin": "闇の六竜神域",
        "food": "濃厚な赤ワインと熟成肉",
        "val_gift": "生殖と繁栄を祈るビターチョコ",
        "white_gift": "情熱的な薔薇の花束",
        "dancho": "お前（団长）",
        "tone": "妖娆放荡御姐",
    },
    # 星晶兽/眷属
    "yggdrasil": {
        "name": "ユグドラシル",
        "power": "創樹の大地生機",
        "weapon": "霊木の大枝",
        "origin": "ルーマシー群島",
        "food": "清らかな湧き水と朝露",
        "val_gift": "木の実と蜂蜜の森チョコ",
        "white_gift": "色鮮やかな花の種と小さなスコップ",
        "dancho": "団長さん",
        "tone": "纯真灵巧心音",
    },
    "europa": {
        "name": "エウロペ",
        "power": "聖泉の清浄奔流",
        "weapon": "聖泉の金杖と霊弓",
        "origin": "水天司ガブリエルの神域",
        "food": "百合の香る高級紅茶",
        "val_gift": "聖水仕立てのフォンダンショコラ",
        "white_gift": "清らかなクリスタルグラス",
        "dancho": "団長様",
        "tone": "高雅圣洁端庄",
    },
    "brodia": {
        "name": "ブローディア",
        "power": "不壊の刃鏡金剛盾",
        "weapon": "神立の刃（六柄の刃鏡）",
        "origin": "土天司ウリエルの神域",
        "food": "兵糧丸と温かい白湯",
        "val_gift": "刀剣の鍔を模した硬派なチョコ",
        "white_gift": "上質な砥石と手入れ布",
        "dancho": "汝（団長）",
        "tone": "刚毅木讷武人",
    },
    "grimnir": {
        "name": "グリームニル",
        "power": "神聖なる狂風嵐撃",
        "weapon": "狂風神槍と魔導杖",
        "origin": "風天司ラファエルの神域",
        "food": "深煎りブラックコーヒーと激辛料理",
        "val_gift": "漆黒の薔薇を模した魔界風チョコ",
        "white_gift": "超かっこいい革製音楽CDケース",
        "dancho": "我が盟友（団長）",
        "tone": "帅气中二纯情",
    },
}

def generate_scenes_for_character(cid: str, p: dict):
    cdir = BASE_DIR / cid
    cdir.mkdir(parents=True, exist_ok=True)
    name = p["name"]
    d_call = p["dancho"]

    # 1. 邂逅前篇 scene_{cid}_q1_s10
    (cdir / f"scene_{cid}_q1_s10.csv").write_text(f"""id,name,text,trans
1,{name},この地に満ちる気配……全空を揺るがす特異点の光か。,弥漫在此处的气息……正是撼动全空的特异点之光芒吗。
2,団長,君は……？,你是……？
3,{name},私は{name}。{p['origin']}より、汝の魂の器を見定めるために来た。,我乃{name}。自{p['origin']}而来，只为见证汝之灵魂器量。
4,{name},さあ、汝の覚悟と力……この{p['power']}をもって確かめさせてもらおう！,来吧，汝之觉悟与力量……就由这{p['power']}来亲自试炼！
info,,,scene_{cid}_q1_s10
""", encoding="utf-8")

    # 2. 试炼第1话 scene_{cid}_q2_s10
    (cdir / f"scene_{cid}_q2_s10.csv").write_text(f"""id,name,text,trans
1,{name},なるほど……仲間との絆を力に変え、幾多の苦難を越えてきたのだな。,原来如此……将同伴间的羁绊化作力量，跨越了无数艰难险阻啊。
2,団長,一人じゃここまで来られなかった。みんながいるから前を向けるんだ。,凭我一个人是走不到这里的。正因为有大家在，才能勇往直前。
3,{name},ふふ、迷いなきその瞳、実に心地よい。だが真の試練はここからだ！,呵呵，毫无迷惘的双眸，着实令人神清气爽。然而真正的试炼才正要开始！
4,{name},我が全力の一撃、受けてみせるがいい！,接下我这全力的真正一击吧！
info,,,scene_{cid}_q2_s10
""", encoding="utf-8")

    # 3. 试炼第2话 scene_{cid}_q3_s10
    (cdir / f"scene_{cid}_q3_s10.csv").write_text(f"""id,name,text,trans
1,{name},見事だ、{d_call}！まさか我が{p['weapon']}の猛攻を真っ向から凌ぎ切るとはな！,漂亮，{d_call}！真没想到你竟能正面化解我这{p['weapon']}的狂暴攻势！
2,団長,君の全力を受け止められて光栄だよ。,能接下你的全力，感到由衷的荣幸。
3,{name},ははっ、素晴らしい器だ！汝のような騎空士と共に翔ける未来……実に興味深い。,哈哈，何等惊人的器量！与你这样的骑空士并肩翱翔的未来……着实令人期待。
4,{name},我が力、汝のグランサイファーの航路に捧げよう。共に空の果てを目指そうぞ！,我的力量，愿全部奉献给你的格兰赛法号航程。一同向着长空的尽头进发吧！
info,,,scene_{cid}_q3_s10
""", encoding="utf-8")

    # 4. 招募入团 scene_fate_{cid}_ep1
    (cdir / f"scene_fate_{cid}_ep1.csv").write_text(f"""id,name,text,trans
1,ルリア,{name}さん、グランサイファーへようこそ！これからよろしくお願いします！,{name}，欢迎登上格兰赛法号！今后请多多关照！
2,ビィ,へへっ！こんな頼もしい仲間が増えるなんて、オイラたちの騎空団も無敵だな！,嘿嘿！能迎来这么靠谱的同伴，咱们骑空团可真要天下无敌啦！
3,{name},歓迎感謝する。この船に満ちる温もり……確かに居心地が良い。,多谢诸位的盛情款待。这艘船上充盈的暖意……确实令人感到无比舒心。
4,{name},{d_call}、改めてよろしく頼む。我が背中、汝に預けよう。,重新向你致意，{d_call}。我的后背，就托付给你了。
info,,,scene_fate_{cid}_ep1
""", encoding="utf-8")

    # 5. 终突觉醒 scene_{cid}_flb_ep1
    (cdir / f"scene_{cid}_flb_ep1.csv").write_text(f"""id,name,text,trans
1,{name},{p['power']}の真なる深淵が、今ここに覚醒した……！魂がどこまでも研ぎ澄まされていく。,这{p['power']}的真正深渊，终于在此时此刻彻底觉醒了……！能清晰感受到灵魂被无限升华。
2,団長,すごい気迫だ……おめでとう、{name}！,好惊人的昂扬气魄……恭喜你，{name}！
3,{name},汝が信じて寄り添ってくれたからこそ、私は限界を超越できたのだ。,正因为有你的坚信与一路相伴，我才能超越自我极限。
4,{name},この新たな力、すべて汝の道を切り拓くために振るおう。さあ、更なる高みへ！,这份新生的伟力，将全部为了开拓你的道路而挥舞。来吧，向着更高的顶点！
info,,,scene_{cid}_flb_ep1
""", encoding="utf-8")

    # 6. 战斗誓言 scene_{cid}_battle_vow
    (cdir / f"scene_{cid}_battle_vow.csv").write_text(f"""id,name,text,trans
1,{name},{d_call}、戦況は厳しいが……決して退くことはない。,战况虽然严峻，{d_call}……但我决不会后退半步。
2,団長,頼むよ、{name}！一緒に突破口を開こう！,拜托你了，{name}！一起撕开突破口吧！
3,{name},応！我が{p['power']}の神威を刻み込め！汝の命、私が絶対に守り抜く！,好！将我这{p['power']}的神威深深烙印在敌人身上吧！你的安危，由我誓死守护到底！
info,,,scene_{cid}_battle_vow
""", encoding="utf-8")

    # 7. 甲板日常 scene_{cid}_daily_deck
    (cdir / f"scene_{cid}_daily_deck.csv").write_text(f"""id,name,text,trans
1,{name},ふう……良い風が吹いているな。こうして甲板で空を眺めるのも、悪くない。,呼……吹着舒服的好风呢。像这样在甲板上眺望青空，倒也别有一番情趣。
2,団長,いつも警備ありがとう。少し休んでいく？,一直以来辛苦你警戒了。要不要稍微歇歇？
3,{name},ふふ、{d_call}の淹れてくれた{p['food']}を味わいながらなら、喜んで付き合おう。,呵呵，若是能一边品尝{d_call}端来的{p['food']}，我自然十分乐意奉陪。
info,,,scene_{cid}_daily_deck
""", encoding="utf-8")

    # 8. 领域觉醒 scene_{cid}_awakening_ep
    (cdir / f"scene_{cid}_awakening_ep.csv").write_text(f"""id,name,text,trans
1,{name},{d_call}……汝と共に歩んできた日々が、私に新たな感情を教えてくれた。,与你携手走过的每一天，{d_call}……教会了我前所未有的心念与温度。
2,団長,それは僕（私）も同じだよ。出会えて本当によかった。,对我来说也是一样的。能与你相遇真是太好了。
3,{name},この絆こそが私の真の力。世界が如何に変貌しようと、私は永遠に汝の味方だ。,这份羁绊正是我真正的力量源泉。无论这片世界如何沧海桑田，我都永远与你同在。
info,,,scene_{cid}_awakening_ep
""", encoding="utf-8")

    # 9. 生日祝福 Y1 scene_{cid}_s1_birthday
    (cdir / f"scene_{cid}_s1_birthday.csv").write_text(f"""id,name,text,trans
1,{name},{d_call}、誕生日おめでとう！汝が生まれたこの佳き日を、共に祝えて光栄だ。,祝你生日快乐，{d_call}！能在今天这个美好的日子与你一同庆祝，感到万分荣幸。
2,団長,ありがとう、{name}！,谢谢你，{name}！
3,{name},ささやかだが祝福の品を用意した。汝のこれからの航路に、幸多からんことを！,准备了一点微薄的贺礼。愿你在未来的浩瀚航程中福泽绵长、一路坦途！
info,,,scene_{cid}_s1_birthday
""", encoding="utf-8")

    # 10. 生日祝福 Y2 scene_{cid}_s2_birthday
    (cdir / f"scene_{cid}_s2_birthday.csv").write_text(f"""id,name,text,trans
1,{name},またこの特別な日を迎えることができたな。{d_call}、誕生日おめでとう！,又迎来了这特别的一年呢。生日快乐，{d_call}！
2,団長,今年も一緒に祝ってくれて嬉しいよ。,今年也能一起庆祝，真的很开心。
3,{name},ふふ、来年も再来年も、汝の隣で祝わせてもらうぞ。我が最高の盟友よ。,呵呵，无论是明年还是后年，我都会在你身旁为你祝贺的。我至高无上的同伴啊。
info,,,scene_{cid}_s2_birthday
""", encoding="utf-8")

    # 11. 情人节赠礼 Y1 scene_{cid}_s1_valentine
    (cdir / f"scene_{cid}_s1_valentine.csv").write_text(f"""id,name,text,trans
1,{name},{d_call}……受け取ってくれるか？日頃の感謝を込めて、用意したチョコレートだ。,能收下这个吗，{d_call}……？这是蕴含了我平日所有感激心意特制的情人节巧克力。
2,団長,すごく美味しそうだね！ありがとう！,看起来超级美味！谢谢你！
3,{name},喜んでもらえて何よりだ。汝の口に合えば良いのだが……少し照れくさいな。,能让你感到高兴比什么都好。合你的口味便再好不过了……还真有点不好意思呢。
info,,,scene_{cid}_s1_valentine
""", encoding="utf-8")

    # 12. 情人节赠礼 Y2 scene_{cid}_s2_valentine
    (cdir / f"scene_{cid}_s2_valentine.csv").write_text(f"""id,name,text,trans
1,{name},ハッピーバレンタイン、{d_call}。今年はこの特製『{p['val_gift']}』を作ってみたぞ。,情人节快乐，{d_call}。今年我特意尝试做了这款特制『{p['val_gift']}』哦。
2,団長,手が込んでてすごい！大切に食べるよ。,做工好精致！我会好好品尝的。
3,{name},ふふ、汝の笑顔を見られるなら、どんな苦労も報われるというものだ。,呵呵，只要能看到你的笑容，无论花费多少心血都完全值得了。
info,,,scene_{cid}_s2_valentine
""", encoding="utf-8")

    # 13. 白色情人节回礼 Y1 scene_{cid}_s1_white
    (cdir / f"scene_{cid}_s1_white.csv").write_text(f"""id,name,text,trans
1,団長,{name}、バレンタインのお返しだよ。受け取ってくれる？,{name}，这是情人节的回礼哦。愿意收下吗？
2,{name},これを私に……？ありがとう、{d_call}！大切に味わわせてもらうよ。,这是送给我的……？谢谢你，{d_call}！我会满怀珍惜地细细品味的。
3,{name},汝の温かな心遣い、胸に染み渡るようだ。,你这份体贴入微的温柔心意，仿佛瞬间温暖了我的整个胸膛。
info,,,scene_{cid}_s1_white
""", encoding="utf-8")

    # 14. 白色情人节回礼 Y2 scene_{cid}_s2_white
    (cdir / f"scene_{cid}_s2_white.csv").write_text(f"""id,name,text,trans
1,団長,{name}、今年もいつもありがとう。ホワイトデーのお返しだよ！,{name}，今年也一直感谢你的陪伴。这是白色情人节的回礼！
2,{name},ふふっ、私の好みを完璧に把握しているな。実に嬉しいぞ。,呵呵，你真是完美摸透了我的喜好呢。心里着实欢喜极了。
3,{name},汝と共にいる時間は、何よりも甘美で満たされる。これからもよろしく頼むぞ。,与你相伴度过的每分每秒，都比世间万物更甜美满足。今后也请多多关照了。
info,,,scene_{cid}_s2_white
""", encoding="utf-8")

    # 15. 新春除夜祈愿 scene_{cid}_s1_newyear
    (cdir / f"scene_{cid}_s1_newyear.csv").write_text(f"""id,name,text,trans
1,{name},あけましておめでとう、{d_call}！初日の出が実に神々しいな。,新年快乐，{d_call}！新年的第一缕曙光着实神圣庄严啊。
2,団長,あけましておめでとう！今年もよろしくね！,新年快乐！今年也请多多指教啦！
3,{name},今年一年が、汝とグランサイファーにとって栄光に満ちた年となるよう、我が祈願を捧げよう！,我向苍穹起誓祈愿：愿新的一年里，汝与格兰赛法号的每一步都满载无上荣耀！
info,,,scene_{cid}_s1_newyear
""", encoding="utf-8")

    # 16. 万圣特别篇 scene_{cid}_s1_halloween
    (cdir / f"scene_{cid}_s1_halloween.csv").write_text(f"""id,name,text,trans
1,{name},ハッピーハロウィン！トリック・オア・トリート、だぞ{d_call}！,万圣节快乐！不给糖就捣蛋哦，{d_call}！
2,団長,はい、特製のお菓子だよ！いたずらは勘弁してね。,给，特制的大份糖果点心！捣蛋就饶了我吧。
3,{name},ははっ、見事な備えだな。ならば悪戯の代わりに、今夜は汝の仮装パーティーに付き合おう！,哈哈，准备得挺周全嘛。那么作为饶你一命的代价，今晚就陪我尽情畅享变装派对吧！
info,,,scene_{cid}_s1_halloween
""", encoding="utf-8")

    # 17. 圣诞特别篇 scene_{cid}_s1_christmas
    (cdir / f"scene_{cid}_s1_christmas.csv").write_text(f"""id,name,text,trans
1,{name},メリークリスマス、{d_call}！聖夜の雪が空を白く染め上げているな。,圣诞快乐，{d_call}！圣洁的夜雪已然将浩瀚长空染成了一片无瑕纯白。
2,団長,メリークリスマス！今夜はごちそうを囲んで暖まろう。,圣诞快乐！今晚大家一起围着丰盛大餐好好暖暖身子吧。
3,{name},ふふ、汝の笑顔が最高の贈り物だ。この静かな聖夜を、心ゆくまで共に過ごそう。,呵呵，你的笑容就是最好的圣诞馈赠。让我们在这宁静的圣夜里，尽情相伴吧。
info,,,scene_{cid}_s1_christmas
""", encoding="utf-8")

def main():
    total = 0
    for cid, profile in CHAR_PROFILES.items():
        generate_scenes_for_character(cid, profile)
        total += 17
        print(f"Generated 17 scenarios for {cid:12} in corpus/gbf/{cid}/")

    print(f"\nSuccessfully generated {total} scenario files across 14 characters!")

if __name__ == "__main__":
    main()
