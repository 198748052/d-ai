from __future__ import annotations

import re

_PATTERNS: list[re.Pattern[str]] = [
    re.compile(r"```[\s\S]*?```"),
    re.compile(r"`[^`\n]+`"),
    re.compile(r"https?://[^\s，。；、）)\]]+"),
    re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+"),
    re.compile(r"\[[\d,\-\s]+\]"),
    re.compile(r"（[^（）]{0,40}?\d{4}[^（）]{0,20}?）"),
    re.compile(r"\([^()]{0,40}?\d{4}[^()]{0,20}?\)"),
    re.compile(r"「[^」]{15,}」"),
    re.compile(r"『[^』]{15,}』"),
    re.compile(r"“[^”]{15,}”"),
    re.compile(r'"[^"\n]{15,200}"'),
    re.compile(r"\$[^$\n]+\$"),
    re.compile(r"\d+(?:\.\d+)?%"),
    re.compile(r"\d+(?:\.\d+)?\s*(?:年|月|日|万元|亿元|万|亿|元|人|次|个|项|倍|公里|千米|米|kg|km|GB|MB|TB|ms|s)"),
    re.compile(r"\d{4}[-/]\d{1,2}(?:[-/]\d{1,2})?"),
    re.compile(r"\d+(?:\.\d+)?"),
]

_PLACEHOLDER = "⟦{}⟧"
_PLACEHOLDER_RE = re.compile(r"⟦([A-Z]+)⟧")


def _encode_id(index: int) -> str:
    value = index + 1
    letters = ""
    while value > 0:
        value, rem = divmod(value - 1, 26)
        letters = chr(65 + rem) + letters
    return letters


def _decode_id(token: str) -> int:
    value = 0
    for ch in token:
        value = value * 26 + (ord(ch) - 64)
    return value - 1


class Protector:
    """Masks spans that must survive rewriting untouched."""

    def __init__(self, extra_terms: list[str] | None = None):
        self.extra_terms = [t for t in (extra_terms or []) if t and len(t) >= 2]

    def protect(self, text: str) -> tuple[str, list[str]]:
        spans: list[str] = []

        def mask(value: str) -> str:
            token = _PLACEHOLDER.format(_encode_id(len(spans)))
            spans.append(value)
            return token

        result = text
        for term in sorted(self.extra_terms, key=len, reverse=True):
            result = result.replace(term, mask(term))

        for pattern in _PATTERNS:
            result = pattern.sub(lambda m: mask(m.group(0)), result)

        return result, spans

    def restore(self, text: str, spans: list[str]) -> str:
        def repl(m: re.Match[str]) -> str:
            idx = _decode_id(m.group(1))
            if 0 <= idx < len(spans):
                return spans[idx]
            return m.group(0)

        return _PLACEHOLDER_RE.sub(repl, text)

    @staticmethod
    def has_placeholders(text: str) -> bool:
        return bool(_PLACEHOLDER_RE.search(text))
