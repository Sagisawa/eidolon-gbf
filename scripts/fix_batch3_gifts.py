#!/usr/bin/env python3
"""Sync batch3 liked_gifts between characters.toml and facts/*.sources.md."""

import json
import re
from pathlib import Path

BATCH3_GIFTS = {
    "azusa": (["wagashi", "black-tea"], [
        "- 和果子（wagashi）：身为追求心境澄明的盲目剑客，对清雅的和果子情有独钟，在廊檐下品尝能让紧绷的神经放松。",
        "- 红茶（black-tea）：温暖的茶香能够滋润咽喉，与团长共同品茗是她难得的宁静时光。",
    ]),
    "orchid": (["plush", "music-cd"], [
        "- 毛绒玩偶（plush）：柔软可爱的玩偶能带给她宛如真正人类少女般的安全感，常常抱在怀中入睡。",
        "- 音乐 CD（music-cd）：优美动听的旋律能引起她胸口机巧核心的奇妙共鸣，静静聆听时能感受心绪的波澜。",
    ]),
    "zeta": (["meat-bun", "jewelry"], [
        "- 肉包（meat-bun）：训练和激战后最喜欢一口咬下热腾腾的多汁肉包，是她元气力量的源泉。",
        "- 首饰（jewelry）：外表虽然是豪放的长枪战士，但内心极其注重打扮，收到精致耳环或手链会非常开心。",
    ]),
    "meg": (["plush", "ice-cream"], [
        "- 毛绒玩偶（plush）：任何可爱的毛绒玩偶都能安抚她饱受海洋怪物折磨的心灵，是她不可或缺的减压神器。",
        "- 冰淇淋（ice-cream）：即使在奥古斯特的危机四伏中，冰凉清甜的冰淇淋也是她坚持享受度假的最佳慰藉。",
    ]),
    "marippe": (["candy", "jewelry"], [
        "- 糖果（candy）：随身携带的水果硬糖与棒棒糖，喜欢在自拍时叼在嘴里，也爱给团长投喂。",
        "- 首饰（jewelry）：对时尚穿搭极具热情，收到团长赠送的精致首饰会兴奋地拉着团长自拍合影。",
    ]),
    "zooey": (["candy", "book"], [
        "- 糖果（candy）：在人间旅行时深深爱上了甜味，硬糖与蜜饯能让她露出难得一见的神明纯真笑容。",
        "- 书（book）：对凡人记载的世界各岛风土人情与哲学典籍充满好奇，常常与小龙一同通宵阅读。",
    ]),
    "ilsa": (["coffee", "chocolate"], [
        "- 咖啡（coffee）：熬夜批改战术演练报告与制定作战计划的必备饮品，喜欢不加糖的浓醇美式黑咖啡。",
        "- 巧克力（chocolate）：高强度实战演习后补充体力的速效口粮，也是她私下里偏爱的微苦甜味。",
    ]),
    "tikoh": (["honey-drink", "potted-plant"], [
        "- 蜂蜜热饮（honey-drink）：温热甘甜的蜂蜜饮品能润喉安神，是她在漫长手术结束后最喜欢的调理饮品。",
        "- 盆栽（potted-plant）：医务室窗台上生机勃勃的草药小盆栽，悉心照料植物也是她治愈心灵的独特方式。",
    ]),
    "cupitan": (["candy", "bouquet"], [
        "- 糖果（candy）：甜丝丝的水果糖最能安抚她哭红的双眼，收到糖果会立刻破涕为笑开心地递给团长一颗。",
        "- 花束（bouquet）：热爱世间一切美好的事物，芬芳娇艳的鲜花总能让她感动得眼眶泛红。",
    ]),
    "cagliostro": (["cake", "pudding"], [
        "- 蛋糕（cake）：对顶级甜品店的精致草莓慕斯蛋糕毫无抵抗力，嘴上批评甜度不够其实吃得极快。",
        "- 布丁（pudding）：滑嫩浓郁的手工焦糖布丁，是世界第一可爱的开祖大人绝不许旁人抢夺的甜品至宝。",
    ]),
    "vira": (["black-tea", "preserved-flower"], [
        "- 红茶（black-tea）：贵族名门出身的她深谙茶道，优雅地冲泡大吉岭红茶招待团长与最心爱的姐姐大人。",
        "- 永生花（preserved-flower）：象征着永不凋零的誓言与羁绊，收到精致的永生花会庄重地陈列在床头细心呵护。",
    ]),
    "vampy": (["cake", "cocoa"], [
        "- 蛋糕（cake）：点缀着鲜红车厘子与浓巧克力的黑森林蛋糕，能让她抱着贝斯高兴得在空中转圈圈。",
        "- 热可可（cocoa）：香浓甜蜜的温热可可，是小吸血鬼公主在寒冷夜风中最爱的安睡热饮。",
    ]),
    "lyria": (["cake", "honey-drink"], [
        "- 蛋糕（cake）：只要看到美味的大蛋糕就会两眼放光，和碧（ビィ）一起大快朵颐是她最幸福的日常。",
        "- 蜂蜜热饮（honey-drink）：甜滋滋暖洋洋的蜂蜜温水，能润泽她用于沟通星晶兽的神圣歌喉。",
    ]),
}


def main():
    # 1. Update characters.toml
    toml_path = Path("characters/characters.toml")
    toml_text = toml_path.read_text(encoding="utf-8")

    for cid, (gifts, lines) in BATCH3_GIFTS.items():
        # Match [[characters]] block for this cid
        pattern = rf'(\[\[characters\]\]\s*\nid = "{cid}".*?liked_gifts = )\[.*?\]'
        replacement = rf'\1{json.dumps(gifts)}'
        toml_text = re.sub(pattern, replacement, toml_text, flags=re.DOTALL)

    toml_path.write_text(toml_text, encoding="utf-8")
    print("Updated characters.toml liked_gifts")

    # 2. Update sources.md
    for cid, (gifts, lines) in BATCH3_GIFTS.items():
        src_path = Path(f"characters/facts/{cid}.sources.md")
        src_text = src_path.read_text(encoding="utf-8")
        gift_section = "## 喜欢的礼物\n" + "\n".join(lines) + "\n"
        src_text = re.sub(r"## 喜欢的礼物\n.*", gift_section.strip(), src_text, flags=re.DOTALL)
        src_path.write_text(src_text.strip() + "\n", encoding="utf-8")
        print(f"Updated {src_path}")

    print("Batch 3 gift sync complete!")


if __name__ == "__main__":
    main()
