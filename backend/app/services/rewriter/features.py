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


_DE_CHAIN = re.compile(r"(?:[^，。；！？\s]{1,12}的){3,}[^，。；！？\s]{0,12}")
_ENUM_RUN = re.compile(
    r"首先[^。！？]{0,80}其次|第一[，,、][^。！？]{0,60}第二[，,、]|"
    r"一方面[^。！？]{0,80}另一方面"
)


def _per_1000(count: int, chars: int) -> float:
    return round(count * 1000 / chars, 2) if chars else 0.0


def short_sentence_runs(text: str, limit: int = 12, min_run: int = 3) -> int:
    """Count runs of >= min_run consecutive very short sentences (S-02)."""
    sentences = [s for s in split_sentences(text) if s.strip()]
    lengths = [len(s) for s in sentences]
    runs = 0
    start = 0
    for index in range(1, len(lengths) + 1):
        if index == len(lengths) or lengths[index] >= limit:
            if index - start >= min_run:
                runs += 1
            start = index
    return runs


def structural_metrics(text: str) -> dict:
    """Deterministic structural proxies for the S-01..S-20 rule family."""
    chars = len(_compact(text))
    sentences = [s for s in split_sentences(text) if s.strip()]
    lengths = [len(s) for s in sentences]
    count = len(lengths)
    mean_len = sum(lengths) / count if count else 0.0
    if count > 1 and mean_len:
        variance = sum((value - mean_len) ** 2 for value in lengths) / count
        cv = (variance**0.5) / mean_len
    else:
        cv = 1.0

    long_nested = sum(
        1 for sentence in sentences if len(sentence) > 60 and sentence.count("，") > 5
    )
    de_chain = len(_DE_CHAIN.findall(text))
    passive = text.count("被")
    pronoun_it = text.count("它")
    de_ending = sum(1 for sentence in sentences if sentence.rstrip("。！？").endswith("的"))
    de_ending_ratio = de_ending / count if count else 0.0
    dash = max(0, text.count("—") - text.count("——"))
    enumeration = len(_ENUM_RUN.findall(text))
    openings = [sentence[:2] for sentence in sentences]
    opening_repeats = sum(
        1
        for index in range(2, len(openings))
        if openings[index] == openings[index - 1] == openings[index - 2]
    )
    short_run = short_sentence_runs(text)

    paragraphs = [p for p in re.split(r"\n\s*\n+", text) if p.strip()]
    para_lengths = [len(_compact(p)) for p in paragraphs]
    if len(para_lengths) > 1:
        para_mean = sum(para_lengths) / len(para_lengths)
        para_var = sum((value - para_mean) ** 2 for value in para_lengths) / len(para_lengths)
        para_cv = (para_var**0.5) / para_mean if para_mean else 0.0
    else:
        para_cv = 1.0

    return {
        "chars": chars,
        "sentences": count,
        "mean_len": round(mean_len, 2),
        "cv": round(cv, 3),
        "short_run": short_run,
        "long_nested": long_nested,
        "de_chain": de_chain,
        "passive_per_1000": _per_1000(passive, chars),
        "it_per_1000": _per_1000(pronoun_it, chars),
        "de_ending_ratio": round(de_ending_ratio, 3),
        "dash_per_1000": _per_1000(dash, chars),
        "enumeration_runs": enumeration,
        "opening_repeats": opening_repeats,
        "paragraph_cv": round(para_cv, 3),
    }


def structural_issues(metrics: dict) -> list[dict]:
    """Map structural metrics to human-readable S-rule findings."""
    issues: list[dict] = []

    def add(code: str, label: str, detail: str) -> None:
        issues.append({"code": code, "label": label, "detail": detail})

    if metrics.get("sentences", 0) >= 4 and metrics.get("cv", 1) < 0.32:
        add("S-01", "句长过于均匀", "句子长度接近，缺少长短句交错")
    if metrics.get("short_run", 0) > 0:
        add("S-02", "短句群堆叠", "连续三句以上都是短句，像降重工具输出")
    if metrics.get("long_nested", 0) > 0:
        add("S-03", "长句过度嵌套", "单句超过 60 字且逗号分句超过 5 个")
    if metrics.get("de_chain", 0) > 0:
        add("S-04", "长定语堆叠", "出现三层以上的“的”字修饰链")
    if metrics.get("passive_per_1000", 0) > 8:
        add("S-05", "被字句过量", "被动语态密度偏高")
    if metrics.get("it_per_1000", 0) > 10:
        add("S-08", "它字指代滥用", "连续用“它”指代，主语应省略或复现名词")
    if metrics.get("de_ending_ratio", 0) > 0.15:
        add("S-16", "的字收尾偏多", "过多句子以“的”收尾")
    if metrics.get("dash_per_1000", 0) >= 3:
        add("P14", "破折号偏多", "破折号高频且功能雷同")
    if metrics.get("enumeration_runs", 0) > 0:
        add("C-08", "完美列举", "出现完整的首先/其次或第一/第二序列")
    if metrics.get("opening_repeats", 0) > 0:
        add("S-12", "段内开头重复", "连续三句开头相同")
    if metrics.get("paragraph_cv", 1) < 0.3 and metrics.get("chars", 0) > 500:
        add("S-15", "段落长度均匀", "段落字数过于接近，缺少短段或长段")
    return issues
