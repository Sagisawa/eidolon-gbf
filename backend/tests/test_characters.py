"""Characters come from configuration: the list, the avatars, the image colours, call
backgrounds, stands and greetings, and each one's character sheet."""

import json
import logging
import re
from dataclasses import replace
from pathlib import Path

import pytest

from eidolon.characters import CharacterConfigError, Fact, load_characters, parse_facts
from eidolon.config import Settings, stand_assets_url_from_env
from tests.conftest import (
    AVATAR, BACKGROUND, KOGANE_SHEET, MANO_SHEET, SCSP_AVATAR, CharacterConfig, ClientFactory,
)
from tests.fakes import FakeLLM
from tests.test_text_turn import send_turn, start_conversation

REPO_CHARACTERS = Path(__file__).parents[2] / "characters"


async def test_character_list_shows_name_intro_avatar_colour_and_background_but_not_the_sheet(
    make_client: ClientFactory,
):
    """It is shown before signing in."""
    client = make_client(FakeLLM(), user=None)

    res = await client.get("/api/characters")

    assert res.status_code == 200
    assert res.json() == [
        {
            "id": "mano",
            "name": "櫻木真乃",
            "intro": "illumination STARS 的中心",
            "avatar_url": "/api/characters/mano/avatar",
            "scsp_avatar_url": "/api/characters/mano/scsp-avatar",
            "color": "#ffbad6",
            "background_url": "/api/characters/mano/background",
            "stand": None,  # no stand assets URL is configured
            "idol_id": 1,
            "name_zh": None,  # none configured
            "name_kana": None,
            "name_romaji": None,
            "unit": None,
            "unit_reading": None,  # no world setting
            "unit_order": None,
            "greeting": None,  # none configured
            "call_opener": None,
            "call_poster_url": "/api/characters/mano/background",
            "voxels_url": None,
        },
        {
            "id": "kogane",
            "name": "月岡恋鐘",
            "intro": "L'Antica 的偶像",
            "avatar_url": None,
            "scsp_avatar_url": None,
            "color": "#f84cad",
            "background_url": None,
            "stand": None,
            "idol_id": None,
            "name_zh": None,  # none configured
            "name_kana": None,
            "name_romaji": None,
            "unit": None,
            "unit_reading": None,
            "unit_order": None,
            "greeting": None,
            "call_opener": None,
            "call_poster_url": None,
            "voxels_url": None,
        },
    ]
    assert "ほわっ" not in res.text


async def test_character_list_is_in_idol_number_order_and_those_without_one_follow_as_configured(
    make_client: ClientFactory, characters: CharacterConfig
):
    """Mano is idol 1 and Kogane has no idol number (the fixture)."""
    characters.add("meguru", "八宮めぐる", "sheet", idol_id=3)
    characters.add("someone", "誰か", "sheet")
    characters.add("hiori", "風野灯織", "sheet", idol_id=2)
    client = make_client(FakeLLM(), user=None)

    listed = (await client.get("/api/characters")).json()

    assert [(c["id"], c["idol_id"]) for c in listed] == [
        ("mano", 1), ("hiori", 2), ("meguru", 3), ("kogane", None), ("someone", None),
    ]


async def test_character_list_gives_the_other_names_she_is_searched_by(
    make_client: ClientFactory, characters: CharacterConfig
):
    characters.add("meguru", "八宮めぐる", "sheet", other_names=("八宫巡", "はちみや めぐる", "Hachimiya Meguru"))
    client = make_client(FakeLLM(), user=None)

    listed = {c["id"]: c for c in (await client.get("/api/characters")).json()}

    assert [listed["meguru"][f] for f in ("name_zh", "name_kana", "name_romaji")] == [
        "八宫巡", "はちみや めぐる", "Hachimiya Meguru",
    ]


async def test_avatar_is_served_without_a_session_so_img_tags_can_load_it(
    make_client: ClientFactory,
):
    client = make_client(FakeLLM(), user=None)

    res = await client.get("/api/characters/mano/avatar")

    assert res.status_code == 200
    assert res.content == AVATAR
    assert (await client.get("/api/characters/kogane/avatar")).status_code == 404
    assert (await client.get("/api/characters/nobody/avatar")).status_code == 404


async def test_scsp_avatar_is_served_without_a_session_like_the_avatar(
    make_client: ClientFactory,
):
    client = make_client(FakeLLM(), user=None)

    res = await client.get("/api/characters/mano/scsp-avatar")

    assert res.status_code == 200
    assert res.content == SCSP_AVATAR
    assert (await client.get("/api/characters/kogane/scsp-avatar")).status_code == 404
    assert (await client.get("/api/characters/nobody/scsp-avatar")).status_code == 404


async def test_call_background_is_served_without_a_session_like_the_avatar(
    make_client: ClientFactory,
):
    client = make_client(FakeLLM(), user=None)

    res = await client.get("/api/characters/mano/background")

    assert res.status_code == 200
    assert res.content == BACKGROUND
    assert (await client.get("/api/characters/kogane/background")).status_code == 404
    assert (await client.get("/api/characters/nobody/background")).status_code == 404


@pytest.mark.parametrize("picture", ["avatar", "scsp-avatar", "background"])
async def test_avatar_and_background_are_cached_by_the_browser_and_revalidated_by_etag(
    make_client: ClientFactory, picture: str
):
    """The sidebar and the list filter show every avatar on each visit; without this
    they were downloaded again every time and flashed the name's first letter."""
    client = make_client(FakeLLM(), user=None)

    res = await client.get(f"/api/characters/mano/{picture}")

    assert res.headers["cache-control"] == "public, max-age=86400"
    again = await client.get(
        f"/api/characters/mano/{picture}", headers={"if-none-match": res.headers["etag"]}
    )
    assert again.status_code == 304
    assert again.headers["cache-control"] == "public, max-age=86400"
    stale = await client.get(f"/api/characters/mano/{picture}", headers={"if-none-match": '"stale"'})
    assert stale.status_code == 200


@pytest.mark.parametrize(
    ("character", "sheet", "other_sheet"),
    [("mano", MANO_SHEET, KOGANE_SHEET), ("kogane", KOGANE_SHEET, MANO_SHEET)],
)
async def test_each_character_talks_with_her_own_character_sheet(
    make_client: ClientFactory, character: str, sheet: str, other_sheet: str
):
    llm = FakeLLM(["<ja>はい</ja><zh>好</zh>"])
    client = make_client(llm)
    conversation_id = await start_conversation(client, character)

    await send_turn(client, conversation_id, "你好")

    system = llm.prompts[0][0]
    assert sheet in system.content
    assert other_sheet not in system.content


async def test_a_character_added_to_the_configuration_can_be_talked_to(
    make_client: ClientFactory, characters: CharacterConfig
):
    characters.add("hiori", "風野灯織", "# 人设\n你是風野灯織。", intro="认真的努力家")
    llm = FakeLLM(["<ja>はい</ja><zh>好</zh>"])
    client = make_client(llm)

    listed = (await client.get("/api/characters")).json()
    conversation_id = await start_conversation(client, "hiori")
    await send_turn(client, conversation_id, "你好")

    assert [c["id"] for c in listed] == ["mano", "kogane", "hiori"]
    assert "你是風野灯織。" in llm.prompts[0][0].content


async def test_conversation_with_a_character_removed_from_the_configuration_is_gone(
    make_client: ClientFactory, characters: CharacterConfig
):
    characters.add("hiori", "風野灯織", "# 人设\n你是風野灯織。")
    conversation_id = await start_conversation(make_client(FakeLLM()), "hiori")
    CharacterConfig(characters.directory).add("mano", "櫻木真乃", MANO_SHEET)
    client = make_client(FakeLLM())

    res = await client.post(f"/api/conversations/{conversation_id}/turns", json={"text": "你好"})

    assert res.status_code == 404
    assert res.json()["detail"] == "角色不存在"


def test_repository_configures_its_idols_with_their_voices():
    loaded = load_characters(REPO_CHARACTERS / "characters.toml")

    assert {id: c.voice_id for id, c in loaded.items()} == {
        "narmaya": "d2f31010862d449eb0896dd7358f3531",
        "vikala": "e20d009971a343f4bc04eba1191f03b7",
        "nier": "c31f409581a84f3e8b7d9b0a1f2c3d4e",
        "anila": "f0a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5",
        "andira": "a1b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6",
        "mahira": "b2c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7",
        "vajra": "c3d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8",
        "kumbhira": "d4e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9",
        "catura": "e5f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0",
        "cindhara": "f6a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1",
        "makora": "a7b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2",
        "haira": "b8c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3",
        "indara": "c9d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4",
        "sanchira": "d0e1f2a3b4c5d6e7f8a9b0c1d2e3f4a5",
        "uno": "01010101010101010101010101010101",
        "song": "02020202020202020202020202020202",
        "sarasa": "03030303030303030303030303030303",
        "quatre": "04040404040404040404040404040404",
        "funf": "05050505050505050505050505050505",
        "seox": "06060606060606060606060606060606",
        "seofon": "07070707070707070707070707070707",
        "eahta": "08080808080808080808080808080808",
        "niyon": "09090909090909090909090909090909",
        "tien": "10101010101010101010101010101010",
        "maria": "11111111111111111111111111111111",
        "fraux": "12121212121212121212121212121212",
        "geisenborger": "13131313131313131313131313131313",
        "estarriola": "14141414141414141414141414141414",
        "caim": "15151515151515151515151515151515",
        "lobelia": "16161616161616161616161616161616",
        "katzelia": "17171717171717171717171717171717",
        "alanaan": "18181818181818181818181818181818",
        "haaselia": "19191919191919191919191919191919",
        "chichiri": "7cf0b0ea9d2b04e4b74a9f1de22f2b73",
        "uruki": "ffcf953f582277040f71ed164e942aeb",
        "shushuku": "1136ccb7de83c8434adcef22368603af",
        "ami": "080edfa2198f39af811cafc7e9dc710e",
        "wilnas": "cea8b67b2953ac7cfebef869e31fe7a3",
        "wamdus": "7c3cf28355453c83fd164e0914be8fb7",
        "galleon": "d0f58e1eb9bfaa52c393f4d22299cf08",
        "ewiyar": "fb45af9c3a8f93c308d1f0bdc2ae6f65",
        "luwoh": "05f071700da512bc6b7e1b4516a3b615",
        "fediel": "333cd9cd0a100a2946deb442d1bcc949",
        "yggdrasil": "9a22cac6b424719ec65047786027765c",
        "europa": "e68361c3a220cece385cb83a553b9250",
        "brodia": "ede4a32d558ba1abab48eb4fe0cb1b6a",
        "grimnir": "cfdb75a0fbe35a1fccef7bb9df20a76f",
        "sandalphon": "4a26b45da83b7689c3589976ffd221b3",
        "lucifer": "51d6a5df7a34716a046efd4f3773caae",
        "lucilius": "0b32839c47d2eb804d70424c0e108ed7",
        "lucio": "a96e8b271fff3376192fd88b30c8a490",
        "beelzebub": "74723d35ae166d8918809c35a89e7a4c",
        "belial": "644a0ca2266db3fbffaf1e1ea8afefdb",
        "shalem": "167b903ec4a501cecd4f564dd4ef0031",
        "raziel": "cab01d568ff6c229c71b221001beb9c4",
        "olivia": "327ba4398988e45cf50bf936b1620dc6",
        "azusa": "ddba4cf178079fab2fc7edb303e166fe",
        "orchid": "73de8aea077d71dc2c4cb001ed998c7f",
        "zeta": "ccada9c548c52840891925aae64e1f8e",
        "meg": "2ef4dd3ce7a1883e2b8e193753399ea0",
        "marippe": "66e08d076004dc38c9394b4c54dfe119",
        "zooey": "12d20e61bc0fe3126cbc23984bc9a622",
        "ilsa": "88c707beb08672e15a4d4a850b56dcc9",
        "tikoh": "027933dab7e7397789f03cea77cdec00",
        "cupitan": "d26ff295cb9f87e876e98151533b84e1",
        "cagliostro": "c2f9d6e3ca613ddf07b5e0b08789dc1d",
        "vira": "ab5df814e522f40bda413b8da1929412",
        "vampy": "75f2a8032c5599be5578f0ea0c4c40e3",
        "lyria": "d294288c1e1fb85dbbcfd14af4a0f06a",
    }
    assert {id: c.name for id, c in loaded.items()} == {
        "narmaya": "ナルメア",
        "vikala": "ビカラ",
        "nier": "ニーア",
        "anila": "アニラ",
        "andira": "アンチラ",
        "mahira": "マキラ",
        "vajra": "ヴァジラ",
        "kumbhira": "クビラ",
        "catura": "シャトラ",
        "cindhara": "シンダラ",
        "makora": "マコラ",
        "haira": "ハイラ",
        "indara": "インダラ",
        "sanchira": "サンチラ",
        "uno": "ウーノ",
        "song": "ソーン",
        "sarasa": "サラーサ",
        "quatre": "カトル",
        "funf": "フュンフ",
        "seox": "シス",
        "seofon": "シエテ",
        "eahta": "オクトー",
        "niyon": "ニオ",
        "tien": "エッセル",
        "maria": "マリア・テレサ",
        "fraux": "フラウ",
        "geisenborger": "ガイゼンボーガー",
        "estarriola": "エスタリオラ",
        "caim": "カイム",
        "lobelia": "ロベリア",
        "katzelia": "カッツェリーラ",
        "alanaan": "アラナン",
        "haaselia": "ハーゼリーラ",
        "chichiri": "チチリ",
        "uruki": "ウルキ",
        "shushuku": "シュシュク",
        "ami": "アミ",
        "wilnas": "ウィルナス",
        "wamdus": "ワムデュス",
        "galleon": "ガレヲン",
        "ewiyar": "イーウィヤ",
        "luwoh": "ル・オー",
        "fediel": "フェディエル",
        "yggdrasil": "ユグドラシル",
        "europa": "エウロペ",
        "brodia": "ブローディア",
        "grimnir": "グリームニル",
        "sandalphon": "サンダルフォン",
        "lucifer": "ルシフェル",
        "lucilius": "ルシファー",
        "lucio": "ルシオ",
        "beelzebub": "ベルゼバブ",
        "belial": "ベリアル",
        "shalem": "ヘレム・ベン・シャレム",
        "raziel": "ラジエル",
        "olivia": "オリヴィエ",
        "azusa": "アズサ",
        "orchid": "オーキス",
        "zeta": "ゼタ",
        "meg": "メグ",
        "marippe": "まりっぺ",
        "zooey": "ゾーイ",
        "ilsa": "イルザ",
        "tikoh": "ティコ",
        "cupitan": "クピタン",
        "cagliostro": "カリオストロ",
        "vira": "ヴィーラ",
        "vampy": "ヴァンピィ",
        "lyria": "ルリア",
    }
    assert {id: c.speakers for id, c in loaded.items()} == {
        "narmaya": ("ナルメア", "ナルメア/娜尔梅亚", "娜尔梅亚", "娜尔梅娅"),
        "vikala": ("ビカラ", "ビカラ/碧卡拉", "碧卡拉", "ビッキー"),
        "nier": ("ニーア", "ニーア/妮亚", "妮亚", "デス", "デス/死亡"),
        "anila": ("アニラ", "アニラ/阿妮拉", "阿妮拉"),
        "andira": ("アンチラ", "アンチラ/安琪拉", "安琪拉"),
        "mahira": ("マキラ", "マキラ/玛琪拉", "玛琪拉"),
        "vajra": ("ヴァジラ", "ヴァジラ/瓦吉拉", "瓦吉拉"),
        "kumbhira": ("クビラ", "クビラ/久碧拉", "久碧拉", "クビラ/库碧拉", "库碧拉"),
        "catura": ("シャトラ", "シャトラ/夏朵拉", "夏朵拉"),
        "cindhara": ("シンダラ", "シンダラ/辛达拉", "辛达拉", "フアン", "シン"),
        "makora": ("マコラ", "マコラ/玛蔻拉", "玛蔻拉"),
        "haira": ("ハイラ", "ハイラ/海菈", "海菈"),
        "indara": ("インダラ", "インダラ/因达拉", "因达拉"),
        "sanchira": ("サンチラ", "サンチラ/桑琪拉", "桑琪拉"),
        "uno": ("ウーノ", "ウーノ/乌诺", "乌诺"),
        "song": ("ソーン", "ソーン/索恩", "索恩"),
        "sarasa": ("サラーサ", "サラーサ/萨拉萨", "萨拉萨"),
        "quatre": ("カトル", "カトル/卡托尔", "卡托尔"),
        "funf": ("フュンフ", "フュンフ/芬芙", "芬芙"),
        "seox": ("シス", "シス/希斯", "希斯"),
        "seofon": ("シエテ", "シエテ/西埃特", "西埃特"),
        "eahta": ("オクトー", "オクトー/奥克托", "奥克托"),
        "niyon": ("ニオ", "ニオ/妮欧", "妮欧"),
        "tien": ("エッセル", "エッセル/艾瑟尔", "艾瑟尔"),
        "maria": ("マリア・テレサ", "マリア・テレサ/玛利亚・泰蕾莎", "マリア", "玛利亚"),
        "fraux": ("フラウ", "フラウ/芙劳", "芙劳"),
        "geisenborger": ("ガイゼンボーガー", "ガイゼンボーガー/盖森博加", "盖森博加"),
        "estarriola": ("エスタリオラ", "エスタリオラ/艾斯塔利奥拉", "艾斯塔利奥拉"),
        "caim": ("カイム", "カイム/凯姆", "凯姆"),
        "lobelia": ("ロベリア", "ロベリア/罗贝利亚", "罗贝利亚"),
        "katzelia": ("カッツェリーラ", "カッツェリーラ/卡杰莉拉", "卡杰莉拉"),
        "alanaan": ("アラナン", "アラナン/阿拉南", "阿拉南"),
        "haaselia": ("ハーゼリーラ", "ハーゼリーラ/哈洁莉拉", "ハーゼ", "哈洁莉拉"),
        "chichiri": ("チチリ", "チチリ/茜茜莉", "茜茜莉"),
        "uruki": ("ウルキ", "ウルキ/乌鲁姬", "乌鲁姬"),
        "shushuku": ("シュシュク", "シュシュク/修修库", "修修库"),
        "ami": ("アミ", "アミ/阿蜜", "阿蜜"),
        "wilnas": ("ウィルナス", "ウィルナス/维尔纳斯", "维尔纳斯"),
        "wamdus": ("ワムデュス", "ワムデュス/瓦姆杜斯", "瓦姆杜斯"),
        "galleon": ("ガレヲン", "ガレヲン/迦列翁", "迦列翁"),
        "ewiyar": ("イーウィヤ", "イーウィヤ/艾维亚", "艾维亚"),
        "luwoh": ("ル・オー", "ル・オー/鲁欧", "鲁欧"),
        "fediel": ("フェディエル", "フェディエル/菲迪尔", "菲迪尔"),
        "yggdrasil": ("ユグドラシル", "ユグドラシル/尤古多拉希尔", "尤古多拉希尔"),
        "europa": ("エウロペ", "エウロペ/欧罗巴", "欧罗巴"),
        "brodia": ("ブローディア", "ブローディア/布罗迪亚", "布罗迪亚", "神立之剑"),
        "grimnir": ("グリームニル", "グリームニル/格里姆尼尔", "格里姆尼尔", "军神"),
        "sandalphon": ("サンダルフォン", "サンダルフォン/圣德芬", "圣德芬", "天司长"),
        "lucifer": ("ルシフェル", "ルシフェル/路西菲尔", "路西菲尔", "最高天司"),
        "lucilius": ("ルシファー", "ルシファー/路西法", "路西法", "星之民路西法"),
        "lucio": ("ルシオ", "ルシオ/路西欧", "路西欧", "サハル"),
        "beelzebub": ("ベルゼバブ", "ベルゼバブ/别西卜", "别西卜", "黒衣の男", "巴布"),
        "belial": ("ベリアル", "ベリアル/贝利尔", "贝利尔", "狡知"),
        "shalem": ("ヘレム・ベン・シャレム", "ヘレム・ベン・シャレム/赫列尔·本·沙利姆", "シャレム", "沙利姆"),
        "raziel": ("ラジエル", "ラジエル/拉结尔", "拉结尔", "睿智天司"),
        "olivia": ("オリヴィエ", "オリヴィエ/奥利维尔", "奥利维尔", "堕天司"),
        "azusa": ("アズサ", "アズサ/阿梓", "阿梓"),
        "orchid": ("オーキス", "オーキス/欧契斯", "欧契斯"),
        "zeta": ("ゼタ", "ゼタ/泽塔", "泽塔"),
        "meg": ("メグ", "メグ/梅格", "梅格"),
        "marippe": ("まりっぺ", "まりっぺ/玛莉沛", "玛莉沛", "マリ"),
        "zooey": ("ゾーイ", "ゾーイ/佐伊", "佐伊"),
        "ilsa": ("イルザ", "イルザ/艾尔莎", "艾尔莎"),
        "tikoh": ("ティコ", "ティコ/蒂子", "蒂子"),
        "cupitan": ("クピタン", "クピタン/库皮坦", "库皮坦"),
        "cagliostro": ("カリオストロ", "カリオストロ/卡莉奥丝特罗", "卡莉奥丝特罗"),
        "vira": ("ヴィーラ", "ヴィーラ/维拉", "维拉"),
        "vampy": ("ヴァンピィ", "ヴァンピィ/斑比", "斑比"),
        "lyria": ("ルリア", "ルリア/露莉亚", "露莉亚"),
    }
    assert all(c.sheet and c.facts and c.avatar for c in loaded.values())
    assert {id: c.color for id, c in loaded.items()} == {
        "narmaya": "#8a5aa8",
        "vikala": "#f59e0b",
        "nier": "#7c2d58",
        "anila": "#c83232",
        "andira": "#2ea865",
        "mahira": "#d99726",
        "vajra": "#2a78c5",
        "kumbhira": "#d97724",
        "catura": "#38bdf8",
        "cindhara": "#ea580c",
        "makora": "#ec4899",
        "haira": "#0284c7",
        "indara": "#7e22ce",
        "sanchira": "#dc2626",
        "uno": "#4a78a6",
        "song": "#d8b846",
        "sarasa": "#c85828",
        "quatre": "#2a6890",
        "funf": "#f0c030",
        "seox": "#583868",
        "seofon": "#2ea878",
        "eahta": "#8c6838",
        "niyon": "#38b090",
        "tien": "#c83828",
        "maria": "#1d4ed8",
        "fraux": "#b91c1c",
        "geisenborger": "#475569",
        "estarriola": "#059669",
        "caim": "#b45309",
        "lobelia": "#701a75",
        "katzelia": "#0f766e",
        "alanaan": "#ea580c",
        "haaselia": "#1e3a8a",
        "chichiri": "#e11d48",
        "uruki": "#0284c7",
        "shushuku": "#d97706",
        "ami": "#10b981",
        "wilnas": "#dc2626",
        "wamdus": "#06b6d4",
        "galleon": "#b45309",
        "ewiyar": "#15803d",
        "luwoh": "#eab308",
        "fediel": "#6b21a8",
        "yggdrasil": "#84cc16",
        "europa": "#38bdf8",
        "brodia": "#78350f",
        "grimnir": "#0284c7",
        "sandalphon": "#4a6b82",
        "lucifer": "#60a5fa",
        "lucilius": "#1e1b4b",
        "lucio": "#f59e0b",
        "beelzebub": "#831843",
        "belial": "#991b1b",
        "shalem": "#4c1d95",
        "raziel": "#16a34a",
        "olivia": "#581c87",
        "azusa": "#532938",
        "orchid": "#48446b",
        "zeta": "#c03535",
        "meg": "#2f718f",
        "marippe": "#e58238",
        "zooey": "#244b7d",
        "ilsa": "#7c5643",
        "tikoh": "#3d7a6e",
        "cupitan": "#3679a8",
        "cagliostro": "#c9688b",
        "vira": "#7a3272",
        "vampy": "#b82e56",
        "lyria": "#3a9fd8",
    }


def test_character_facts_are_split_by_heading(characters: CharacterConfig):
    characters.add(
        "hiori", "風野灯織", "sheet",
        facts="# 档案\n生日是2月27日。\n\n# 人物关系\n\n## 櫻木真乃\n同组合的伙伴。\n### 趣事\n一起去看鸟。\n",
    )

    assert load_characters(characters.path)["hiori"].facts == (
        Fact("档案", "档案\n生日是2月27日。"),
        Fact("人物关系 / 櫻木真乃", "人物关系 / 櫻木真乃\n同组合的伙伴。"),
        Fact("人物关系 / 櫻木真乃 / 趣事", "人物关系 / 櫻木真乃 / 趣事\n一起去看鸟。"),
    )


def test_text_before_any_heading_is_an_untitled_fact():
    assert parse_facts("生日是2月27日。\n\n# 档案\n身高155cm。") == (
        Fact(None, "生日是2月27日。"),
        Fact("档案", "档案\n身高155cm。"),
    )


def test_missing_character_sheet_is_reported_with_its_path(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", sheet=None)

    with pytest.raises(CharacterConfigError, match=r"sheets[/\\]mano\.md"):
        load_characters(config.path)


def test_duplicate_character_ids_are_rejected(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a").add("mano", "真乃", "b")

    with pytest.raises(CharacterConfigError, match="mano"):
        load_characters(config.path)


def test_character_missing_a_required_field_is_rejected(tmp_path: Path):
    config = CharacterConfig(tmp_path)
    config.write("characters.toml", '[[characters]]\nid = "mano"\nname = "櫻木真乃"\n')

    with pytest.raises(CharacterConfigError, match="intro、voice_id、sheet、color"):
        load_characters(config.path)


def test_character_id_must_be_safe_to_put_in_a_url(tmp_path: Path):
    config = CharacterConfig(tmp_path)
    config.write("characters.toml", '[[characters]]\nid = "Mano San"\nname = "a"\n'
                 'intro = ""\nvoice_id = "v"\nsheet = "s.md"\ncolor = "#ffbad6"\n')

    with pytest.raises(CharacterConfigError, match="Mano San"):
        load_characters(config.path)


def test_speakers_must_be_a_list_of_names(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    config.path.write_text(
        config.path.read_text(encoding="utf-8") + 'speakers = "真乃"\n', encoding="utf-8"
    )

    with pytest.raises(CharacterConfigError, match="speakers"):
        load_characters(config.path)


def test_two_characters_cannot_share_a_speaker_name(tmp_path: Path):
    config = (
        CharacterConfig(tmp_path)
        .add("mano", "櫻木真乃", "a", speakers=["真乃"])
        .add("mano2", "真乃", "b", speakers=["真乃"])
    )

    with pytest.raises(CharacterConfigError, match="真乃"):
        load_characters(config.path)


def test_missing_configuration_file_is_reported(tmp_path: Path):
    with pytest.raises(CharacterConfigError, match="characters.toml"):
        load_characters(tmp_path / "characters.toml")


@pytest.mark.parametrize("color", ["ffbad6", "#fff", "#ffbad", "#ffbad6ff", "#ggbad6", "pink", ""])
def test_image_colour_must_be_a_hex_rrggbb(tmp_path: Path, color: str):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a", color=color)

    with pytest.raises(CharacterConfigError, match="角色 mano 的 color.*#rrggbb"):
        load_characters(config.path)


def test_image_colour_is_read_in_lower_case(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a", color="#FFBAD6")

    assert load_characters(config.path)["mano"].color == "#ffbad6"


def test_missing_call_background_is_a_warning_and_treated_as_none(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    config.path.write_text(
        config.path.read_text(encoding="utf-8") + 'background = "backgrounds/mano.jpg"\n',
        encoding="utf-8",
    )

    with caplog.at_level(logging.WARNING, logger="eidolon.characters"):
        mano = load_characters(config.path)["mano"]

    assert mano.background is None
    assert "backgrounds" in caplog.text and "mano" in caplog.text


STAND_ASSETS = "https://stand.example/eidolon"


async def test_character_with_an_idol_and_a_default_outfit_has_a_stand_and_her_outfit_list_once_assets_are_served(
    make_client: ClientFactory, settings: Settings
):
    client = make_client(FakeLLM(), settings=replace(settings, stand_assets_url=STAND_ASSETS), user=None)

    listed = {c["id"]: c for c in (await client.get("/api/characters")).json()}

    assert listed["mano"]["stand"] == {
        "default_outfit": {
            "id": "stand/1030010010",
            "url": f"{STAND_ASSETS}/spine/idols/stand/1030010010/",
        },
        "outfits_url": f"{STAND_ASSETS}/outfits/1.json",
    }
    assert listed["kogane"]["stand"] is None  # no idol, no default outfit


@pytest.mark.parametrize(
    ("idol_id", "default_outfit"), [(1, None), (None, "stand_costume/1030010010")]
)
async def test_character_missing_her_idol_or_her_default_outfit_has_no_stand(
    make_client: ClientFactory,
    settings: Settings,
    characters: CharacterConfig,
    idol_id: int | None,
    default_outfit: str | None,
):
    characters.add("hiori", "風野灯織", "sheet", idol_id=idol_id, default_outfit=default_outfit)
    client = make_client(FakeLLM(), settings=replace(settings, stand_assets_url=STAND_ASSETS))

    listed = {c["id"]: c for c in (await client.get("/api/characters")).json()}

    assert listed["hiori"]["stand"] is None


def add_raw(config: CharacterConfig, line: str) -> None:
    config.path.write_text(config.path.read_text(encoding="utf-8") + line + "\n", encoding="utf-8")


@pytest.mark.parametrize("value", ['"1"', "0", "1.5", "true"])
def test_idol_id_must_be_a_positive_whole_number(tmp_path: Path, value: str):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    add_raw(config, f"idol_id = {value}")

    with pytest.raises(CharacterConfigError, match="角色 mano 的 idol_id"):
        load_characters(config.path)


@pytest.mark.parametrize(
    "value",
    [
        '"1030010010"',
        '"cb/1030010010"',
        '"stand/103001001"',
        '"stand/1030010010/"',
        '"spine/idols/stand/1030010010"',
        "1030010010",
    ],
)
def test_default_outfit_must_name_a_stand_outfit(tmp_path: Path, value: str):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    add_raw(config, f"default_outfit = {value}")

    with pytest.raises(CharacterConfigError, match="角色 mano 的 default_outfit.*stand/<enzaId>"):
        load_characters(config.path)


@pytest.mark.parametrize(
    ("field", "value"),
    [("name_zh", '"  "'), ("name_kana", "1"), ("name_romaji", '"Sakuragi\\rMano"')],
)
def test_other_names_must_each_be_a_line_of_text(tmp_path: Path, field: str, value: str):
    """Not configuring them at all is fine (the list test above)."""
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    add_raw(config, f"{field} = {value}")

    with pytest.raises(CharacterConfigError, match=f"角色 mano 的 {field}"):
        load_characters(config.path)


def test_repository_gives_each_idol_her_other_names():
    """Her reading is the world setting's reading of her name."""
    loaded = load_characters(REPO_CHARACTERS / "characters.toml")
    readings = {
        idol["name"]: idol["reading"]
        for idol in json.loads((REPO_CHARACTERS / "world.json").read_text(encoding="utf-8"))["idols"]
    }

    for c in loaded.values():
        assert c.name_zh and c.name_kana and c.name_romaji, c.id
        assert c.name_kana.replace(" ", "") == readings[c.name], c.id
        assert re.fullmatch(r"[A-Z][a-z]+(?: [A-Z][a-z]+)?", c.name_romaji), c.id


def test_repository_gives_each_idol_her_photo_tags():
    """Her character tag in lower case, and her looks with one eye colour among them."""
    loaded = load_characters(REPO_CHARACTERS / "characters.toml")

    for c in loaded.values():
        assert c.photo_tag and c.photo_appearance, c.id
        assert c.photo_tag == c.photo_tag.lower(), c.id
        looks = [tag.strip() for tag in c.photo_appearance.split(",")]
        eye_colours = [t for t in looks if t.endswith(" eyes") and not t.startswith("hair ")]
        assert len(eye_colours) == 1, c.id  # `hair between eyes` is how her bangs fall


def test_repository_gives_its_idols_their_idol_ids_and_default_outfits():
    loaded = load_characters(REPO_CHARACTERS / "characters.toml")

    assert len(loaded) >= 1
    for c in loaded.values():
        assert c.idol_id is None or isinstance(c.idol_id, int)


def _jpeg_size(path: Path) -> tuple[int, int]:
    """Width and height from a JPEG's start-of-frame segment, without an imaging library."""
    data = path.read_bytes()
    i = 2
    while i < len(data):
        marker, length = data[i + 1], int.from_bytes(data[i + 2 : i + 4])
        if 0xC0 <= marker <= 0xCF and marker not in (0xC4, 0xC8, 0xCC):
            return int.from_bytes(data[i + 7 : i + 9]), int.from_bytes(data[i + 5 : i + 7])
        i += 2 + length
    raise ValueError(f"{path} has no start-of-frame segment")


def test_repository_avatars_are_shrunk_to_what_the_screens_show():
    """Shown at 112px at most, so 224px for high-density screens (characters.toml). The list
    filter loads every one of them; most 400px originals were 100–160 KB, a few about 30 KB,
    so the size alone wouldn't catch one being put back."""
    loaded = load_characters(REPO_CHARACTERS / "characters.toml")

    too_big = {}
    for id, c in loaded.items():
        for field, avatar in (("avatar", c.avatar), ("scsp_avatar", c.scsp_avatar)):
            if avatar is None:
                continue
            width, height = _jpeg_size(avatar)
            size = avatar.stat().st_size
            if width > 224 or height > 224 or size > 32 * 1024:
                too_big[id, field] = (width, height, size)
    assert too_big == {}


def test_stand_assets_url_is_read_without_its_trailing_slash(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("EIDOLON_STAND_ASSETS_URL", raising=False)
    assert stand_assets_url_from_env() is None

    monkeypatch.setenv("EIDOLON_STAND_ASSETS_URL", " https://stand.example/eidolon/ ")
    assert stand_assets_url_from_env() == "https://stand.example/eidolon"

    monkeypatch.setenv("EIDOLON_STAND_ASSETS_URL", "http://localhost:8765")
    assert stand_assets_url_from_env() == "http://localhost:8765"


@pytest.mark.parametrize("value", ["stand.example/eidolon", "/stand", "ftp://stand.example"])
def test_stand_assets_url_must_be_a_web_address(monkeypatch: pytest.MonkeyPatch, value: str):
    monkeypatch.setenv("EIDOLON_STAND_ASSETS_URL", value)

    with pytest.raises(RuntimeError, match="EIDOLON_STAND_ASSETS_URL"):
        stand_assets_url_from_env()


MANO_GREETING = ("[softly] ほわっ……はじめまして、櫻木真乃です", "……初次见面，我是櫻木真乃")


def mano_with_greeting(
    characters: CharacterConfig,
    greeting: tuple[str, str] = MANO_GREETING,
    voice_id: str = "mano-voice",
) -> None:
    """Rewrite the configuration with Mano alone, greeting as given."""
    CharacterConfig(characters.directory).add(
        "mano", "櫻木真乃", MANO_SHEET, voice_id=voice_id, greeting=greeting
    )


async def listed_greeting(
    make_client: ClientFactory, settings: Settings, assets: str | None = STAND_ASSETS
) -> dict:
    client = make_client(FakeLLM(), settings=replace(settings, stand_assets_url=assets), user=None)
    listed = {c["id"]: c for c in (await client.get("/api/characters")).json()}
    return listed["mano"]["greeting"]


async def test_greeting_is_shown_without_its_delivery_cues_with_its_subtitle_and_where_to_hear_it(
    make_client: ClientFactory, settings: Settings, characters: CharacterConfig
):
    mano_with_greeting(characters)

    greeting = await listed_greeting(make_client, settings)

    assert greeting["ja"] == "ほわっ……はじめまして、櫻木真乃です"
    assert greeting["subtitle"] == "……初次见面，我是櫻木真乃"
    assert re.fullmatch(rf"{re.escape(STAND_ASSETS)}/greetings/mano-[0-9a-f]+\.mp3", greeting["audio_url"])


async def test_greeting_has_no_audio_unless_the_stand_assets_are_served(
    make_client: ClientFactory, settings: Settings, characters: CharacterConfig
):
    mano_with_greeting(characters)

    greeting = await listed_greeting(make_client, settings, assets=None)

    assert greeting == {
        "ja": "ほわっ……はじめまして、櫻木真乃です",
        "subtitle": "……初次见面，我是櫻木真乃",
        "audio_url": None,
    }


async def test_greeting_audio_moves_when_its_words_or_her_voice_change_but_not_its_subtitle(
    make_client: ClientFactory, settings: Settings, characters: CharacterConfig
):
    """The address changes with what she says, cues and all, and in what voice, so a
    browser never plays an old one from its cache."""
    mano_with_greeting(characters)
    first = (await listed_greeting(make_client, settings))["audio_url"]
    mano_with_greeting(characters, (MANO_GREETING[0], "初次见面"))
    resubtitled = (await listed_greeting(make_client, settings))["audio_url"]
    mano_with_greeting(characters, ("[happily] ほわっ……はじめまして、櫻木真乃です", MANO_GREETING[1]))
    recued = (await listed_greeting(make_client, settings))["audio_url"]
    mano_with_greeting(characters, voice_id="another-voice")
    revoiced = (await listed_greeting(make_client, settings))["audio_url"]

    assert resubtitled == first
    assert len({first, recued, revoiced}) == 3


async def test_greeting_of_a_character_without_a_voice_has_no_audio(
    make_client: ClientFactory, settings: Settings, characters: CharacterConfig
):
    mano_with_greeting(characters, voice_id="")

    greeting = await listed_greeting(make_client, settings)

    assert greeting["ja"] == "ほわっ……はじめまして、櫻木真乃です"
    assert greeting["audio_url"] is None


@pytest.mark.parametrize(
    "lines",
    [
        'greeting = "はじめまして"',
        'greeting_subtitle = "初次见面"',
        'greeting = "[softly]"\ngreeting_subtitle = "初次见面"',
    ],
)
def test_greeting_needs_both_its_words_and_its_subtitle(tmp_path: Path, lines: str):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    add_raw(config, lines)

    with pytest.raises(CharacterConfigError, match="角色 mano 的招呼"):
        load_characters(config.path)


def test_greeting_is_optional(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")

    assert load_characters(config.path)["mano"].greeting is None


MANO_CALL_OPENER = (
    "[shyly] あっ、もしもし……真乃です。えっと、今、お電話だいじょうぶですか？",
    "啊，喂……我是真乃。那个，现在方便接电话吗？",
)


@pytest.mark.parametrize(
    "lines",
    [
        'call_opener = "もしもし"',
        'call_opener_subtitle = "喂"',
        'call_opener = "[shyly]"\ncall_opener_subtitle = "喂"',
    ],
)
def test_call_opener_needs_both_its_words_and_its_subtitle(tmp_path: Path, lines: str):
    """As her greeting does, and said the same way."""
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")
    add_raw(config, lines)

    with pytest.raises(CharacterConfigError, match="角色 mano 的开场白"):
        load_characters(config.path)


def test_call_opener_is_optional(tmp_path: Path):
    config = CharacterConfig(tmp_path).add("mano", "櫻木真乃", "a")

    assert load_characters(config.path)["mano"].call_opener is None


def test_call_opener_is_seen_without_its_delivery_cues_apart_from_her_greeting(tmp_path: Path):
    config = CharacterConfig(tmp_path).add(
        "mano", "櫻木真乃", "a", greeting=MANO_GREETING, call_opener=MANO_CALL_OPENER
    )

    mano = load_characters(config.path)["mano"]

    assert mano.call_opener is not None and mano.greeting is not None
    assert mano.call_opener.ja == "あっ、もしもし……真乃です。えっと、今、お電話だいじょうぶですか？"
    assert mano.call_opener.subtitle == MANO_CALL_OPENER[1]
    assert mano.greeting.ja == "ほわっ……はじめまして、櫻木真乃です"


async def listed_call_opener(
    make_client: ClientFactory, settings: Settings, assets: str | None = STAND_ASSETS
) -> dict:
    client = make_client(FakeLLM(), settings=replace(settings, stand_assets_url=assets), user=None)
    listed = {c["id"]: c for c in (await client.get("/api/characters")).json()}
    return listed["mano"]["call_opener"]


async def test_call_opener_is_listed_without_its_delivery_cues_with_its_subtitle_and_where_to_hear_it(
    make_client: ClientFactory, settings: Settings, characters: CharacterConfig
):
    CharacterConfig(characters.directory).add(
        "mano", "櫻木真乃", MANO_SHEET, voice_id="mano-voice", greeting=MANO_GREETING, call_opener=MANO_CALL_OPENER
    )

    opener = await listed_call_opener(make_client, settings)

    assert opener["ja"] == "あっ、もしもし……真乃です。えっと、今、お電話だいじょうぶですか？"
    assert opener["subtitle"] == "啊，喂……我是真乃。那个，现在方便接电话吗？"
    assert re.fullmatch(rf"{re.escape(STAND_ASSETS)}/call-openers/mano-[0-9a-f]+\.mp3", opener["audio_url"])
    greeting = await listed_greeting(make_client, settings)
    assert greeting["audio_url"] != opener["audio_url"]


async def test_call_opener_has_no_audio_unless_the_stand_assets_are_served(
    make_client: ClientFactory, settings: Settings, characters: CharacterConfig
):
    CharacterConfig(characters.directory).add(
        "mano", "櫻木真乃", MANO_SHEET, voice_id="mano-voice", call_opener=MANO_CALL_OPENER
    )

    opener = await listed_call_opener(make_client, settings, assets=None)

    assert opener == {
        "ja": "あっ、もしもし……真乃です。えっと、今、お電話だいじょうぶですか？",
        "subtitle": "啊，喂……我是真乃。那个，现在方便接电话吗？",
        "audio_url": None,
    }
    assert (await listed_greeting(make_client, settings)) is None


async def test_call_poster_and_voxels_are_where_the_bucket_keeps_them(make_client: ClientFactory, settings: Settings):
    """Her card on the landing page's incoming call and her voxel figure in its act about
    memory, both put in the bucket by hand: listed without asking the bucket whether they are
    there (the page falls back to her colour)."""
    client = make_client(FakeLLM(), settings=replace(settings, stand_assets_url=STAND_ASSETS), user=None)

    listed = (await client.get("/api/characters")).json()

    assert {c["id"]: (c["call_poster_url"], c["voxels_url"]) for c in listed} == {
        "mano": (f"{STAND_ASSETS}/call-posters/mano.webp", f"{STAND_ASSETS}/landing-voxels/mano.json"),
        "kogane": (f"{STAND_ASSETS}/call-posters/kogane.webp", f"{STAND_ASSETS}/landing-voxels/kogane.json"),
    }


async def test_landing_memory_still_is_where_the_bucket_keeps_it(make_client: ClientFactory, settings: Settings):
    """The landing page's act about memory as one picture, for visitors who see no animation:
    put in the bucket by hand and listed as her call poster is, without asking the bucket."""
    served = make_client(FakeLLM(), settings=replace(settings, stand_assets_url=STAND_ASSETS), user=None)
    unserved = make_client(FakeLLM(), user=None)

    assert (await served.get("/api/landing")).json() == {"memory_still_url": f"{STAND_ASSETS}/landing-memory/still.webp"}
    assert (await unserved.get("/api/landing")).json() == {"memory_still_url": None}


async def test_local_sound_endpoint_and_greeting_fallback(make_client: ClientFactory, characters: CharacterConfig):
    """When a character has a local sound file, her greeting falls back to it when no bucket is configured."""
    CharacterConfig(characters.directory).add(
        "nier", "ニーア", MANO_SHEET, voice_id="nier-voice", greeting=MANO_GREETING
    )
    client = make_client(FakeLLM(), user=None)
    listed = {c["id"]: c for c in (await client.get("/api/characters")).json()}
    # nier has frontend/public/sounds/gbf/nier_greeting.mp3
    assert listed["nier"]["greeting"]["audio_url"] == "/sounds/gbf/nier_greeting.mp3"

    res = await client.get("/sounds/gbf/nier_greeting.mp3")
    assert res.status_code == 200
    assert res.headers["content-type"] == "audio/mpeg"
