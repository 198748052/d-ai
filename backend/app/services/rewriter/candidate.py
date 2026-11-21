from __future__ import annotations

import difflib
import json
import re
from functools import lru_cache
from pathlib import Path

from ...core.config import DATA_DIR
from .content import fact_used
from .diagnosis import diagnose
from .features import short_sentence_runs
from .leakage import scan as scan_leakage

"""模型层：多候选生成后的选择器。

综合语义保真、代理特征分、自然度和内容事实使用情况，选一个候选。
真实检测器反馈校准后的权重会从 data/calibration.json 读取。
"""

WEIGHTS_PATH = DATA_DIR / "calibration.json"
DEFAULT_WEIGHTS = {
    "proxy": 0.45,
    "semantic": 0.2,
    "natural": 0.2,
    "content": 0.15,
}


@lru_cache(maxsize=1)
def load_weights() -> dict:
    try:
        data = json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULT_WEIGHTS)
    weights = dict(DEFAULT_WEIGHTS)
    for key, value in (data.get("selector_weights") or {}).items():
        try:
            weights[key] = float(value)
        except (TypeError, ValueError):
            continue
    return weights


def reload_weights() -> None:
    load_weights.cache_clear()


def _semantic_score(original: str, candidate: str) -> float:
    if not original or not candidate:
        return 1.0
    ratio = difflib.SequenceMatcher(None, original, candidate).ratio()
    # 目标区间 0.55-0.85：太低丢信息，太高说明只做了同义替换。
    if 0.55 <= ratio <= 0.85:
        return 0.0
    return round(min(1.0, abs(ratio - 0.7)), 4)


def _natural_score(candidate: str, after: dict) -> float:
    structure = after.get("structure") or {}
    score = 0.0
    score += short_sentence_runs(candidate) * 1.5
    score += structure.get("long_nested", 0) * 0.6
    if structure.get("cv", 1.0) > 0.95:
        score += 1.2
    if structure.get("cv", 1.0) < 0.25:
        score += 0.8
    score += len(scan_leakage(candidate)) * 2.0
    return round(score, 4)


def _content_score(candidate: str, facts: list[dict], before: dict, after: dict) -> float:
    if not facts:
        return 0.0
    used = sum(
        1 for fact in facts if fact_used(str(fact.get("text") or ""), candidate)
    )
    score = (len(facts) - used) / max(1, len(facts)) * 2.0
    before_density = before.get("content_density") or {}
    after_density = after.get("content_density") or {}
    for key in ("numbers", "citations", "examples", "limitations"):
        if after_density.get(key, 0) < before_density.get(key, 0):
            score += 0.3
    return round(score, 4)


def score_candidate(
    original: str,
    candidate: str,
    before: dict,
    after: dict,
    facts: list[dict] | None = None,
) -> dict:
    weights = load_weights()
    facts = facts or []
    proxy = float(after.get("total_per_1000") or 0.0) / 100.0
    semantic = _semantic_score(original, candidate)
    natural = _natural_score(candidate, after)
    content = _content_score(candidate, facts, before, after)
    total = (
        weights["proxy"] * proxy
        + weights["semantic"] * semantic
        + weights["natural"] * natural
        + weights["content"] * content
    )
    return {
        "score": round(total, 4),
        "proxy": round(proxy, 4),
        "semantic": semantic,
        "natural": natural,
        "content": content,
        "ai_per_1000": after.get("total_per_1000"),
    }


def select_candidate(
    original: str,
    candidates: list[str],
    before: dict,
    facts: list[dict] | None = None,
) -> tuple[str, list[dict]]:
    scored: list[dict] = []
    best_text = candidates[0] if candidates else original
    best_score = float("inf")
    for index, candidate in enumerate(candidates):
        if not candidate or not candidate.strip():
            continue
        after = diagnose(candidate, "academic")
        result = score_candidate(original, candidate, before, after, facts)
        result["index"] = index
        scored.append(result)
        if result["score"] < best_score:
            best_score = result["score"]
            best_text = candidate
    return best_text, scored
