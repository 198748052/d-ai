from __future__ import annotations

import re
from dataclasses import dataclass

from ..segmenter import split_paragraphs

"""内容层：扫描空泛断言、生成澄清问题、核验用户补充的事实。

原则：具体数据、引用、案例、局限只能来自用户，禁止模型编造。
"""

ABSTRACT_CLAIMS = [
    "显著提升", "显著提高", "显著降低", "显著改善", "明显提升", "明显改善",
    "大幅提高", "大幅提升", "大幅降低", "有效提升", "有效改善", "效果显著",
    "效果良好", "性能优异", "性能优越", "具有优势", "显著优于", "明显优于",
    "提高效率", "降低成本", "增强稳定性", "提升质量", "改善体验",
]

UNSOURCED = re.compile(r"(?:研究表明|数据显示|专家指出|学者认为|业内人士表示|普遍认为)")
CITATION = re.compile(
    r"\[\d+(?:[,\-]\d+)*\]|（\d{4}）|\(\d{4}\)|（[^）]{1,16}[，,]\s*\d{4}）|"
    r"\([^)]{1,16}[，,]\s*\d{4}\)|"
    r"[A-Za-z][A-Za-z\-']+\s+et\s+al\.?,?\s*\d{4}|"
    r"[A-Za-z][A-Za-z\-']+\s*等?（\d{4}）|等（\d{4}）"
)
NUMBER = re.compile(
    r"\d+(?:\.\d+)?\s*(?:%|％|倍|个百分点|人|例|个|次|项|组|年|月|天|小时|分钟|秒|"
    r"mg|kg|km|GB|MB|TB|ms|元|万元|亿元)"
)
EXPERIMENT = re.compile(r"(?:实验|测试|调查|问卷|样本|数据集|仿真|对照|基线)")
LIMITATION = re.compile(r"(?:局限|不足|限制|偏差|未能|尚未|有待|例外|失败|不适用|边界条件)")
EXAMPLE = re.compile(r"(?:例如|比如|譬如|以[^。！？]{1,16}为例)")
HEDGE = re.compile(r"(?:可能|或许|在一定程度上|从现有数据看|倾向于|大致|较为|未必|尚需)")
JUDGMENT = re.compile(r"(?:本文认为|笔者认为|在我看来|可以判断|更合理的解释是|值得注意的是)")

_STOPWORDS = {
    "这个", "那个", "我们", "他们", "以及", "进行", "通过", "可以", "需要",
    "一个", "一种", "其中", "对于", "关于", "由于", "因此", "但是", "而且",
    "the", "and", "for", "with", "that", "this",
}


@dataclass
class Question:
    id: str
    paragraph: int
    claim: str
    question: str
    kind: str
    suggestions: list[str]


def _nearby(text: str, start: int, end: int, pattern: re.Pattern[str], window: int = 40) -> bool:
    left = max(0, start - window)
    right = min(len(text), end + window)
    return bool(pattern.search(text[left:right]))


def content_density(text: str) -> dict:
    chars = max(1, len(re.sub(r"\s+", "", text)))
    numbers = len(NUMBER.findall(text))
    citations = len(CITATION.findall(text))
    examples = len(EXAMPLE.findall(text))
    limitations = len(LIMITATION.findall(text))
    hedges = len(HEDGE.findall(text))
    judgments = len(JUDGMENT.findall(text))
    experiments = len(EXPERIMENT.findall(text))
    return {
        "chars": chars,
        "numbers": numbers,
        "citations": citations,
        "examples": examples,
        "limitations": limitations,
        "hedges": hedges,
        "judgments": judgments,
        "experiments": experiments,
        "numbers_per_1000": round(numbers * 1000 / chars, 2),
        "citations_per_1000": round(citations * 1000 / chars, 2),
        "specificity_score": numbers + citations + examples + experiments,
    }


def scan_content_needs(text: str, max_questions: int = 8) -> list[Question]:
    paragraphs = split_paragraphs(text)
    questions: list[Question] = []
    seen: set[tuple[int, str]] = set()

    for p_index, paragraph in enumerate(paragraphs):
        per_paragraph = 0
        for claim in ABSTRACT_CLAIMS:
            start = paragraph.find(claim)
            if start == -1:
                continue
            if _nearby(paragraph, start, start + len(claim), NUMBER):
                continue
            key = (p_index, "data")
            if key in seen or per_paragraph >= 2:
                continue
            seen.add(key)
            per_paragraph += 1
            questions.append(
                Question(
                    id=f"p{p_index + 1}-data-{len(questions) + 1}",
                    paragraph=p_index + 1,
                    claim=claim,
                    question=(
                        f"第 {p_index + 1} 段「{claim}」缺少具体数据。"
                        "具体是哪个指标、提升了多少、样本量或实验条件是什么？"
                    ),
                    kind="data",
                    suggestions=["指标名称", "提升幅度", "样本量", "实验条件"],
                )
            )

        for match in UNSOURCED.finditer(paragraph):
            key = (p_index, "citation")
            if key in seen or per_paragraph >= 2:
                continue
            if _nearby(paragraph, match.start(), match.end(), CITATION, window=60):
                continue
            seen.add(key)
            per_paragraph += 1
            questions.append(
                Question(
                    id=f"p{p_index + 1}-citation-{len(questions) + 1}",
                    paragraph=p_index + 1,
                    claim=match.group(0),
                    question=(
                        f"第 {p_index + 1} 段「{match.group(0)}」没有出处。"
                        "能否补充作者、年份、期刊/会议或 DOI？"
                    ),
                    kind="citation",
                    suggestions=["作者", "年份", "期刊/会议", "DOI"],
                )
            )

        if EXPERIMENT.search(paragraph) and not _nearby(
            paragraph, 0, len(paragraph), NUMBER, window=0
        ):
            key = (p_index, "method")
            if key not in seen and per_paragraph < 2:
                seen.add(key)
                per_paragraph += 1
                questions.append(
                    Question(
                        id=f"p{p_index + 1}-method-{len(questions) + 1}",
                        paragraph=p_index + 1,
                        claim="实验/测试描述",
                        question=(
                            f"第 {p_index + 1} 段提到实验或测试，"
                            "样本量、对照组和实验条件分别是什么？"
                        ),
                        kind="method",
                        suggestions=["样本量", "对照组", "实验条件", "评价指标"],
                    )
                )

        if ABSTRACT_CLAIMS and any(claim in paragraph for claim in ABSTRACT_CLAIMS):
            if not LIMITATION.search(paragraph):
                key = (p_index, "limitation")
                if key not in seen and per_paragraph < 2:
                    seen.add(key)
                    per_paragraph += 1
                    questions.append(
                        Question(
                            id=f"p{p_index + 1}-limitation-{len(questions) + 1}",
                            paragraph=p_index + 1,
                            claim="效果/优势断言",
                            question=(
                                f"第 {p_index + 1} 段只写了效果，没有边界。"
                                "这套方法在哪些条件下失效或效果下降？有没有失败案例或例外？"
                            ),
                            kind="limitation",
                            suggestions=["失效条件", "失败案例", "适用边界", "反例"],
                        )
                    )

        if len(questions) >= max_questions:
            break

    return questions[:max_questions]


def unsourced_count(text: str) -> int:
    return len(UNSOURCED.findall(text))


def assign_facts(facts: list[dict], paragraphs: list[str]) -> dict[int, list[dict]]:
    """把事实分配到段落：优先 anchor，其次词面重叠，最后放第一段。"""
    assignments: dict[int, list[dict]] = {}
    if not facts or not paragraphs:
        return assignments
    for fact in facts:
        text = str(fact.get("text") or "").strip()
        if not text:
            continue
        anchor = str(fact.get("anchor") or "").strip()
        target = None
        match = re.search(r"第\s*(\d+)\s*段", anchor)
        if match:
            index = int(match.group(1)) - 1
            if 0 <= index < len(paragraphs):
                target = index
        if target is None and anchor:
            for index, paragraph in enumerate(paragraphs):
                if anchor in paragraph:
                    target = index
                    break
        if target is None:
            tokens = _fact_tokens(text)
            best_index = 0
            best_overlap = 0
            for index, paragraph in enumerate(paragraphs):
                overlap = sum(1 for token in tokens if token in paragraph)
                if overlap > best_overlap:
                    best_overlap = overlap
                    best_index = index
            target = best_index
        assignments.setdefault(target, []).append(fact)
    return assignments


def fact_lines(facts: list[dict]) -> str:
    lines: list[str] = []
    for index, fact in enumerate(facts, 1):
        kind = str(fact.get("kind") or "other")
        text = str(fact.get("text") or "").strip()
        anchor = str(fact.get("anchor") or "").strip()
        if not text:
            continue
        suffix = f"（位置提示：{anchor}）" if anchor else ""
        lines.append(f"{index}. [{kind}] {text}{suffix}")
    return "\n".join(lines)


def _fact_tokens(fact: str) -> list[str]:
    numbers = NUMBER.findall(fact)
    citations = CITATION.findall(fact)
    tokens: list[str] = []
    for item in numbers + citations:
        value = item.strip()
        if value and value not in tokens:
            tokens.append(value)
    try:
        import jieba

        words = [
            word.strip()
            for word in jieba.lcut(fact)
            if len(word.strip()) >= 2 and word.strip() not in _STOPWORDS
        ]
    except Exception:  # noqa: BLE001
        words = []
    for word in sorted(words, key=len, reverse=True):
        if word not in tokens:
            tokens.append(word)
    return tokens[:6]


def fact_used(fact: str, text: str) -> bool:
    tokens = _fact_tokens(fact)
    if not tokens:
        return fact.strip()[:12] in text
    hits = sum(1 for token in tokens if token in text)
    required = 1 if len(tokens) <= 2 else max(2, len(tokens) // 2)
    return hits >= required


def verify_content(
    before: str,
    after: str,
    facts: list[dict],
    unsourced_before: int = 0,
    unsourced_after: int = 0,
) -> dict:
    density_before = content_density(before)
    density_after = content_density(after)
    warnings: list[str] = []
    used = 0
    for fact in facts:
        text = str(fact.get("text") or "").strip()
        if not text:
            continue
        if fact_used(text, after):
            used += 1
        else:
            warnings.append(f"用户补充的事实没有写入结果：{text[:40]}")

    for key, label in [
        ("numbers", "数字"),
        ("citations", "引用"),
        ("examples", "案例"),
        ("limitations", "局限"),
    ]:
        if density_after[key] < density_before[key]:
            warnings.append(f"改写后{label}数量下降：{density_before[key]} → {density_after[key]}")

    if unsourced_before and unsourced_after >= unsourced_before and not facts:
        warnings.append("无源权威表述没有减少，建议补充引用或改为限定表述")

    return {
        "facts_provided": len([fact for fact in facts if str(fact.get("text") or "").strip()]),
        "facts_used": used,
        "density_before": density_before,
        "density_after": density_after,
        "warnings": warnings,
    }
