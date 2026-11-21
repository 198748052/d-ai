from __future__ import annotations

import re

from ..segmenter import split_sentences
from .context_guard import load_blacklist
from .features import short_sentence_runs, structural_metrics
from .leakage import scan as scan_leakage

"""Anti-overfit and anti-regression guards.

改写动作本身会引入新味：过度不均匀的句长、连续短句、刻意规避痕迹都会
被检测器抓住。这里负责在候选结果落盘前拦截这些"矫枉过正"。
"""

_DUP_WINDOW = 40
_DUP_STEP = 10


def has_duplication(text: str, window: int = _DUP_WINDOW, step: int = _DUP_STEP) -> bool:
    seen: set[str] = set()
    for index in range(0, max(1, len(text) - window), step):
        chunk = text[index : index + window]
        if chunk in seen:
            return True
        seen.add(chunk)
    return False


def clean_candidate(original: str, candidate: str) -> str:
    text = (candidate or "").strip()
    if not text:
        return text
    # 只处理“原文重复两遍”的明显回声，避免误删合法扩写。
    if original and len(original) > 20 and text.count(original) >= 2:
        text = text.replace(original, "", 1).strip()
    half = len(text) // 2
    if half > 20 and text[:half].strip() == text[half:].strip():
        text = text[:half].strip()
    return text


def _introduced_short_run(original: str, candidate: str) -> bool:
    before = short_sentence_runs(original)
    after = short_sentence_runs(candidate)
    return after > before


def _over_diverse(original: str, candidate: str) -> bool:
    """Reject extreme burstiness that looks like deliberate evasion."""
    before = structural_metrics(original).get("cv", 1.0)
    after = structural_metrics(candidate).get("cv", 1.0)
    return after > 0.95 and after > before + 0.35


def _introduced_leakage(candidate: str) -> bool:
    return bool(scan_leakage(candidate))


def overfit_reason(original: str, candidate: str) -> str | None:
    if _introduced_short_run(original, candidate):
        return "连续短句堆叠（S-02）"
    if _over_diverse(original, candidate):
        return "句长差异被刻意拉大"
    if _introduced_leakage(candidate):
        return "引入过程痕迹"
    return None


def acceptable(
    original: str,
    candidate: str,
    max_ratio: float = 1.5,
    min_ratio: float = 0.6,
    allow_overfit: bool = False,
) -> tuple[bool, str]:
    if not candidate or not candidate.strip():
        return False, "结果为空"
    ratio = len(candidate) / max(1, len(original))
    delta = abs(len(candidate) - len(original))
    if delta > 30 and (ratio > max_ratio or ratio < min_ratio):
        return False, "长度异常"
    if has_duplication(candidate):
        return False, "结果重复"
    blacklist = load_blacklist()
    if any(
        term and term in candidate and term not in original
        for term in blacklist.hard_banned
    ):
        return False, "引入黑名单替换产物"
    if not allow_overfit:
        reason = overfit_reason(original, candidate)
        if reason:
            return False, reason
    return True, ""


def merge_short_runs(text: str, limit: int = 12, max_merge: int = 2) -> str:
    """Merge consecutive very short sentences so they stop looking machine-split."""
    sentences = [sentence for sentence in split_sentences(text) if sentence.strip()]
    if len(sentences) < 3:
        return text
    output: list[str] = []
    merges = 0
    index = 0
    while index < len(sentences):
        current = sentences[index]
        if (
            merges < max_merge
            and index + 1 < len(sentences)
            and len(current) < limit
            and len(sentences[index + 1]) < limit
            and current.rstrip().endswith(("。", "！", "？"))
        ):
            output.append(current.rstrip()[:-1] + "，" + sentences[index + 1])
            merges += 1
            index += 2
        else:
            output.append(current)
            index += 1
    return "".join(output)


def strip_repeated_openers(text: str, max_repeat: int = 3) -> str:
    """Break mechanical sentence openings such as 从…/在… repeated three times."""
    sentences = [sentence for sentence in split_sentences(text) if sentence.strip()]
    if len(sentences) < max_repeat:
        return text
    output: list[str] = []
    run: list[str] = []
    for sentence in sentences:
        prefix = sentence[:2]
        if run and run[-1][0] == prefix:
            run.append((prefix, sentence))
        else:
            run = [(prefix, sentence)]
        output.append(sentence)
        if len(run) == max_repeat:
            # Leave the third one untouched; the LLM pass handles semantics.
            run = []
    return "".join(output)


def quality_compare(before: dict, after: dict) -> dict:
    """Compare two diagnosis payloads and flag regressions."""
    before_total = float(before.get("total_per_1000") or 0.0)
    after_total = float(after.get("total_per_1000") or 0.0)
    before_structure = before.get("structure") or {}
    after_structure = after.get("structure") or {}
    regressions: list[str] = []
    if after_total > before_total + 0.5:
        regressions.append("AI 特征总密度上升")
    if after_structure.get("short_run", 0) > before_structure.get("short_run", 0):
        regressions.append("新增连续短句")
    if after_structure.get("cv", 1) > 0.95 and before_structure.get("cv", 1) < 0.6:
        regressions.append("句长差异被刻意拉大")
    if after.get("leakage") and not before.get("leakage"):
        regressions.append("新增过程痕迹")
    return {
        "before_total": before_total,
        "after_total": after_total,
        "regressions": regressions,
        "ok": not regressions,
    }
