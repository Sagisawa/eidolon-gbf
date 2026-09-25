"""Sample story files: SCTranslationData CSVs written the way the upstream repository lays
them out, and the game's own script JSON."""

import json
from pathlib import Path

PRODUCER = "0000000000000"

# Mano's first W.I.N.G. episode: the producer, the company president and Mano.
PARK = [
    (PRODUCER, "プロデューサー", "（いよいよ俺が、アイドルを\\nプロデュースする時が来た）", "（终于到了我培育偶像的时候了）"),
    ("1902001010010", "社長", "おはよう、お前を待っていたぞ", "早上好，我正等着你呢"),
    ("1001001010110", "真乃", "公園で鳩と一緒に歌っていました", "我在公园和鸽子一起唱歌"),
    ("select", "", "歌が好きなのか？", "喜欢唱歌吗？"),
    ("select", "", "鳩が好きなのか？", "喜欢鸽子吗？"),
    ("1001001010120", "真乃", "ほわっ……はい、どっちも好きです", "呼哇……嗯，两个都喜欢"),
]
# Won the W.I.N.G. final.
WON = [
    ("6001001060050", "真乃", "……ゆ、優勝、したんですねっ", "……优，优胜了呢"),
    (PRODUCER, "プロデューサー", "……ああ、夢なんかじゃないぞ", "……是啊，不是在做梦哦"),
]
# Knocked out of W.I.N.G., under a file name that doesn't say so.
KNOCKED_OUT = [
    ("6001001020010", "真乃", "私……負けちゃいました……", "我……失败了……"),
]
SEASON_FAILED = [
    ("7902001020010", "社長", "結果は聞いた", ""),
    ("7001001020010", "真乃", "だめだったんですね……", "不行呢……"),
]
AUDITION_LOST = [
    ("5001001000120010", "真乃", "ごめんなさい……", "对不起……"),
]
# A card of Kogane's, with a joint line shared with Mano.
KOGANE_CARD = [
    ("2011004010010", "恋鐘", "長崎のちゃんぽん、ばりうまかよ！", "长崎的什锦面超好吃的！"),
    ("2011004010020", "恋鐘の母", "恋鐘、写真ば撮ろうか", "恋钟，拍张照片吧"),
    ("2011004010030", "真乃＆恋鐘", "はいっ！", "好的！"),
]
# An event episode with neither Mano nor Kogane speaking.
HIORI_EVENT = [
    ("4001004010010", "灯織", "写真の撮影、頑張ります", "拍照，我会加油的"),
    ("4001004010020", "めぐる", "公園で撮るんだって！", "听说要在公园拍！"),
]


def write_story(root: Path, relative: str, rows: list[tuple[str, str, str, str]], info: str | None) -> None:
    lines = ["id,name,text,trans", *(",".join(row) for row in rows)]
    if info is not None:
        lines += [f"info,{info}.json,,", "译者,テスト,,"]
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    # SCTranslationData files come with a BOM and CRLF line endings as often as not.
    path.write_text("﻿" + "\r\n".join(lines) + "\r\n", encoding="utf-8")


def write_sample_stories(root: Path) -> Path:
    write_story(root, "櫻木真乃/W.I.N.G.編/公園の歌声.csv", PARK, "produce_events/100100101")
    write_story(root, "櫻木真乃/W.I.N.G.編/決勝後コミュ.csv", WON, "produce_events/600100106")
    write_story(root, "櫻木真乃/W.I.N.G.編/produce_events_600100102.csv", KNOCKED_OUT, "produce_events/600100102")
    write_story(root, "櫻木真乃/W.I.N.G.編/シーズン1（失敗）.csv", SEASON_FAILED, "produce_events/700100102")
    write_story(root, "櫻木真乃/W.I.N.G.編/オーディション後②.csv", AUDITION_LOST, "produce_communication_auditions/500100100012")
    write_story(root, "月岡恋鐘/【ばりうまかブルース】月岡恋鐘/長崎の味.csv", KOGANE_CARD, "produce_events/201100401")
    write_story(root, "283活动剧情/Light up the illumination/第1話.csv", HIORI_EVENT, "game_event_communications/400100401")
    return root


# The game's own scripts: an array of frames, as served under `assets/json/<script>.json`.
# Mano's first W.I.N.G. episode with a choice: each option jumps to its own reaction, and
# both reactions rejoin the story afterwards. Frames without text are stage directions.
PARK_SCRIPT = [
    {"bg": "park_day", "bgm": "bgm_0001"},
    {"id": "0000000000000", "speaker": "プロデューサー", "text": "（いよいよ俺が、アイドルを\nプロデュースする時が来た）"},
    {"id": "1001001010110", "speaker": "真乃", "text": "公園で鳩と一緒に歌っていました", "voice": "produce_events/1001001010110"},
    {"select": "歌が好きなのか？", "nextLabel": "song"},
    {"select": "鳩が好きなのか？", "nextLabel": "dove"},
    {"label": "song", "id": "1001001010120", "speaker": "真乃", "text": "はい、歌うのが大好きです", "nextLabel": "join"},
    {"label": "dove", "id": "1001001010130", "speaker": "真乃", "text": "ほわっ……鳩さん、かわいいですよね", "nextLabel": "join"},
    {"label": "join", "id": "1001001010140", "speaker": "真乃", "text": "また、公園に来てくれますか？"},
    {"text": "", "speaker": "真乃"},
    {"text": "（夕日が公園を照らしている）"},
]
# The same script SCTranslationData already has, translated (see `WON`).
WON_SCRIPT = [
    {"id": "6001001060050", "speaker": "真乃", "text": "……ゆ、優勝、したんですねっ"},
    {"id": "0000000000000", "speaker": "プロデューサー", "text": "……ああ、夢なんかじゃないぞ"},
]
KNOCKED_OUT_SCRIPT = [
    {"id": "6001001020010", "speaker": "真乃", "text": "私……負けちゃいました……"},
]
# A card of Kogane's that SCTranslationData has not translated.
KOGANE_SCRIPT = [
    {"id": "2011005010010", "speaker": "恋鐘", "text": "ちゃんぽんば作ったけん、食べてみて！"},
    {"select": "いただきます", "nextLabel": "a"},
    {"select": "あとでもらうよ", "nextLabel": "b"},
    {"label": "a", "id": "2011005010020", "speaker": "恋鐘", "text": "どげん？ばりうまかやろ？"},
    {"label": "b", "id": "2011005010030", "speaker": "恋鐘", "text": "えー、冷めてしまうばい"},
]


def write_script(root: Path, relative: str, frames: object) -> None:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(frames, ensure_ascii=False), encoding="utf-8")
