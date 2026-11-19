from __future__ import annotations

import math
import re

from ..segmenter import split_sentences

CONNECTORS = [
    "首先", "其次", "再次", "最后", "此外", "与此同时", "综上所述", "总而言之",
    "由此可见", "值得注意的是", "需要指出的是", "需要强调的是", "基于此",
    "在此基础上", "在此背景下", "因此", "然而", "从而", "进而", "不仅",
    "而且", "一方面", "另一方面", "总之", "总的来说",
]

TEMPLATES = [
    "具有重要意义", "发挥重要作用", "发挥关键作用", "奠定坚实基础", "提供有力支撑",
    "注入新动能", "开辟新路径", "提供新思路", "带来新机遇", "不可或缺", "至关重要",
    "高质量发展", "赋能", "抓手", "闭环", "链路", "沉淀", "对齐", "颗粒度",
    "底层逻辑", "范式", "维度", "组合拳", "扮演着重要角色", "形成了良性循环",
]


def _compact(text: str) -> str:
    return re.sub(r"\s+", "", text)


def _ngrams(text: str, n: int = 3) -> list[str]:
    compact = _compact(text)
    return [compact[i : i + n] for i in range(len(compact) - n + 1)]


def _bigrams(text: str) -> set[str]:
    return {text[i : i + 2] for i in range(len(text) - 1)}


def analyze(text: str) -> dict:
    sentences = [s for s in split_sentences(text) if s.strip()]
    lengths = [len(s) for s in sentences]
    count = len(lengths)
    mean_len = sum(lengths) / count if count else 0.0
    if count > 1 and mean_len:
        variance = sum((value - mean_len) ** 2 for value in lengths) / count
        cv = math.sqrt(variance) / mean_len
    else:
        cv = 1.0

    chars = _compact(text)
    ttr = len(set(chars)) / len(chars) if chars else 1.0

    grams = _ngrams(text)
    repetition = 1 - len(set(grams)) / len(grams) if grams else 0.0

    connector_density = sum(text.count(item) for item in CONNECTORS) / max(1, len(chars)) * 1000
    template_count = sum(text.count(item) for item in TEMPLATES)

    similarities: list[float] = []
    for left, right in zip(sentences, sentences[1:]):
        left_grams = _bigrams(left)
        right_grams = _bigrams(right)
        if left_grams and right_grams:
            similarities.append(len(left_grams & right_grams) / len(left_grams | right_grams))
    adjacent_sim = sum(similarities) / len(similarities) if similarities else 0.0

    return {
        "sentences": count,
        "mean_len": round(mean_len, 2),
        "cv": round(cv, 3),
        "ttr": round(ttr, 3),
        "repetition": round(repetition, 3),
        "connector_density": round(connector_density, 2),
        "template_count": template_count,
        "adjacent_sim": round(adjacent_sim, 3),
    }


def ai_likeness(metrics: dict) -> float:
    """Proxy score built from publicly described detector signals. Higher means more AI-like."""
    score = 0.0
    score += max(0.0, 0.45 - metrics["cv"]) * 100 * 0.28
    score += max(0.0, metrics["connector_density"] - 2.5) * 2.5 * 0.12
    score += max(0.0, 0.42 - metrics["ttr"]) * 100 * 0.12
    score += metrics["repetition"] * 100 * 0.16
    score += metrics["template_count"] * 0.9 * 0.14
    score += max(0.0, metrics["adjacent_sim"] - 0.12) * 100 * 0.18
    return round(score, 2)


def uniform_runs(text: str, window: int = 8, min_run: int = 3) -> list[dict]:
    """Find runs of consecutive sentences whose lengths are too close."""
    sentences = [s for s in split_sentences(text) if s.strip()]
    lengths = [len(s) for s in sentences]
    runs: list[dict] = []
    start = 0
    for index in range(1, len(lengths) + 1):
        if index == len(lengths) or abs(lengths[index] - lengths[index - 1]) > window:
            if index - start >= min_run:
                runs.append(
                    {
                        "start": start,
                        "end": index - 1,
                        "lengths": lengths[start:index],
                    }
                )
            start = index
    return runs


HEDGES = [
    "可能", "或许", "在一定程度上", "从现有数据看", "在现有", "范围内", "倾向于",
    "大致", "较为", "某种程度上", "未必", "不完全", "有待", "尚需", "条件下",
]


def paragraph_metrics(text: str) -> dict:
    sentences = [s for s in split_sentences(text) if s.strip()]
    lengths = [len(s) for s in sentences]
    count = len(lengths)
    mean_len = sum(lengths) / count if count else 0.0
    if count > 1 and mean_len:
        variance = sum((value - mean_len) ** 2 for value in lengths) / count
        cv = (variance**0.5) / mean_len
    else:
        cv = 1.0

    short_count = sum(1 for value in lengths if value < 15)
    long_count = sum(1 for value in lengths if value > 40)
    openings = [sentence[:2] for sentence in sentences]
    opening_repeats = sum(
        1
        for index in range(2, len(openings))
        if openings[index] == openings[index - 1] == openings[index - 2]
    )
    hedge_count = sum(text.count(word) for word in HEDGES)
    return {
        "sentences": count,
        "cv": round(cv, 3),
        "short_count": short_count,
        "long_count": long_count,
        "opening_repeats": opening_repeats,
        "hedge_count": hedge_count,
    }
