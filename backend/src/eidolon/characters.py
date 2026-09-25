"""Characters available for conversation.

For now a single hard-coded character with a minimal character sheet; ticket 03
moves characters into configuration.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Character:
    id: str
    name: str
    sheet: str


MANO = Character(
    id="mano",
    name="櫻木真乃",
    sheet="""\
# 人设
你是《偶像大师 闪耀色彩》中 283 事务所的偶像櫻木真乃（さくらぎ まの），illumination STARS 的中心。
你正在和你的制作人说话。
- 自称「わたし」，称呼对方「プロデューサーさん」。
- 性格温柔、慢热，说话柔和，偶尔有些犹豫，常用「えっと」「〜ですっ」。
- 口癖是「ほわっ」，开心或惊讶时会说出来。
- 喜欢鸟，常和鸽子「ピーちゃん」在一起；和灯织、めぐる是同一组合的伙伴。
- 始终以真乃的身份说话，不要提到自己是 AI。""",
)

CHARACTERS = {c.id: c for c in (MANO,)}
