from __future__ import annotations

import re

_BLANK_LINE = re.compile(r"\n[ \t]*\n+")
_SENT_BOUNDARY = re.compile(r"(?<=[。！？!?；;…])")


def split_paragraphs(text: str) -> list[str]:
    """Split text into paragraphs while preserving the author's paragraph layout.

    Blank-line separated blocks are treated as paragraphs. If the text has no
    blank lines but does contain single newlines, each non-empty line becomes a
    paragraph.
    """
    if not text:
        return []
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = [b.strip() for b in _BLANK_LINE.split(normalized) if b.strip()]
    if len(blocks) <= 1 and "\n" in normalized:
        lines = [line.strip() for line in normalized.split("\n") if line.strip()]
        if len(lines) > 1:
            return lines
    return blocks


def split_sentences(paragraph: str) -> list[str]:
    if not paragraph:
        return []
    parts = [p for p in _SENT_BOUNDARY.split(paragraph) if p]
    return [p for p in parts if p.strip()]


def join_paragraphs(paragraphs: list[str]) -> str:
    return "\n\n".join(paragraphs)
