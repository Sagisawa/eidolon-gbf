"""名单：world sync 的导入把来源里写的名字对应到世界设定里的谁。

由世界设定里的偶像、组合、社长和事务员构造，回答三件事：一个人名（可以附带声优名）
是哪位偶像，一个名字或读音是哪个组合，一个人是不是社长或事务员。从各自的来源里把
人名、声优名抽出来，由各导入自己做；怎么比，只在这里定一次：

- 人名和声优名：NFKC，去掉空白，去掉末尾「（初代）」这类尾注；
- 组合的名字和读音：NFKC，`’` 换成 `'`，片假名换成平假名，去掉非文字字符，casefold。
"""

import re
import unicodedata
from collections.abc import Iterable

from eidolon.sync_tools import hiragana, without_spaces
from eidolon.world import Idol, Staff, Unit

_NOTE = re.compile(r"\([^()]*\)$")
"""NFKC 之后名字末尾的尾注：三峰結華（初代）。"""


def person_key(name: str) -> str:
    """比对用的人名或声优名：`三峰 結華（初代）` 就是 `三峰結華`。"""
    return _NOTE.sub("", without_spaces(unicodedata.normalize("NFKC", name)))


def unit_key(name: str) -> str:
    """比对用的组合名或读音：`L’Antica` 是 `l'antica`，`illumination STARS` 是
    `illuminationstars`，`イルミネーションスターズ` 是 `いるみねーしょんすたーず`。"""
    text = hiragana(unicodedata.normalize("NFKC", name).replace("’", "'"))
    return re.sub(r"[\W_]", "", text).casefold()


class Roster:
    def __init__(
        self, idols: Iterable[Idol], units: Iterable[Unit], staff: Iterable[Staff] = ()
    ) -> None:
        idols, units = list(idols), tuple(units)
        self.idols = tuple(idol.name for idol in idols)
        """偶像的名字，按世界设定里的顺序。"""
        self.units = units
        self._by_name = {person_key(idol.name): idol.name for idol in idols}
        self._by_cv = {person_key(idol.cv): idol.name for idol in idols if idol.cv}
        self._units: dict[str, Unit] = {}
        for unit in units:
            for name in (unit.name, unit.reading):
                if name and unit_key(name):
                    self._units.setdefault(unit_key(name), unit)
        self._staff = {person_key(s.name) for s in staff}

    def idol(self, name: str | None, cv: str | None = None) -> str | None:
        """叫 `name` 的偶像；名字对不上时，是声优叫 `cv` 的那位；都对不上就是 None。"""
        if name and (idol := self._by_name.get(person_key(name))):
            return idol
        return self._by_cv.get(person_key(cv)) if cv else None

    def unit(self, name: str) -> Unit | None:
        """名字或读音是 `name` 的组合；特别组合不是组合。"""
        return self._units.get(key) if (key := unit_key(name)) else None

    def is_staff(self, name: str) -> bool:
        """`name` 是不是社长或事务员。"""
        return person_key(name) in self._staff
