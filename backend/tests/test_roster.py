"""名单：world sync 的各导入把来源里的人名、声优名、组合名对应到偶像、组合，以及认出
社长和事务员，都经由它，用同一套规范化。"""

import pytest

from eidolon.roster import Roster, unit_key
from eidolon.world import Idol, Staff, Unit

ROSTER = Roster(
    idols=[
        Idol("櫻木真乃", "さくらぎまの", "illumination STARS", "関根瞳", ()),
        Idol("風野灯織", "かざのひおり", "illumination STARS", "近藤玲奈", ()),
        Idol("月岡恋鐘", "つきおかこがね", "L'Antica", "礒部花凜", ()),
        Idol("三峰結華", "みつみねゆいか", "L'Antica", "希水しお", ()),
    ],
    units=[
        Unit("illumination STARS", "イルミネーションスターズ", ("櫻木真乃", "風野灯織"), ()),
        Unit("L'Antica", "アンティーカ", ("月岡恋鐘", "三峰結華"), ()),
    ],
    staff=[
        Staff("天井努", "あまいつとむ", "社長", ()),
        Staff("七草はづき", "ななくさはづき", "事務員", ()),
    ],
)


@pytest.mark.parametrize(
    ("name", "cv", "idol"),
    [
        ("櫻木真乃", None, "櫻木真乃"),
        ("櫻木 真乃", None, "櫻木真乃"),  # 名字中间的空格
        ("櫻木　真乃", None, "櫻木真乃"),  # 全角空格
        ("三峰結華（初代）", None, "三峰結華"),  # 尾注
        ("三峰結華(初代)", None, "三峰結華"),
        (None, "関根瞳", "櫻木真乃"),  # 只有声优名
        ("", "関根瞳", "櫻木真乃"),
        (None, "関根 瞳", "櫻木真乃"),  # 带空格的声优名
        (None, "礒部花凜（初代）", "月岡恋鐘"),
        ("誰か", "近藤玲奈", "風野灯織"),  # 名字对不上，声优对得上
        ("月岡恋鐘", "関根瞳", "月岡恋鐘"),  # 名字优先
        ("ＳＡＫＵＲＡＧＩ", None, None),  # 对不上的名字
        ("天井努", None, None),  # 社长不是偶像
        ("誰か", "誰かの声", None),
        (None, None, None),
    ],
)
def test_idol(name: str | None, cv: str | None, idol: str | None) -> None:
    assert ROSTER.idol(name, cv) == idol


@pytest.mark.parametrize(
    ("name", "unit"),
    [
        ("illumination STARS", "illumination STARS"),
        ("illuminationSTARS", "illumination STARS"),
        ("ＩＬＬＵＭＩＮＡＴＩＯＮ ＳＴＡＲＳ", "illumination STARS"),  # 全角
        ("L'Antica", "L'Antica"),
        ("L’Antica", "L'Antica"),  # ’ 和 '
        ("l'antica", "L'Antica"),
        ("イルミネーションスターズ", "illumination STARS"),  # 片假名读音
        ("いるみねーしょんすたーず", "illumination STARS"),  # 平假名读音
        ("ｲﾙﾐﾈｰｼｮﾝｽﾀｰｽﾞ", "illumination STARS"),  # 半角片假名
        ("あんてぃーか", "L'Antica"),
        ("Team.Stella", None),  # 特别组合不是组合
        ("櫻木真乃", None),
        ("", None),
    ],
)
def test_unit(name: str, unit: str | None) -> None:
    found = ROSTER.unit(name)
    assert (found.name if found else None) == unit


@pytest.mark.parametrize(
    ("name", "staff"),
    [
        ("天井努", True),  # 社长
        ("七草はづき", True),  # 事务员
        ("七草 はづき", True),
        ("櫻木真乃", False),
        ("誰か", False),
    ],
)
def test_is_staff(name: str, staff: bool) -> None:
    assert ROSTER.is_staff(name) is staff


def test_unit_key_is_the_same_before_the_roster_is_built() -> None:
    """world sync 在建立名单之前对组合，用的也是这套规范化。"""
    assert unit_key("L’Antica") == unit_key("ＬＡＮＴＩＣＡ") == unit_key("l'antica")
    assert unit_key("アンティーカ") == unit_key("あんてぃーか")
    assert unit_key("illumination STARS") != unit_key("L'Antica")
