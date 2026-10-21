#!/usr/bin/env python3
"""Canonical modular scenario generator and visual/audio asset scaffolder for Phase 3 Divine Generals:
- indara (インダラ / 巳蛇)
- sanchira (サンチラ / 午马)
"""

import csv
import math
import struct
import wave
from pathlib import Path
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent

PHASE3_CONFIG = [
    {
        "id": "indara",
        "name": "インダラ",
        "name_zh": "因达拉",
        "title": "巳（蛇）之神将",
        "dancho_h": "団長",
        "color_primary": (126, 34, 206),   # Deep royal purple
        "color_secondary": (30, 27, 75),    # Dark midnight purple
        "voice_freq": 460.0,
        "q1_ja": "巳神宮のインダラよ。フン、私の毒を恐れないなんて、物好きな団長ね。仲間に加えてあげるわ。",
        "q1_zh": "我是巳神宫的因达拉。哼，居然不怕我的蛇毒，真是个爱管闲事的怪人团长呢。就特别允许你收我入队好了。",
        "q2_ja": "私の前で団長に手を出そうなんて、いい度胸じゃない！白蛇よ、奴らの急所を噛み砕きなさい！",
        "q2_zh": "敢当着我的面对团长动粗，胆子倒是不小嘛！灵蛇，给我狠狠咬碎那帮家伙的要害！",
        "q3_ja": "べ、別にアンタの心配なんてしてないわよ！……でも、怪我がないなら……よかったわ。",
        "q3_zh": "我、我可没有在担心你啊！……不过，既然你没受伤……那就好。",
        "flb_ja": "真・神将覚醒……！アンタが信じてくれたから、私は蛇神の呪縛を力に変えられたのよ！いくわよ、団長！",
        "flb_zh": "真·神将觉醒……！正是因为你全心信任我，我才能将蛇神的宿命诅咒化作力量！我们要上咯，团长！",
        "val1_ja": "ほ、ほら受け取りなさい！手作りチョコよ。毒なんて入ってないから、黙って食べればいいの！",
        "val1_zh": "给、给我收下！这是手作巧克力。里面可没下毒，少废话赶紧吃下去就是了！",
        "val2_ja": "二年目も渡す羽目になるとはね……。アンタの胃袋、もう完全に私の手中に落ちたってことよ。",
        "val2_zh": "没想到第二年还得给你送啊……这就说明你的胃袋已经彻底落入本神将的掌心了呢。",
        "daily_ja": "アンタ、働きすぎよ。たまには私の隣で休みなさい。……肩くらい揉んであげてもいいわよ。",
        "daily_zh": "你啊，工作得太拼命了。偶尔也来我身边歇会儿。……给你捏捏肩膀也是可以的哦。",
        "battle_ja": "団長に仇なす雑魚共、この場で跡形もなく溶かしてあげるわ！蛇咬連撃ーーッ！！",
        "battle_zh": "胆敢加害团长的杂碎们，就在这里被我融化得灰都不剩吧！蛇咬连击——！！",
    },
    {
        "id": "sanchira",
        "name": "サンチラ",
        "name_zh": "桑琪拉",
        "title": "午（马）之神将",
        "dancho_h": "団長",
        "color_primary": (220, 38, 38),    # Crimson flame red
        "color_secondary": (69, 10, 10),    # Deep dark crimson
        "voice_freq": 500.0,
        "q1_ja": "午神宮のサンチラだ！大空を疾風のごとく駆け巡るのが私の役目！団長、一緒に突っ走ろうぜ！",
        "q1_zh": "我是午神宫的桑琪拉！如疾风般奔腾天际就是我的使命！团长，让我们一起风驰电掣地奔驰吧！",
        "q2_ja": "団長、私の背中にしっかり捕まってろ！天馬の蹄で敵陣を真っ二つに踏み破ってやる！",
        "q2_zh": "团长，紧紧抓稳我的马鞍！看我用天马神蹄把这帮敌阵踩成两半！",
        "q3_ja": "ふぅーっ！いい汗かいたな！団長と肩を並べて走る風は、天下一品に気持ちいいぜ！",
        "q3_zh": "呼——！痛痛快快流了一身汗！能和团长并肩疾驰的狂风，感觉简直是天下第一爽快！",
        "flb_ja": "限界突破！天馬轟雷の真髄を今ここに解き放つ！団長、私についてこいっ！！",
        "flb_zh": "极限突破！天马轰雷的至高精髓此刻当全面爆发！团长，跟紧我的脚步冲锋吧！！",
        "val1_ja": "団長！バレンタインの特製エナジーチョコだ！食べれば百人力で疾走できるぞ！食ってみな！",
        "val1_zh": "团长！这是情人节特制元气巧克力！吃了之后保准你能充满百人之力飞奔狂飙！快尝尝！",
        "val2_ja": "二年目も気合入れて作ったぜ！団長が私の隣で走ってくれるのが、最高の誇りだからな！",
        "val2_zh": "第二年的巧克力我也注入了十二分的干劲哦！能有团长在身旁与我并驾齐驱，就是我最大的骄傲！",
        "daily_ja": "おっ、団長！甲板でランニングか？いいぜ、私の俊足にどこまでついてこられるか勝負だ！",
        "daily_zh": "哟，团长！来甲板上晨跑吗？来得好，看看你能跟上本神将的神速到第几圈吧！",
        "battle_ja": "神馬の蹄を舐めるなよ！団長の道を阻む悪霊共、一撃で踏み潰してやるぜーーッ！！",
        "battle_zh": "可别小看了神马之蹄！胆敢阻挡团长去路的恶灵们，看我一击把你们通通踏平——！！",
    },
]

def make_assets():
    avatars_dir = ROOT / "characters" / "avatars"
    bg_dir = ROOT / "characters" / "backgrounds"
    sound_dir = ROOT / "frontend" / "public" / "sounds" / "gbf"
    avatars_dir.mkdir(parents=True, exist_ok=True)
    bg_dir.mkdir(parents=True, exist_ok=True)
    sound_dir.mkdir(parents=True, exist_ok=True)

    for char in PHASE3_CONFIG:
        cid = char["id"]
        # Avatar (224x224, < 32KB)
        img_av = Image.new("RGB", (224, 224), char["color_primary"])
        draw_av = ImageDraw.Draw(img_av)
        for y in range(224):
            ratio = y / 224
            r = int(char["color_primary"][0] * (1 - ratio) + char["color_secondary"][0] * ratio)
            g = int(char["color_primary"][1] * (1 - ratio) + char["color_secondary"][1] * ratio)
            b = int(char["color_primary"][2] * (1 - ratio) + char["color_secondary"][2] * ratio)
            draw_av.line([(0, y), (224, y)], fill=(r, g, b))
        draw_av.rectangle([10, 10, 214, 214], outline=(255, 255, 255, 180), width=2)
        draw_av.ellipse([56, 56, 168, 168], outline=(255, 215, 0, 200), width=3)
        img_av.save(avatars_dir / f"{cid}.jpg", "JPEG", quality=85)

        # Background (1024x576)
        img_bg = Image.new("RGB", (1024, 576), char["color_primary"])
        draw_bg = ImageDraw.Draw(img_bg)
        for y in range(576):
            ratio = y / 576
            r = int(char["color_primary"][0] * (1 - ratio) + char["color_secondary"][0] * ratio)
            g = int(char["color_primary"][1] * (1 - ratio) + char["color_secondary"][1] * ratio)
            b = int(char["color_primary"][2] * (1 - ratio) + char["color_secondary"][2] * ratio)
            draw_bg.line([(0, y), (1024, y)], fill=(r, g, b))
        draw_bg.rectangle([50, 50, 974, 526], outline=(255, 255, 255, 180), width=4)
        draw_bg.ellipse([362, 138, 662, 438], outline=(255, 215, 0, 180), width=4)
        img_bg.save(bg_dir / f"{cid}.jpg", "JPEG", quality=90)

        # Audio
        for suffix, mul, dur in [("", 1.0, 1.2), ("_greeting", 1.05, 1.6), ("_call_opener", 0.95, 1.4)]:
            apath = sound_dir / f"{cid}{suffix}.mp3"
            freq = char["voice_freq"] * mul
            sample_rate = 24000
            n_samples = int(sample_rate * dur)
            with wave.open(str(apath), "wb") as wav_file:
                wav_file.setnchannels(1)
                wav_file.setsampwidth(2)
                wav_file.setframerate(sample_rate)
                data = bytearray()
                for i in range(n_samples):
                    t = float(i) / sample_rate
                    env = math.sin(math.pi * t / dur)
                    val = int(32767.0 * 0.3 * env * math.sin(2.0 * math.pi * freq * t))
                    val = max(-32767, min(32767, val))
                    data.extend(struct.pack("<h", val))
                wav_file.writeframes(data)
        print(f"Generated visual and audio assets for [{cid}]")

def make_episodes():
    for char in PHASE3_CONFIG:
        cid = char["id"]
        cname = char["name"]
        dh = char["dancho_h"]
        cdir = ROOT / "corpus" / "gbf" / cid
        cdir.mkdir(parents=True, exist_ok=True)

        scenarios = [
            (
                f"scene_{cid}_q1_s10.csv",
                [
                    (cname, char["q1_ja"], char["q1_zh"]),
                    ("団長", "一緒に大空の果てを目指そう！", "一起来朝着大空的尽头前进吧！"),
                    (cname, f"フン、{dh}の言葉、嘘じゃないでしょうね？期待してるわ。", f"哼，{dh}说出的话可不能食言哦？我可是很期待的。"),
                ]
            ),
            (
                f"scene_{cid}_q2_s10.csv",
                [
                    (cname, char["q2_ja"], char["q2_zh"]),
                    ("団長", f"{cname}、合わせて突撃だ！", f"{cname}，配合节奏一同突击！"),
                    ("ルリア", f"{cname}さん、すごいです！神将の加護が広がっています！", f"{cname}小姐太厉害了！神将的加护正在战场上扩散！"),
                ]
            ),
            (
                f"scene_{cid}_q3_s10.csv",
                [
                    (cname, char["q3_ja"], char["q3_zh"]),
                    ("団長", f"{cname}、大活躍だったね。ありがとう。", f"{cname}今天大活跃呢，谢谢你。"),
                    (cname, f"{dh}に褒めてもらえると……悪くない気分ね。", f"能得到{dh}的夸奖……感觉倒也不赖呢。"),
                ]
            ),
            (
                f"scene_fate_{cid}_ep1.csv",
                [
                    (cname, f"{dh}、私にとってグランサイファーはもう一つの故郷よ。", f"{dh}，对我而言格兰赛法号就是我的第二个家。"),
                    ("団長", "いつでも帰っておいで。ここはみんなの居場所だよ。", "无论何时欢迎回家。这里是属于大家的心灵归宿。"),
                    (cname, f"ええ！{dh}のために、この力を惜しみなく振るってあげるわ！", f"嗯！为了{dh}，我定将毫无保留地挥洒这份神将之力！"),
                ]
            ),
            (
                f"scene_{cid}_flb_ep1.csv",
                [
                    (cname, char["flb_ja"], char["flb_zh"]),
                    ("団長", f"いこう、{cname}！空の彼方へ！", f"我们走，{cname}！飞向天空的彼方！"),
                    (cname, "真・神将覚醒！大空を統べる力を御覧あれ！", "真·神将觉醒！请见证统御大空的至高神威！"),
                ]
            ),
            # Seasonal Year 1
            (
                f"scene_s1_valentine_{cid}.csv",
                [
                    (cname, char["val1_ja"], char["val1_zh"]),
                    ("団長", "ありがとう！すごく美味しそう！", "谢谢你！看起来太美味了！"),
                    (cname, f"べ、別に{dh}のために張り切ったわけじゃないんだからね！", f"我、我可不是专门为了{dh}才大费周章制作的哦！"),
                ]
            ),
            (
                f"scene_s1_white_{cid}.csv",
                [
                    ("団長", f"{cname}、バレンタインのお返しだよ。いつもありがとう。", f"{cname}，这是情人节的回礼哦。平时一直谢谢你。"),
                    (cname, f"{dh}からお返しをもらえるなんて……あ、ありがとう。", f"竟然能收到{dh}的回礼……谢、谢谢你啦。"),
                    (cname, "大切に味わって食べるわ。一生の宝物にするから。", "我会细细品尝的。这会是我一生的珍宝。"),
                ]
            ),
            (
                f"scene_s1_halloween_{cid}.csv",
                [
                    (cname, f"トリック・オア・トリート！{dh}、お菓子をくれないと悪戯しちゃうわよ？", f"不给糖就捣乱！{dh}，不给点心的话我可要恶作剧了哦？"),
                    ("団長", "はい、特製のカボチャ菓子だよ。", "给，这是特制的南瓜点心哦。"),
                    (cname, "ふふ、素直でよろしい！空のハロウィンも悪くないわね！", "呵呵，真听话！空之世界的万圣节倒也不赖嘛！"),
                ]
            ),
            (
                f"scene_s1_christmas_{cid}.csv",
                [
                    (cname, f"メリークリスマス、{dh}！聖夜の雪明かり、綺麗ね。", f"圣诞快乐，{dh}！圣夜的雪光倒映着星空，真美呢。"),
                    ("団長", "一緒に温かいスープを飲もうか。", "我们一起来喝碗热腾腾的浓汤吧。"),
                    (cname, f"ええ……{dh}と過ごす聖夜なら、寒さなんて吹き飛ぶわ。", f"嗯……只要是和{dh}一起度过的圣夜，严寒什么的一下子就烟消云散了。"),
                ]
            ),
            (
                f"scene_s1_newyear_{cid}.csv",
                [
                    (cname, f"あけましておめでとう！{dh}、初日の出よ！", f"新年快乐！{dh}，看啊是新年的初日朝阳！"),
                    ("団長", "あけましておめでとう！今年もよろしくね！", "新年快乐！今年也请多多指教哦！"),
                    (cname, "神将として、新年の平安と大勝利を約束してあげるわ！", "身为十二神将，我向你保证新一年的平安顺遂与全军大胜！"),
                ]
            ),
            (
                f"scene_s1_birthday_{cid}.csv",
                [
                    (cname, f"{dh}、お誕生日おめでとう！", f"{dh}，祝你生日快乐！"),
                    ("団長", "祝ってくれて本当に嬉しいよ！ありがとう！", "能得到你的祝福我真的太高兴了！谢谢你！"),
                    (cname, f"{dh}が生まれてきてくれたことに、感謝してるわ。", f"对于{dh}降生在这个世上这件事，我由衷充满感谢。"),
                ]
            ),
            # Seasonal Year 2
            (
                f"scene_s2_valentine_{cid}.csv",
                [
                    (cname, char["val2_ja"], char["val2_zh"]),
                    ("団長", "今年も最高の手作りだね！いただきます！", "今年的手作点心也是顶级杰作呢！我不客气地开动啦！"),
                    (cname, f"ふふっ、{dh}が美味しそうに食べる姿を見るのが一番よ！", f"呵呵，看到{dh}吃得这么香的样子才是我最开心的！"),
                ]
            ),
            (
                f"scene_s2_white_{cid}.csv",
                [
                    ("団長", f"{cname}、二年目のホワイトデーのお返しだよ。", f"{cname}，这是第二年的白色情人节回礼哦。"),
                    (cname, f"二年連続で{dh}から想いをもらえるなんて……胸がいっぱいよ。", f"能连续两年从{dh}手里收到这份满满的真心……心里满满的。"),
                ]
            ),
            (
                f"scene_s2_halloween_{cid}.csv",
                [
                    (cname, f"{dh}！今年の衣装、少し雰囲気を変えてみたんだけど似合ってる？", f"{dh}！我今年的盛装打扮稍微换了种风格，看着合适吗？"),
                    ("団長", "すごく似合ってて最高に格好良いよ！", "非常相配，简直帅气极了！"),
                    (cname, f"ふん、{dh}に見る目があって安心したわ！", f"哼，算{dh}有眼光，我也放心啦！"),
                ]
            ),
            (
                f"scene_s2_christmas_{cid}.csv",
                [
                    (cname, f"二年目の聖夜も、こうして{dh}と過ごせて嬉しいわ……！", f"第二年的神圣之夜，也能像这样陪伴在{dh}身旁，真好……！"),
                    ("団長", "来年も再来年も、ずっと一緒に過ごそうね。", "明年也好后年也好，我们要一直一起过节哦。"),
                    (cname, "ええ、約束よ！ずっとアンタの隣で背中を守ってあげる！", "嗯，一言为定！我会一直守在你身边守护你的后背！"),
                ]
            ),
            (
                f"scene_s2_newyear_{cid}.csv",
                [
                    (cname, f"あけましておめでとう！今年もグランサイファーに福徳が満ちますように！", "新年快乐！愿今年格兰赛法号上同样福泽绵长、诸邪退散！"),
                    ("団長", "今年もよろしくね！初詣に行こう！", "今年也请多关照！我们一起去新年初诣吧！"),
                    (cname, f"ええ！神将として、そして{dh}の仲間として、精一杯戦うわ！", f"好！身为神将，更身为{dh}不可分割的战友，我定将全力而战！"),
                ]
            ),
            (
                f"scene_s2_birthday_{cid}.csv",
                [
                    (cname, f"{dh}、お誕生日おめでとう！二年目も隣にいられて誇らしいわ！", f"{dh}，生日快乐！第二年依然能陪伴在您身旁我深感自豪！"),
                    ("団長", "いつも支えてくれてありがとう。頼りにしてるよ。", "一直以来支持着我谢谢你。我很信赖你哦。"),
                    (cname, f"これからもずっと、{dh}の行く道を切り拓いてあげるわ！", f"今后也要一直一直，永远为你斩开前行道路的荆棘！"),
                ]
            ),
            # Ship & Battle
            (
                f"scene_{cid}_daily_deck.csv",
                [
                    (cname, char["daily_ja"], char["daily_zh"]),
                    ("団長", "たまにはこうしてのんびりするのもいいね。", "偶尔像这样悠闲地吹吹风也很惬意呢。"),
                    (cname, f"ええ……。{dh}と過ごすこういう時間、案外悪くないわね。", f"是啊……能与{dh}共度这种时光，意外地让人心情舒畅呢。"),
                ]
            ),
            (
                f"scene_{cid}_battle_vow.csv",
                [
                    (cname, char["battle_ja"], char["battle_zh"]),
                    ("団長", f"{cname}、一気に決めるぞ！突撃だ！", f"{cname}，一鼓作气解决对手！全军突击！"),
                    (cname, f"任せなさい！神将の真髄、骨の髄まで叩き込んであげるわ！", f"交给我吧！神将之精髓，定让他们刻骨铭心！"),
                ]
            ),
        ]

        for fname, lines in scenarios:
            fpath = cdir / fname
            with open(fpath, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["id", "name", "text", "trans"])
                for idx, (spk, ja, zh) in enumerate(lines, 1):
                    writer.writerow([idx, spk, ja, zh])
                writer.writerow(["info", "", "", Path(fname).stem])
        print(f"Generated 19 canonical CSVs for [{cid}]")

if __name__ == "__main__":
    make_assets()
    make_episodes()
    print("Done generating Phase 3 visual/audio assets and scenarios!")
