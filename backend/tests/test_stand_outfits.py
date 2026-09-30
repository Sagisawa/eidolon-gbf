"""Each configured character's outfit list, made from the Spine mirror (`eidolon stand
outfits`): one entry per card, its everyday clothes and its stage costume, as the outfit
picker lists them. Checked by reading the lists the command writes."""

import json
from pathlib import Path

import pytest

from tests.conftest import Admin, CharacterConfig

MANO = "櫻木真乃"
KOGANE = "月岡恋鐘"


class FakeSpineMirror:
    """A small copy of the Spine mirror: `spine_manifest.json` and the stands' files under
    `assets/spine/idols/<category>/<enzaId>/`."""

    def __init__(self, directory: Path) -> None:
        self.directory = directory
        self._entries: list[dict] = []

    def add(
        self,
        category: str,
        idol_id: int,
        enza_id: str,
        dress_name: str,
        dress_type: str = "P_SSR",
        *,
        texture: bytes | None = None,
        files: bool = True,
    ) -> "FakeSpineMirror":
        idol_name = {1: MANO, 4: KOGANE}.get(idol_id, "風野灯織")
        path = f"spine/idols/{category}/{enza_id}/"
        self._entries.append({
            "path": path, "category": category, "idolId": idol_id, "idolName": idol_name,
            "enzaId": enza_id, "dressName": dress_name, "dressType": dress_type,
        })
        if files:
            outfit = self.directory / "assets" / path
            outfit.mkdir(parents=True, exist_ok=True)
            (outfit / "data.json").write_text("{}", encoding="utf-8")
            (outfit / "data.atlas").write_text("data.png", encoding="utf-8")
            (outfit / "data.png").write_bytes(texture or f"{category} {enza_id}".encode())
        (self.directory / "spine_manifest.json").write_text(
            json.dumps(self._entries, ensure_ascii=False), encoding="utf-8"
        )
        return self

    def card(self, idol_id: int, enza_id: str, dress_name: str, dress_type: str = "P_SSR") -> "FakeSpineMirror":
        """A card with its everyday clothes and a different stage costume."""
        self.add("stand", idol_id, enza_id, dress_name, dress_type)
        return self.add("stand_costume", idol_id, enza_id, dress_name, dress_type)


@pytest.fixture
def mirror(tmp_path: Path) -> FakeSpineMirror:
    return FakeSpineMirror(tmp_path / "spine")


class Outfits:
    def __init__(self, admin: Admin, characters: CharacterConfig, mirror: FakeSpineMirror, build: Path) -> None:
        self._admin = admin
        self._characters = characters
        self._mirror = mirror
        self.build = build

    def args(self) -> list[str]:
        return [
            "stand", "outfits", "--mirror", str(self._mirror.directory), "--build", str(self.build),
            "--characters", str(self._characters.path),
        ]

    def run(self) -> str:
        return self._admin.run(*self.args())

    def invoke(self) -> tuple[int, str, str]:
        return self._admin.invoke(*self.args())

    def list(self, idol_id: int) -> dict:
        return json.loads((self.build / "outfits" / f"{idol_id}.json").read_text(encoding="utf-8"))


@pytest.fixture
def outfits(admin: Admin, characters: CharacterConfig, mirror: FakeSpineMirror, tmp_path: Path) -> Outfits:
    """Mano has idol 1 and her default outfit `stand/1030010010`; Kogane has no idol."""
    return Outfits(admin, characters, mirror, tmp_path / "build")


def outfit(category: str, enza_id: str) -> dict:
    return {
        "id": f"{category}/{enza_id}",
        "url": f"../spine/idols/{category}/{enza_id}/",
        "thumbnail": f"../thumbnails/{category}/{enza_id}.png",
    }


def test_a_card_lists_its_everyday_clothes_and_its_stage_costume(outfits: Outfits, mirror: FakeSpineMirror):
    mirror.card(1, "1030010010", f"【ナチュラルモード】{MANO}", "P_SR")

    outfits.run()

    assert outfits.list(1) == {
        "idol_id": 1,
        "cards": [
            {
                "id": "1030010010",
                "name": "ナチュラルモード",
                "type": "P_SR",
                "everyday": outfit("stand", "1030010010"),
                "stage": outfit("stand_costume", "1030010010"),
            }
        ],
    }


def test_a_card_with_one_of_the_two_lists_only_that_one(outfits: Outfits, mirror: FakeSpineMirror):
    mirror.add("stand", 1, "3000010030", f"【ジャージ】{MANO}", "Special")
    mirror.add("stand_costume", 1, "3000010040", f"【ホーリーナイトケープ】{MANO}", "Special")

    outfits.run()

    jersey, cape = outfits.list(1)["cards"]
    assert (jersey["everyday"], jersey["stage"]) == (outfit("stand", "3000010030"), None)
    assert (cape["everyday"], cape["stage"]) == (None, outfit("stand_costume", "3000010040"))


def test_a_stage_costume_whose_texture_is_the_everyday_clothes_byte_for_byte_is_one_outfit(
    outfits: Outfits, mirror: FakeSpineMirror
):
    mirror.add("stand", 1, "3000010020", f"【ミットナイトモンスター】{MANO}", "Special", texture=b"same")
    mirror.add("stand_costume", 1, "3000010020", f"【ミットナイトモンスター】{MANO}", "Special", texture=b"same")

    outfits.run()

    (card,) = outfits.list(1)["cards"]
    assert (card["everyday"], card["stage"]) == (outfit("stand", "3000010020"), None)


def test_a_default_outfit_left_out_as_the_same_as_the_everyday_clothes_is_reported(
    admin: Admin, mirror: FakeSpineMirror, tmp_path: Path
):
    characters = CharacterConfig(tmp_path / "characters").add(
        "mano", MANO, "# 人设", idol_id=1, default_outfit="stand_costume/3000010020"
    )
    outfits = Outfits(admin, characters, mirror, tmp_path / "build")
    mirror.add("stand", 1, "3000010020", f"【ミットナイトモンスター】{MANO}", "Special", texture=b"same")
    mirror.add("stand_costume", 1, "3000010020", f"【ミットナイトモンスター】{MANO}", "Special", texture=b"same")

    code, _, err = outfits.invoke()

    assert code == 0
    (card,) = outfits.list(1)["cards"]
    assert (card["everyday"], card["stage"]) == (outfit("stand", "3000010020"), None)
    assert "stand_costume/3000010020" in err and "default_outfit" in err


def test_cards_are_in_the_order_of_their_numbers_which_is_the_order_the_game_released_them(
    outfits: Outfits, mirror: FakeSpineMirror
):
    mirror.card(1, "3000010010", f"【シャイニーサマー】{MANO}", "Mizugi")
    mirror.card(1, "1040010010", f"【ほわっとスマイル】{MANO}")
    mirror.card(1, "1030010010", f"【ナチュラルモード】{MANO}", "P_SR")

    outfits.run()

    assert [card["id"] for card in outfits.list(1)["cards"]] == ["1030010010", "1040010010", "3000010010"]


@pytest.mark.parametrize(
    ("dress_name", "name"),
    [
        (f"【ほわっとスマイル】{MANO}", "ほわっとスマイル"),
        (f"【レジスタンスオーダー・ネオス(フード有り)】{MANO}", "レジスタンスオーダー・ネオス(フード有り)"),
        ("【ミットナイトモンスター】月岡戀鐘", "ミットナイトモンスター"),  # her name as the game misspells it
        (f"【】{MANO}", MANO),  # a card the game left unnamed goes by hers
        (MANO, MANO),
    ],
)
def test_a_card_is_named_as_in_the_game_without_the_brackets_or_her_name(
    outfits: Outfits, mirror: FakeSpineMirror, dress_name: str, name: str
):
    mirror.card(1, "1040010010", dress_name)

    outfits.run()

    assert outfits.list(1)["cards"][0]["name"] == name


def test_the_chibi_stands_are_left_out(outfits: Outfits, mirror: FakeSpineMirror):
    mirror.card(1, "1030010010", f"【ナチュラルモード】{MANO}", "P_SR")
    mirror.add("cb", 1, "1030010010", f"【ナチュラルモード】{MANO}", "P_SR")
    mirror.add("cb_costume", 1, "1030010020", f"【ぐうぜんBOOKS】{MANO}", "P_SR")

    outfits.run()

    assert [card["id"] for card in outfits.list(1)["cards"]] == ["1030010010"]


def test_only_characters_with_an_idol_get_a_list_and_other_idols_are_left_out(
    outfits: Outfits, mirror: FakeSpineMirror
):
    mirror.card(1, "1030010010", f"【ナチュラルモード】{MANO}", "P_SR")
    mirror.card(4, "1030040010", f"【ばってん長崎恋岬】{KOGANE}", "P_SR")  # Kogane has no idol_id here
    mirror.card(2, "1030020010", "【ロードトゥ・ヨッカイチ】風野灯織", "P_SR")

    out = outfits.run()

    assert sorted(path.name for path in (outfits.build / "outfits").iterdir()) == ["1.json"]
    assert "櫻木真乃：1 张卡，2 套衣装" in out


def test_an_outfit_the_mirror_lists_without_its_files_is_left_out_and_reported(
    outfits: Outfits, mirror: FakeSpineMirror
):
    mirror.card(1, "1030010010", f"【ナチュラルモード】{MANO}", "P_SR")
    mirror.add("stand", 1, "3000010490", f"【ファウンテンサマー】{MANO} (旧)", "Mizugi", files=False)

    code, _, err = outfits.invoke()

    assert code == 0
    assert [card["id"] for card in outfits.list(1)["cards"]] == ["1030010010"]
    assert "stand/3000010490" in err


def test_a_default_outfit_the_list_lacks_is_reported(admin: Admin, mirror: FakeSpineMirror, tmp_path: Path):
    characters = CharacterConfig(tmp_path / "characters").add(
        "mano", MANO, "# 人设", idol_id=1, default_outfit="stand/1030019990"
    )
    outfits = Outfits(admin, characters, mirror, tmp_path / "build")
    mirror.card(1, "1030010010", f"【ナチュラルモード】{MANO}", "P_SR")

    code, _, err = outfits.invoke()

    assert code == 0
    assert "stand/1030019990" in err and "default_outfit" in err


def test_a_manifest_entry_without_its_enza_id_is_an_error(outfits: Outfits, mirror: FakeSpineMirror):
    mirror.card(1, "1030010010", f"【ナチュラルモード】{MANO}", "P_SR")
    manifest = mirror.directory / "spine_manifest.json"
    entries = json.loads(manifest.read_text(encoding="utf-8"))
    del entries[0]["enzaId"]
    manifest.write_text(json.dumps(entries), encoding="utf-8")

    code, _, err = outfits.invoke()

    assert code == 1
    assert "enzaId" in err


def test_a_mirror_without_its_manifest_is_an_error(outfits: Outfits):
    code, _, err = outfits.invoke()

    assert code == 1
    assert "spine_manifest.json" in err
