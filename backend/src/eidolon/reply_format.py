"""The structured reply format and its streaming parser (ADR-0001).

The chat model answers in segments, each a Japanese line followed by its Chinese
subtitle:

    <ja>こんにちは、プロデューサーさん！</ja><zh>你好，制作人！</zh>

The parser turns a stream of arbitrary text chunks into per-segment deltas as soon
as they arrive, so Japanese text can reach TTS before the reply is finished.
"""

from dataclasses import dataclass, field
from typing import Literal

Lang = Literal["ja", "zh"]

FORMAT_INSTRUCTIONS = """\
# 回复格式
无论用户用中文还是日语说话，你都只用日语回答，并给每句日语附上中文字幕。
把回复分成一到几个短段，每段先写日语原文，紧接着写这段的中文字幕，格式如下：
<ja>日语原文</ja><zh>中文字幕</zh>
除了这些标签和标签里的内容，不要输出任何其他文字。"""


@dataclass(frozen=True)
class SegmentDelta:
    segment: int
    lang: Lang
    text: str


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

    def feed(self, chunk: str) -> list[SegmentDelta]:
        self._buffer += chunk
        deltas: list[SegmentDelta] = []
        while True:
            if self._inside is None:
                if not self._open_next_tag():
                    return deltas
            else:
                delta, closed = self._take_content(self._inside)
                if delta is not None:
                    deltas.append(delta)
                if not closed:
                    return deltas
                self._inside = None

    def finish(self) -> list[SegmentDelta]:
        """Flush what is left at the end of a stream; the parser can then go on with the
        next stream of the same reply. A reply that ignored the format becomes one
        Japanese segment."""
        deltas: list[SegmentDelta] = []
        if self._inside is not None:
            keep = _partial_suffix(self._buffer, (f"</{self._inside}>",))
            text = self._buffer[: len(self._buffer) - keep]
            if text:
                deltas.append(self._append(self._inside, text))
        elif not self.segments and (self._stray + self._buffer).strip():
            deltas.append(self._append("ja", (self._stray + self._buffer).strip()))
        self._buffer, self._inside, self._stray = "", None, ""
        return deltas

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
            self.segments.append(Segment())
        self._inside = lang
        return True

    def _take_content(self, lang: Lang) -> tuple[SegmentDelta | None, bool]:
        close = f"</{lang}>"
        end = self._buffer.find(close)
        if end >= 0:
            text, self._buffer = self._buffer[:end], self._buffer[end + len(close) :]
            return (self._append(lang, text) if text else None), True
        keep = _partial_suffix(self._buffer, (close,))
        text = self._buffer[: len(self._buffer) - keep]
        self._buffer = self._buffer[len(self._buffer) - keep :]
        return (self._append(lang, text) if text else None), False

    def _append(self, lang: Lang, text: str) -> SegmentDelta:
        if not self.segments:
            self.segments.append(Segment())
        segment = self.segments[-1]
        setattr(segment, lang, getattr(segment, lang) + text)
        return SegmentDelta(len(self.segments) - 1, lang, text)


def format_reply(segments: list[Segment]) -> str:
    """Write segments back in the reply format, e.g. for earlier replies in the prompt."""
    return "".join(f"<ja>{s.ja}</ja><zh>{s.zh}</zh>" for s in segments)


def _partial_suffix(text: str, tags: tuple[str, ...]) -> int:
    """Length of the longest suffix of `text` that could be the start of one of `tags`."""
    for size in range(min(len(text), max(len(t) for t in tags) - 1), 0, -1):
        if any(t.startswith(text[-size:]) for t in tags):
            return size
    return 0
