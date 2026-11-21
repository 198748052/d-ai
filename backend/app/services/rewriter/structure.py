from __future__ import annotations

import difflib
import re
import statistics

from ...schemas import ParagraphResult
from ..segmenter import split_sentences
from .features import paragraph_metrics

"""结构层：在允许的范围内拉开段落长短，拆分长段、合并短段。

只改变段落边界，保持标题、序号和段落顺序不变；不新增内容。
"""

_HEADING_RE = re.compile(
    r"^\s*(?:[（(][一二三四五六七八九十\d]+[）)]|\d+[.、]|[一二三四五六七八九十]+[、.])[^\n]{0,40}$"
)


def is_heading(text: str) -> bool:
    stripped = text.strip()
    return len(stripped) <= 40 and bool(_HEADING_RE.match(stripped))


def _changed_ratio(original: str, rewritten: str) -> float:
    if not original:
        return 0.0
    return round(1.0 - difflib.SequenceMatcher(None, original, rewritten).ratio(), 4)


def _length_ratio(original: str, rewritten: str) -> float:
    if not original:
        return 1.0
    return round(len(rewritten) / max(1, len(original)), 4)


def _make(index: int, original: str, rewritten: str) -> ParagraphResult:
    return ParagraphResult(
        index=index,
        original=original,
        rewritten=rewritten,
        changed_ratio=_changed_ratio(original, rewritten),
        length_ratio=_length_ratio(original, rewritten),
        metrics=paragraph_metrics(rewritten),
    )


def _split_pair(
    original: str, rewritten: str, ratio: float
) -> tuple[tuple[str, str], tuple[str, str]] | None:
    originals = [s for s in split_sentences(original) if s.strip()]
    rewrittens = [s for s in split_sentences(rewritten) if s.strip()]
    if len(originals) < 2 or len(rewrittens) < 2:
        return None
    o_index = max(1, min(len(originals) - 1, int(len(originals) * ratio)))
    r_index = max(1, min(len(rewrittens) - 1, int(len(rewrittens) * ratio)))
    left_original = "".join(originals[:o_index])
    right_original = "".join(originals[o_index:])
    left_rewritten = "".join(rewrittens[:r_index])
    right_rewritten = "".join(rewrittens[r_index:])
    if min(len(left_rewritten), len(right_rewritten)) < 35:
        return None
    return (
        (left_original, left_rewritten),
        (right_original, right_rewritten),
    )


def _paragraph_cv(results: list[ParagraphResult]) -> float:
    lengths = [len(item.rewritten) for item in results if not is_heading(item.rewritten)]
    if len(lengths) < 2:
        return 1.0
    mean = statistics.fmean(lengths)
    if not mean:
        return 1.0
    return statistics.pstdev(lengths) / mean


def restructure(
    results: list[ParagraphResult],
    intensity: str = "medium",
) -> tuple[list[ParagraphResult], list[str]]:
    """Apply at most 1-3 paragraph boundary changes, keeping order and headings."""
    if len(results) < 3:
        return results, []
    limit = {"light": 1, "medium": 2, "strong": 3}.get(intensity, 2)
    current = list(results)
    changes: list[str] = []
    operations = 0

    while operations < limit:
        if _paragraph_cv(current) >= 0.35 and operations >= 1:
            break

        lengths = [
            (index, len(item.rewritten))
            for index, item in enumerate(current)
            if not is_heading(item.rewritten)
        ]
        if not lengths:
            break

        # 1) 长段拆分：优先拆最长且句子数足够的一段。
        longest_index, longest_len = max(lengths, key=lambda pair: pair[1])
        if longest_len >= 180:
            pair = _split_pair(
                current[longest_index].original,
                current[longest_index].rewritten,
                0.6,
            )
            if pair is not None:
                left, right = pair
                current[longest_index : longest_index + 1] = [
                    _make(longest_index, *left),
                    _make(longest_index + 1, *right),
                ]
                changes.append(
                    f"第 {longest_index + 1} 段较长（{longest_len} 字），拆成两段以拉开段长"
                )
                operations += 1
                continue

        # 2) 短段合并：找相邻且都偏短的两段。
        merged = False
        for index in range(len(current) - 1):
            left = current[index]
            right = current[index + 1]
            if is_heading(left.rewritten) or is_heading(right.rewritten):
                continue
            if len(left.rewritten) < 90 and len(right.rewritten) < 110:
                current[index : index + 2] = [
                    _make(
                        index,
                        left.original + right.original,
                        left.rewritten + right.rewritten,
                    )
                ]
                changes.append(
                    f"第 {index + 1}、{index + 2} 段都偏短，合并为一段以形成长论证段"
                )
                operations += 1
                merged = True
                break
        if merged:
            continue

        # 3) 单句段：把长段末尾的短句独立成段，作为强调。
        for index, length in sorted(lengths, key=lambda pair: pair[1], reverse=True):
            if length < 200:
                continue
            rewrittens = [s for s in split_sentences(current[index].rewritten) if s.strip()]
            originals = [s for s in split_sentences(current[index].original) if s.strip()]
            if len(rewrittens) < 2 or len(originals) < 2:
                continue
            last = rewrittens[-1]
            if len(last) > 35:
                continue
            current[index : index + 1] = [
                _make(index, "".join(originals[:-1]), "".join(rewrittens[:-1])),
                _make(index + 1, originals[-1], last),
            ]
            changes.append(
                f"第 {index + 1} 段末尾短句独立成段，形成单句强调段"
            )
            operations += 1
            break
        else:
            break

    for new_index, item in enumerate(current):
        item.index = new_index
    return current, changes
