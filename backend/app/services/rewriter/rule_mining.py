from __future__ import annotations

import math
import re
from collections import Counter
from dataclasses import dataclass

from ..segmenter import split_sentences
from .diagnosis import TEMPLATE_PATTERNS
from .features import structural_metrics

"""规则挖掘：对比高 AI 率与低 AI 率文章，产出可人工确认的候选规则。

只做离线统计和候选生成，不自动改写，也不自动写入规则库。
"""

STOPWORDS = {
    "这个", "那个", "我们", "他们", "以及", "进行", "通过", "可以", "需要",
    "一个", "一种", "其中", "对于", "关于", "由于", "因此", "但是", "而且",
    "如果", "因为", "所以", "已经", "还是", "或者", "并且", "同时", "此外",
    "这些", "那些", "这种", "那种", "方面", "问题", "研究", "方法", "结果",
    "分析", "影响", "作用", "具有", "存在", "成为", "能够", "不同", "主要",
    "相关", "进一步", "目前", "本文", "笔者", "根据", "基于", "以上", "以下",
    "the", "and", "for", "with", "that", "this", "from", "have", "were",
    "行业", "打造", "传统", "简单", "深层", "形成", "提升", "提高", "降低",
    "增加", "减少", "实现", "完成", "发展", "建设", "推动", "促进", "加强",
    "完善", "优化", "创新", "应用", "系统", "技术", "管理", "服务", "企业",
    "社会", "国家", "经济", "文化", "教育", "环境", "平台", "模式", "机制",
    "体系", "能力", "水平", "质量", "效率", "价值", "目标", "任务", "过程",
    "阶段", "结构", "功能", "特点", "优势", "意义", "作用", "影响", "挑战",
    "趋势", "方向", "领域", "层面", "角度", "维度", "内容", "情况", "条件",
    "方式", "途径", "措施", "策略", "方案", "项目", "工作", "活动", "产品",
    "不是", "而是", "升级", "主要", "重要", "进一步",
}

_CJK = re.compile(r"[\u4e00-\u9fff]")
_NON_WORD = re.compile(r"^[\W_]+$")


@dataclass
class Candidate:
    kind: str
    pattern: str
    note: str
    replacements: list[str]
    severity: str
    high_count: int
    low_count: int
    high_per_1000: float
    low_per_1000: float
    lift: float
    examples: list[str]

    def as_dict(self) -> dict:
        return {
            "kind": self.kind,
            "pattern": self.pattern,
            "note": self.note,
            "replacements": self.replacements,
            "severity": self.severity,
            "high_count": self.high_count,
            "low_count": self.low_count,
            "high_per_1000": self.high_per_1000,
            "low_per_1000": self.low_per_1000,
            "lift": self.lift,
            "examples": self.examples,
        }


def _chars(text: str) -> int:
    return max(1, len(_CJK.findall(text)) + len(re.findall(r"[A-Za-z0-9]", text)))


def _per_1000(count: int, chars: int) -> float:
    return round(count * 1000 / max(1, chars), 2)


def _words(text: str) -> list[str]:
    try:
        import jieba

        raw = jieba.lcut(text)
    except Exception:  # noqa: BLE001
        raw = re.findall(r"[\u4e00-\u9fff]{2,}", text)
    words: list[str] = []
    for word in raw:
        value = word.strip()
        if len(value) < 2 or value in STOPWORDS:
            continue
        if _NON_WORD.match(value):
            continue
        if not _CJK.search(value):
            continue
        words.append(value)
    return words


def _ngrams(text: str, n: int) -> list[str]:
    compact = "".join(_CJK.findall(text))
    return [compact[i : i + n] for i in range(max(0, len(compact) - n + 1))]


def _examples(term: str, texts: list[str], limit: int = 2) -> list[str]:
    examples: list[str] = []
    for text in texts:
        for sentence in split_sentences(text):
            if term in sentence:
                examples.append(sentence.strip()[:80])
                break
        if len(examples) >= limit:
            break
    return examples


def _count_term(term: str, texts: list[str]) -> int:
    return sum(text.count(term) for text in texts)


def _lexicon_candidates(high_texts: list[str], low_texts: list[str], top_n: int) -> list[Candidate]:
    high_chars = _chars("\n".join(high_texts))
    low_chars = _chars("\n".join(low_texts))
    high_counter: Counter[str] = Counter()
    for text in high_texts:
        high_counter.update(_words(text))
    low_counter: Counter[str] = Counter()
    for text in low_texts:
        low_counter.update(_words(text))

    scored: list[tuple[float, str, int, int]] = []
    for term, high_count in high_counter.items():
        if high_count < 2:
            continue
        low_count = low_counter.get(term, 0)
        high_rate = high_count * 1000 / high_chars
        low_rate = low_count * 1000 / low_chars
        if high_rate < low_rate * 1.5:
            continue
        lift = (high_rate + 0.5) / (low_rate + 0.5)
        if lift < 2:
            continue
        score = (high_rate - low_rate) * math.log1p(high_count)
        scored.append((score, term, high_count, low_count))

    scored.sort(reverse=True)
    selected: list[Candidate] = []
    selected_terms: list[str] = []
    for score, term, high_count, low_count in scored:
        if any(term in existing and existing != term for existing in selected_terms):
            continue
        selected_terms.append(term)
        high_rate = _per_1000(high_count, high_chars)
        low_rate = _per_1000(low_count, low_chars)
        selected.append(
            Candidate(
                kind="lexicon",
                pattern=term,
                note="高 AI 率文章高频表达，建议人工确认替换或删除",
                replacements=[],
                severity="medium",
                high_count=high_count,
                low_count=low_count,
                high_per_1000=high_rate,
                low_per_1000=low_rate,
                lift=round((high_rate + 0.5) / (low_rate + 0.5), 2),
                examples=_examples(term, high_texts),
            )
        )
        if len(selected) >= top_n:
            break
    return selected


def _regex_candidates(high_texts: list[str], low_texts: list[str], top_n: int) -> list[Candidate]:
    high_chars = _chars("\n".join(high_texts))
    low_chars = _chars("\n".join(low_texts))
    output: list[Candidate] = []
    for code, label, pattern in TEMPLATE_PATTERNS:
        high_count = sum(len(pattern.findall(text)) for text in high_texts)
        if high_count == 0:
            continue
        low_count = sum(len(pattern.findall(text)) for text in low_texts)
        high_rate = _per_1000(high_count, high_chars)
        low_rate = _per_1000(low_count, low_chars)
        lift = (high_rate + 0.5) / (low_rate + 0.5)
        if lift < 1.5:
            continue
        example = ""
        for text in high_texts:
            match = pattern.search(text)
            if match:
                example = match.group(0)[:80]
                break
        output.append(
            Candidate(
                kind="regex",
                pattern=pattern.pattern,
                note=f"{code} {label}：高 AI 率文章命中更多",
                replacements=[],
                severity="medium",
                high_count=high_count,
                low_count=low_count,
                high_per_1000=high_rate,
                low_per_1000=low_rate,
                lift=round(lift, 2),
                examples=[example] if example else [],
            )
        )
    output.sort(key=lambda item: item.lift, reverse=True)
    return output[:top_n]


def _structure_candidates(high_texts: list[str], low_texts: list[str]) -> list[Candidate]:
    def mean_metric(texts: list[str], key: str) -> float:
        values = [structural_metrics(text).get(key, 0) for text in texts]
        return round(sum(values) / len(values), 3) if values else 0.0

    output: list[Candidate] = []
    labels = {
        "cv": ("句长变异系数", "高 AI 文本句长更均匀；低 AI 文本长短差异更大"),
        "short_run": ("连续短句", "高 AI 文本连续短句更多"),
        "long_nested": ("长句嵌套", "高 AI 文本长句嵌套更多"),
        "de_chain": ("三层的字链", "高 AI 文本多层“的”更多"),
        "passive_per_1000": ("被字句密度", "高 AI 文本被动语态更多"),
        "it_per_1000": ("它字指代", "高 AI 文本“它”字指代更多"),
        "de_ending_ratio": ("的字收尾", "高 AI 文本“的”字收尾更多"),
        "dash_per_1000": ("破折号密度", "高 AI 文本破折号更多"),
        "paragraph_cv": ("段落长度 CV", "高 AI 文本段落长度更均匀"),
    }
    for key, (label, note) in labels.items():
        high = mean_metric(high_texts, key)
        low = mean_metric(low_texts, key)
        if key == "cv":
            significant = low - high > 0.08
        elif key == "paragraph_cv":
            significant = low - high > 0.1
        else:
            significant = high - low > 0.5
        if not significant:
            continue
        output.append(
            Candidate(
                kind="structure",
                pattern=key,
                note=f"{label}：高 AI {high} vs 低 AI {low}。{note}",
                replacements=[],
                severity="medium",
                high_count=0,
                low_count=0,
                high_per_1000=high,
                low_per_1000=low,
                lift=round((high + 0.1) / (low + 0.1), 2),
                examples=[],
            )
        )
    return output


def mine_rules(
    high_texts: list[str],
    low_texts: list[str],
    top_n: int = 30,
) -> dict:
    high_texts = [text for text in high_texts if text and text.strip()]
    low_texts = [text for text in low_texts if text and text.strip()]
    if not high_texts or not low_texts:
        return {
            "summary": {
                "high_count": len(high_texts),
                "low_count": len(low_texts),
                "high_chars": sum(_chars(text) for text in high_texts),
                "low_chars": sum(_chars(text) for text in low_texts),
                "message": "需要同时提供高 AI 率和低 AI 率文章",
            },
            "lexicon": [],
            "regex": [],
            "structure": [],
        }
    top_n = max(5, min(100, top_n))
    return {
        "summary": {
            "high_count": len(high_texts),
            "low_count": len(low_texts),
            "high_chars": sum(_chars(text) for text in high_texts),
            "low_chars": sum(_chars(text) for text in low_texts),
            "message": "候选规则来自离线统计，需要人工确认后再加入规则库",
        },
        "lexicon": [item.as_dict() for item in _lexicon_candidates(high_texts, low_texts, top_n)],
        "regex": [item.as_dict() for item in _regex_candidates(high_texts, low_texts, top_n)],
        "structure": [item.as_dict() for item in _structure_candidates(high_texts, low_texts)],
    }
