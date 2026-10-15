"""The structured reply format and its streaming parser (ADR-0001).

The chat model answers in segments, each a Japanese line followed by its Chinese
subtitle:

    <ja>こんにちは、プロデューサーさん！</ja><zh>你好，制作人！</zh>

The parser turns a stream of arbitrary text chunks into per-segment deltas as soon
as they arrive, so Japanese text can reach TTS before the reply is finished. It also
says when each segment is complete: once its subtitle closes, the next segment opens
(the model skipped the subtitle), or the stream ends. The segments keep what the model
wrote; the deltas show it without delivery cues, and the Japanese is voiced with them
(see `delivery_cues`).
"""

from dataclasses import dataclass, field
from typing import Literal

from eidolon.delivery_cues import CueFilter

Lang = Literal["ja", "zh"]

FORMAT_INSTRUCTIONS = """\
# 回复格式
无论用户用中文还是日语说话，你都只用日语回答，并给每句日语附上中文字幕。
把回复分成段，每段先写日语原文，紧接着写这段的中文字幕，格式如下：
<ja>日语原文</ja><zh>中文字幕</zh>
除了这些标签和标签里的内容，不要输出任何其他文字。

# 说话长度
像真人当面说话那样：接对方一句话，通常只回一两句。
- 平时只写一到两段，每段只有一句简短的口语。不写长句，不要把几件事塞进一段，也不要用「首先……其次……」这种条理分明的说法。
- 被要求讲一段事情时（包括回忆过去的事），可以多说几句，但最多四段左右；讲到自然的停顿处就停下，剩下的等对方追问再讲，不要一口气讲完。
- 不必每次都用提问收尾，话说完了自然停下就好。
- 对方一次问了几件事，每件都用一句话简短回应，不要漏掉，这时可以超过两段。
- 话多话少、怎么说仍以人设为准；这里只管一次说多少。

# 情绪与语气提示
让情绪自然地流露在日语的措辞里：感叹词、语气词、停顿、口语化的说法。但口吻和口癖始终以人设为准，不要为了显得有情绪而夸张。
通话时日语原文会被念出来。情绪明显的段，可以在日语原文里加上语气提示，告诉配音这里该怎么念：用方括号括起简短的英文描述，放在段首管整段，放在句中管它后面的部分。平常说话、交代事情的段不加，一次回复里通常只有一两段需要。例如：
<ja>[shyly] え、えっと……ありがとう。</ja><zh>那、那个……谢谢。</zh><ja>明日は十時に集合だよね。</ja><zh>明天是十点集合对吧。</zh>
<ja>そっか……[disappointed] 行けないんだ。</ja><zh>这样啊……去不了了啊。</zh>
常用的有 [happily] [excitedly] [shyly] [embarrassed] [sadly] [disappointed] [sulking] [angrily] [worried] [surprised] [gently] [teasing] [whispering] [laughing] [sleepy]，也可以自由描述，例如 [laughing nervously]，但不要超过四个英文单词。
- 每段最多两个语气提示；拿不准要不要加时就不加。
- 语气提示只写在 <ja> 里；<zh> 只翻译台词，不带语气提示。
- 只用方括号加英文，不要用圆括号、方头括号或其他括号，也不要用日语或中文写提示。"""


@dataclass(frozen=True)
class SegmentDelta:
    segment: int
    lang: Lang
    text: str
    type: Literal["delta"] = field(default="delta", init=False)


@dataclass(frozen=True)
class SegmentComplete:
    """Segment `segment` has all it will get. Stays on the server: a call needs to know
    when a reply has a complete segment, the browser does not."""

    segment: int
    type: Literal["segment-complete"] = field(default="segment-complete", init=False)


@dataclass(frozen=True)
class SpeechDelta:
    """More of segment `segment`'s Japanese to voice, sent along with the `SegmentDelta`
    that shows it: the same words, but with their delivery cues. Stays on the server."""

    segment: int
    text: str
    type: Literal["speech-delta"] = field(default="speech-delta", init=False)


ParserEvent = SegmentDelta | SpeechDelta | SegmentComplete


@dataclass
class Segment:
    ja: str = ""
    zh: str = ""


@dataclass
class ReplyParser:
    segments: list[Segment] = field(default_factory=list)
    _buffer: str = ""
    _inside: Lang | None = None
    _stray: str = ""
    _said_complete: int = 0  # how many segments are known to be complete
    _line: CueFilter = field(default_factory=CueFilter)  # the open tag's content
    _events: list[ParserEvent] = field(default_factory=list)

    @property
    def complete(self) -> list[Segment]:
        """The segments said to be complete so far, leaving out any half-written one."""
        return self.segments[: self._said_complete]

    def feed(self, chunk: str) -> list[ParserEvent]:
        self._buffer += chunk
        while True:
            if self._inside is None:
                if not self._open_next_tag():
                    return self._hand_over()
            else:
                closed = self._take_content(self._inside)
                if not closed:
                    return self._hand_over()
                self._end_line(self._inside)
                if self._inside == "zh":
                    self._complete_up_to(len(self.segments))
                self._inside = None

    def finish(self) -> list[ParserEvent]:
        """Flush what is left at the end of a stream; the parser can then go on with the
        next stream of the same reply. A reply that ignored the format becomes one
        Japanese segment."""
        if self._inside is not None:
            keep = _partial_suffix(self._buffer, (f"</{self._inside}>",))
            text = self._buffer[: len(self._buffer) - keep]
            if text:
                self._append(self._inside, text)
            self._end_line(self._inside)
        elif not self.segments and (self._stray + self._buffer).strip():
            self._append("ja", (self._stray + self._buffer).strip())
            self._end_line("ja")
        self._buffer, self._inside, self._stray = "", None, ""
        self._complete_up_to(len(self.segments))
        return self._hand_over()

    def _open_next_tag(self) -> bool:
        langs: tuple[Lang, ...] = ("ja", "zh")
        starts: list[tuple[int, Lang]] = [(i, lang) for lang in langs if (i := self._buffer.find(f"<{lang}>")) >= 0]
        if not starts:
            keep = _partial_suffix(self._buffer, ("<ja>", "<zh>"))
            self._stray += self._buffer[: len(self._buffer) - keep]
            self._buffer = self._buffer[len(self._buffer) - keep :]
            return False
        start, lang = min(starts)
        self._stray += self._buffer[:start]
        self._buffer = self._buffer[start + len(f"<{lang}>") :]
        if lang == "ja" or not self.segments or self.segments[-1].zh:
            self._complete_up_to(len(self.segments))
            self.segments.append(Segment())
        self._inside = lang
        self._line = CueFilter()
        return True

    def _take_content(self, lang: Lang) -> bool:
        """Take what there is of the open tag's content; True if the tag closed."""
        close = f"</{lang}>"
        end = self._buffer.find(close)
        closed = end >= 0
        if not closed:
            end = len(self._buffer) - _partial_suffix(self._buffer, (close,))
        text = self._buffer[:end]
        self._buffer = self._buffer[end + len(close) :] if closed else self._buffer[end:]
        if text:
            self._append(lang, text)
        return closed

    def _append(self, lang: Lang, text: str) -> None:
        if not self.segments:
            self.segments.append(Segment())
        segment = self.segments[-1]
        setattr(segment, lang, getattr(segment, lang) + text)
        self._show(lang, *self._line.feed(text))

    def _end_line(self, lang: Lang) -> None:
        self._show(lang, *self._line.finish())
        self._line = CueFilter()

    def _show(self, lang: Lang, shown: str, voiced: str) -> None:
        """Show what the reply's text has come to, and voice its Japanese."""
        if shown:
            self._events.append(SegmentDelta(len(self.segments) - 1, lang, shown))
        if lang == "ja" and voiced:
            self._events.append(SpeechDelta(len(self.segments) - 1, voiced))

    def _complete_up_to(self, segments: int) -> None:
        """Say the first `segments` segments are complete, those not said to be already."""
        self._events += [SegmentComplete(i) for i in range(self._said_complete, segments)]
        self._said_complete = max(self._said_complete, segments)

    def _hand_over(self) -> list[ParserEvent]:
        """The events since the last were handed over."""
        events, self._events = self._events, []
        return events


def format_reply(segments: list[Segment]) -> str:
    """Write segments back in the reply format, e.g. for earlier replies in the prompt."""
    return "".join(f"<ja>{s.ja}</ja><zh>{s.zh}</zh>" for s in segments)


def _partial_suffix(text: str, tags: tuple[str, ...]) -> int:
    """Length of the longest suffix of `text` that could be the start of one of `tags`."""
    for size in range(min(len(text), max(len(t) for t in tags) - 1), 0, -1):
        if any(t.startswith(text[-size:]) for t in tags):
            return size
    return 0
