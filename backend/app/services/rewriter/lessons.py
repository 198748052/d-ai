from __future__ import annotations

import difflib
import re
from collections import Counter
from datetime import datetime, timezone

from sqlalchemy import delete, or_
from sqlmodel import Session, select

from ...db.database import engine
from ...models.models import RewriteLesson
from .context_guard import load_whitelist
from .diagnosis import (
    ABSTRACT_NOUNS,
    BUSINESS_JARGON,
    CONNECTOR_CLICHES,
    FOUR_CHAR,
    HOLLOW_TERMS,
    HUA_SUFFIX,
    diagnose,
)

CATEGORY_LABELS = {
    "low_perplexity": "低困惑度",
    "template": "模板句式",
    "high_freq": "高频套话",
    "hollow": "空洞升华",
    "register": "语体错位",
    "leakage": "过程痕迹",
    "structure": "结构问题",
}

DEFAULT_STRATEGIES = {
    "low_perplexity": "换语序、补限定条件或具体细节",
    "template": "删掉模板连接词，直接进入对象或结论",
    "high_freq": "换成具体动作、数据或案例",
    "hollow": "删掉拔高，写具体影响",
    "register": "改回学术语体",
    "leakage": "删除过程痕迹",
    "structure": "调整句子边界和长短节奏",
}

LEXICAL_KIND = "lexical"
MIN_TERM_HITS = 2

LEXICAL_CATEGORY_LABELS = {
    "word": "词语",
    "collocation": "搭配",
    "connector": "连词",
}

LEXICAL_STRATEGIES = {
    "word": "换成具体动作、事实或非套话说法",
    "collocation": "拆开固定搭配，改用具体动作或数据表达",
    "connector": "删掉连接词，让上下句自然衔接",
}

CONNECTOR_TERMS = set(CONNECTOR_CLICHES) | {
    "然而", "因此", "此外", "同时", "从而", "进而", "并且", "而且", "但是", "不过",
    "所以", "因为", "随着", "通过", "基于", "针对", "关于", "与此同时", "一方面",
    "另一方面", "首先", "其次", "再次", "最后", "总之", "综上", "由此可见",
    "值得注意的是", "需要指出的是", "值得一提的是", "换句话说", "换言之", "简而言之",
    "总的来说", "在此背景下", "基于此", "不难看出", "不难发现",
}

AI_ADVERBS = {
    "显著", "大幅", "极大", "充分", "有效", "全面", "深入", "持续", "不断",
    "进一步", "逐步", "快速", "稳步", "有序", "精准", "高效", "深刻", "广泛",
    "积极",
}
AI_ADJECTIVES = {
    "显著", "极大", "充分", "有效", "全面", "深入", "持续", "深刻", "广泛",
    "积极", "重要", "关键", "核心", "巨大", "明显", "突出", "严峻", "复杂",
    "多元", "丰富", "优质", "强大", "深厚", "坚实", "牢固", "科学", "合理",
    "系统", "整体", "协同",
}
AI_VERBS = {
    "发挥", "具有", "提升", "推动", "促进", "实现", "构建", "完善", "加强",
    "优化", "保障", "支撑", "引领", "驱动", "融合", "创新", "赋能", "助力",
    "形成", "打造", "夯实", "筑牢", "激发", "释放", "增强", "拓展", "深化",
    "推进", "落实", "贯彻", "聚焦", "围绕", "服务",
}

AI_WORD_TERMS = set(BUSINESS_JARGON) | set(HOLLOW_TERMS) | set(HUA_SUFFIX) | set(ABSTRACT_NOUNS) | {
    "至关重要", "不可或缺", "毋庸置疑", "显而易见", "不容忽视", "普遍认为",
    "值得注意",
} | AI_ADVERBS

COLLOCATION_TERMS = set(FOUR_CHAR) | {
    "具有重要意义", "具有深远影响", "发挥重要作用", "发挥关键作用", "奠定坚实基础",
    "提供有力支撑", "注入新动能", "开辟新路径", "深度融合", "全面提升", "持续优化",
    "不断完善", "进一步加强", "有效衔接", "有机结合", "稳步推进", "扎实推进",
    "统筹兼顾", "协调推进", "精准发力", "系统谋划", "保驾护航", "添砖加瓦",
    "提质增效", "转型升级", "高质量发展", "新质生产力", "顶层设计", "底层逻辑",
    "闭环管理", "生态体系", "体制机制", "能力建设", "价值引领", "问题导向",
    "目标导向", "显著提升", "显著改善", "极大提升", "有效提升", "有效促进",
    "有力推动", "深刻影响", "深远影响", "重要意义", "重要作用", "核心要素",
    "关键环节", "重要保障", "重要支撑",
}

_KNOWN_TERMS = CONNECTOR_TERMS | AI_WORD_TERMS | COLLOCATION_TERMS
_CONTENT_FLAGS = ("n", "v", "a", "d")
_TERM_RE = re.compile(r"[\u4e00-\u9fff]{2,12}")

_NUMBER_RE = re.compile(r"\d+(?:\.\d+)?%?")
_DATE_RE = re.compile(
    r"\d{4}(?:[-/]\d{1,2}(?:[-/]\d{1,2})?|年(?:\d{1,2}月(?:\d{1,2}日)?)?)"
)
_QUOTE_RE = re.compile(r"“[^”]{1,40}”|「[^」]{1,40}」|『[^』]{1,40}』")
_LATIN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_\-]{2,}")
_WS_RE = re.compile(r"\s+")
_SIMILARITY_THRESHOLD = 0.85
_CONSECUTIVE_PLACEHOLDER_RE = re.compile(r"(?:\{[^}]+\}){2,}")

_KEEP_WORDS = {
    "首先", "其次", "再次", "最后", "此外", "与此同时", "综上所述", "总而言之",
    "总的来说", "由此可见", "值得注意的是", "值得一提的是", "需要指出的是",
    "需要强调的是", "基于此", "在此背景下", "换言之", "换句话说", "也就是说",
    "简而言之", "一方面", "另一方面", "因此", "然而", "从而", "进而", "同时",
    "而且", "并且", "但是", "不过", "所以", "因为", "随着", "通过", "在", "对",
    "为", "使", "由", "从", "向", "与", "和", "及", "以及", "或", "而", "是",
    "有", "具有", "成为", "作为", "存在", "属于", "可以", "能够", "应该", "必须",
    "将", "会", "已经", "正在", "方面", "作用", "意义", "背景", "发展", "过程",
    "问题", "挑战", "机遇", "影响", "关系", "机制", "路径", "模式", "体系", "能力",
    "水平", "程度", "范围", "条件", "结果", "原因", "目标", "方法", "内容", "观点",
    "结论", "建议", "措施", "政策", "技术", "数据", "案例", "理论", "实践", "研究",
    "分析", "探讨", "构建", "实现", "提升", "优化", "促进", "推动", "保障", "支撑",
    "发挥", "提供", "形成", "产生", "导致", "带来", "面临", "需要", "表明", "显示",
    "指出", "认为", "提出", "发现", "证明", "说明", "强调", "关注", "讨论", "比较",
    "验证", "评估", "解决", "支持", "研究显示", "数据显示", "专家指出", "学者认为",
    "普遍认为", "值得注意", "不容忽视", "显而易见", "毋庸置疑",
}


def _normalize_pattern(text: str) -> str:
    value = _QUOTE_RE.sub("{引文}", text or "")
    value = _DATE_RE.sub("{日期}", value)
    value = _NUMBER_RE.sub("{数字}", value)
    value = _LATIN_RE.sub("{术语}", value)
    value = _WS_RE.sub("", value)
    return value[:200]


def extract_template(text: str) -> str:
    """Abstract a normalized sentence into a reusable sentence template.

    Content words become placeholders while connectors, prepositions and
    structural academic phrases stay visible, e.g.
    ``首先，值得注意的是，{内容}在{内容}方面{动词}了{数量}。``
    """
    pattern = text if "{" in text else _normalize_pattern(text)
    if not pattern:
        return ""
    placeholders = re.findall(r"\{[^}]+\}", pattern)
    protected = pattern
    for index, placeholder in enumerate(placeholders):
        protected = protected.replace(placeholder, f"ZZPH{index}ZZ", 1)
    try:
        import jieba.posseg as pseg

        tokens = list(pseg.cut(protected))
    except Exception:  # noqa: BLE001
        return pattern[:120]

    parts: list[str] = []
    for word, flag in tokens:
        if not word.strip():
            continue
        sentinel = re.fullmatch(r"ZZPH(\d+)ZZ", word)
        if sentinel:
            mapped = placeholders[int(sentinel.group(1))]
            if mapped == "{数字}":
                mapped = "{数量}"
            elif mapped == "{日期}":
                mapped = "{时间}"
        elif word in _KEEP_WORDS:
            mapped = word
        elif flag.startswith(("x", "w", "u", "c", "d", "p", "f")):
            mapped = word
        elif flag.startswith(("m", "q")):
            mapped = "{数量}"
        elif flag.startswith("t"):
            mapped = "{时间}"
        elif flag.startswith("n"):
            mapped = "{名词}"
        elif flag.startswith("v"):
            mapped = "{动词}"
        elif flag.startswith("a"):
            mapped = "{形容词}"
        elif flag.startswith("r"):
            mapped = "{指代}"
        elif flag == "eng":
            mapped = "{术语}"
        else:
            mapped = "{内容}"
        if parts and mapped == parts[-1]:
            continue
        parts.append(mapped)

    template = "".join(parts)
    template = re.sub(r"\[\{数量\}\]", "", template)
    template = re.sub(r"[（(]\{数量\}[）)]", "", template)
    template = _CONSECUTIVE_PLACEHOLDER_RE.sub("{内容}", template)
    template = re.sub(r"[，,]{2,}", "，", template)
    template = re.sub(r"^[，,、；;：:]+|[，,、；;：:]+$", "", template).strip()
    if not template:
        return pattern[:120]
    if "{" not in template:
        template = pattern
    return template[:120]


def _similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    return difflib.SequenceMatcher(None, left, right).ratio()


def _term_category(term: str) -> tuple[str, str] | None:
    if term in CONNECTOR_TERMS:
        return "connector", "connector"
    if term in COLLOCATION_TERMS:
        return "collocation", "phrase"
    if term in AI_WORD_TERMS:
        return "word", "word"
    return None


def _add_term(
    bucket: dict[str, tuple[str, str]],
    term: str,
    category: str,
    scope: str,
) -> None:
    term = (term or "").strip()
    if not _TERM_RE.fullmatch(term):
        return
    bucket.setdefault(term, (category, scope))


def _is_ai_pair(left: str, left_flag: str, right: str, right_flag: str) -> bool:
    if left_flag.startswith("d") and right_flag.startswith("v"):
        return left in AI_ADVERBS or left in AI_WORD_TERMS
    if left_flag.startswith("a") and right_flag.startswith("n"):
        return left in AI_ADJECTIVES or right in AI_WORD_TERMS
    if left_flag.startswith("v") and right_flag.startswith("n"):
        return right in AI_WORD_TERMS
    return False


def extract_lexical_terms(text: str) -> dict[str, tuple[str, str]]:
    """Extract AI-heavy words, collocations and connectors from a sentence.

    The returned mapping is ``term -> (category, scope)`` where category is
    ``word``, ``collocation`` or ``connector``.
    """
    value = (text or "").strip()
    if len(value) < 6:
        return {}

    bucket: dict[str, tuple[str, str]] = {}
    whitelist_literals = set(load_whitelist().literals)

    for phrase in sorted(_KNOWN_TERMS, key=len, reverse=True):
        if phrase in whitelist_literals or phrase not in value:
            continue
        meta = _term_category(phrase)
        if meta:
            _add_term(bucket, phrase, meta[0], meta[1])

    try:
        import jieba.posseg as pseg

        tokens = [(word, flag) for word, flag in pseg.cut(value) if word.strip()]
    except Exception:  # noqa: BLE001
        tokens = []

    for word, _flag in tokens:
        meta = _term_category(word)
        if meta and word not in whitelist_literals:
            _add_term(bucket, word, meta[0], meta[1])

    previous: tuple[str, str] | None = None
    for word, flag in tokens:
        if word in {"的", "地", "得", "了", "着", "过"}:
            continue
        if not _TERM_RE.fullmatch(word) or not flag.startswith(_CONTENT_FLAGS):
            previous = None
            continue
        if previous is not None:
            left, left_flag = previous
            pair = left + word
            if pair not in whitelist_literals and (
                pair in COLLOCATION_TERMS
                or _is_ai_pair(left, left_flag, word, flag)
            ):
                _add_term(bucket, pair, "collocation", "phrase")
        previous = (word, flag)

    kept: dict[str, tuple[str, str]] = {}
    for term in sorted(bucket, key=len, reverse=True):
        if any(term != other and term in other for other in kept):
            continue
        kept[term] = bucket[term]
        if len(kept) >= 12:
            break
    return kept


def _classify(text: str, style: str) -> str:
    try:
        result = diagnose(text, style)
        category = str(result.get("dominant") or "")
        if category in CATEGORY_LABELS:
            return category
    except Exception:  # noqa: BLE001
        pass
    return "low_perplexity"


def _find_existing(
    session: Session,
    style: str,
    pattern: str,
    template: str,
    sentence: str,
) -> RewriteLesson | None:
    row = session.exec(
        select(RewriteLesson).where(
            RewriteLesson.style == style,
            RewriteLesson.sentence == sentence,
        )
    ).first()
    if row is not None:
        return row
    if pattern:
        row = session.exec(
            select(RewriteLesson)
            .where(
                RewriteLesson.style == style,
                RewriteLesson.pattern == pattern,
            )
            .order_by(RewriteLesson.hits.desc())
        ).first()
        if row is not None:
            return row
    if template:
        row = session.exec(
            select(RewriteLesson)
            .where(
                RewriteLesson.style == style,
                RewriteLesson.template == template,
            )
            .order_by(RewriteLesson.hits.desc())
        ).first()
        if row is not None:
            return row
    candidates = session.exec(
        select(RewriteLesson)
        .where(RewriteLesson.style == style)
        .order_by(RewriteLesson.last_seen_at.desc(), RewriteLesson.hits.desc())
        .limit(300)
    ).all()
    best: RewriteLesson | None = None
    best_score = 0.0
    left = template or pattern or sentence
    for candidate in candidates:
        right = candidate.template or candidate.pattern or candidate.sentence
        score = _similarity(left, right)
        if score >= _SIMILARITY_THRESHOLD and score > best_score:
            best = candidate
            best_score = score
    return best


def record_lesson(
    style: str,
    sentence: str,
    original: str = "",
    perplexity: float = 0.0,
    threshold: float = 0.0,
    note: str = "",
    outcome: str = "pending",
    scope: str = "sentence",
    source_job_id: int | None = None,
    increment_hits: bool = False,
    category: str = "",
    strategy: str = "",
) -> None:
    """Persist AI-heavy words, collocations and connectors from a low-PPL sentence.

    A term becomes active only after it appears in at least ``MIN_TERM_HITS``
    distinct sentences, so one-off expressions do not enter the prompt.
    """
    text = (sentence or "").strip()
    if not text or len(text) < 6:
        return
    terms = extract_lexical_terms(text)
    if not terms:
        return
    now = datetime.now(timezone.utc)
    try:
        with Session(engine) as session:
            existing = session.exec(
                select(RewriteLesson).where(
                    RewriteLesson.style == style,
                    RewriteLesson.kind == LEXICAL_KIND,
                    RewriteLesson.pattern.in_(list(terms)),
                )
            ).all()
            rows_by_term = {row.pattern: row for row in existing}
            for term, (term_category, term_scope) in terms.items():
                row = rows_by_term.get(term)
                if row is not None:
                    if row.sentence != text:
                        row.hits += 1
                    if perplexity > 0:
                        row.perplexity = round(
                            min(row.perplexity or perplexity, perplexity), 2
                        )
                    if threshold > 0:
                        row.threshold = round(threshold, 2)
                    if outcome == "survived":
                        row.outcome = "survived"
                    elif row.outcome != "survived":
                        row.outcome = outcome
                    if row.status == "candidate" and row.hits >= MIN_TERM_HITS:
                        row.status = "active"
                    row.last_seen_at = now
                    row.updated_at = now
                    row.sentence = text
                    if source_job_id is not None:
                        row.source_job_id = source_job_id
                    row.category = row.category or term_category
                    row.scope = row.scope or term_scope
                    row.strategy = row.strategy or LEXICAL_STRATEGIES[term_category]
                    row.note = note or row.note
                    session.add(row)
                else:
                    session.add(
                        RewriteLesson(
                            style=style,
                            kind=LEXICAL_KIND,
                            sentence=text,
                            pattern=term,
                            template="",
                            category=term_category,
                            outcome=outcome,
                            status="active" if MIN_TERM_HITS <= 1 else "candidate",
                            scope=term_scope,
                            strategy=LEXICAL_STRATEGIES[term_category],
                            original=(original or "").strip()[:200],
                            perplexity=round(perplexity, 2),
                            threshold=round(threshold, 2),
                            hits=1,
                            source_job_id=source_job_id,
                            last_seen_at=now,
                            note=note,
                        )
                    )
            session.commit()
    except Exception:  # noqa: BLE001
        pass


def backfill_templates() -> int:
    """Generate templates for legacy rows that only have pattern/sentence."""
    with Session(engine) as session:
        rows = session.exec(select(RewriteLesson)).all()
        updated = 0
        for row in rows:
            source = row.pattern or row.sentence
            if not source:
                continue
            if row.template and row.template not in {row.pattern, row.sentence}:
                continue
            template = extract_template(source)
            if template and template != row.template:
                row.template = template
                row.updated_at = datetime.now(timezone.utc)
                session.add(row)
                updated += 1
        if updated:
            session.commit()
        return updated


def _format_hint(row: RewriteLesson) -> str:
    label = LEXICAL_CATEGORY_LABELS.get(row.category, "词语")
    term = (row.pattern or "").strip()
    strategy = (row.strategy or LEXICAL_STRATEGIES.get(row.category, "")).strip()
    return f"[{label}] {term}" + (f" → {strategy}" if strategy else "")


def _is_useful(row: RewriteLesson) -> bool:
    text = row.pattern or row.template or row.sentence
    return len(re.findall(r"[\u4e00-\u9fff]", text or "")) >= 2


def recent_lesson_rows(style: str, limit: int = 10) -> list[RewriteLesson]:
    try:
        with Session(engine) as session:
            rows = session.exec(
                select(RewriteLesson)
                .where(
                    RewriteLesson.style == style,
                    RewriteLesson.kind == LEXICAL_KIND,
                    RewriteLesson.status == "active",
                )
                .order_by(RewriteLesson.hits.desc(), RewriteLesson.last_seen_at.desc())
                .limit(limit)
            ).all()
    except Exception:  # noqa: BLE001
        return []
    return [row for row in rows if row.pattern and _is_useful(row)]


def recent_lessons(style: str, limit: int = 10) -> list[str]:
    """Return formatted forbidden words, collocations and connectors."""
    return [_format_hint(row) for row in recent_lesson_rows(style, limit)]


def recent_forbidden_terms(style: str, limit: int = 10) -> list[str]:
    """Return raw terms that must not appear in the rewritten text."""
    return [
        row.pattern.strip()
        for row in recent_lesson_rows(style, limit)
        if row.pattern and row.pattern.strip()
    ]


def match_forbidden_terms(text: str, terms: list[str]) -> list[str]:
    """Return forbidden terms that still appear in the generated text."""
    hits: list[str] = []
    seen: set[str] = set()
    for term in terms:
        value = (term or "").strip()
        if len(value) < 2 or value in seen:
            continue
        if value in (text or ""):
            hits.append(value)
            seen.add(value)
    return hits


def list_lessons(
    style: str | None = None,
    status: str | None = None,
    category: str | None = None,
    outcome: str | None = None,
    keyword: str | None = None,
    limit: int = 100,
    offset: int = 0,
) -> list[RewriteLesson]:
    with Session(engine) as session:
        query = select(RewriteLesson)
        if style:
            query = query.where(RewriteLesson.style == style)
        if status:
            query = query.where(RewriteLesson.status == status)
        if category:
            query = query.where(RewriteLesson.category == category)
        if outcome:
            query = query.where(RewriteLesson.outcome == outcome)
        if keyword:
            value = f"%{keyword.strip()}%"
            query = query.where(
                or_(
                    RewriteLesson.sentence.like(value),
                    RewriteLesson.pattern.like(value),
                    RewriteLesson.note.like(value),
                )
            )
        query = query.order_by(
            RewriteLesson.hits.desc(),
            RewriteLesson.last_seen_at.desc(),
            RewriteLesson.updated_at.desc(),
        )
        return list(session.exec(query.offset(offset).limit(limit)).all())


def lesson_stats(style: str | None = None) -> dict:
    with Session(engine) as session:
        query = select(RewriteLesson)
        if style:
            query = query.where(RewriteLesson.style == style)
        rows = session.exec(query).all()
    lexical = [row for row in rows if row.kind == LEXICAL_KIND]
    return {
        "total": len(rows),
        "lexical_total": len(lexical),
        "legacy": len(rows) - len(lexical),
        "active": sum(1 for row in lexical if row.status == "active"),
        "candidate": sum(1 for row in lexical if row.status == "candidate"),
        "ignored": sum(1 for row in lexical if row.status == "ignored"),
        "resolved": sum(1 for row in lexical if row.status == "resolved"),
        "survived": sum(1 for row in lexical if row.outcome == "survived"),
        "fixed": sum(1 for row in lexical if row.outcome == "fixed"),
        "pending": sum(1 for row in lexical if row.outcome == "pending"),
        "words": sum(1 for row in lexical if row.category == "word"),
        "collocations": sum(1 for row in lexical if row.category == "collocation"),
        "connectors": sum(1 for row in lexical if row.category == "connector"),
        "categories": dict(Counter(row.category for row in lexical)),
    }


def clear_lessons(style: str | None = None) -> int:
    """Delete every lesson row, optionally limited to one style."""
    with Session(engine) as session:
        statement = delete(RewriteLesson)
        if style:
            statement = statement.where(RewriteLesson.style == style)
        result = session.execute(statement)
        session.commit()
        return result.rowcount or 0


def update_lesson(
    lesson_id: int,
    status: str | None = None,
    category: str | None = None,
    strategy: str | None = None,
    note: str | None = None,
) -> RewriteLesson | None:
    with Session(engine) as session:
        row = session.get(RewriteLesson, lesson_id)
        if row is None:
            return None
        if status is not None:
            row.status = status
        if category is not None:
            row.category = category
        if strategy is not None:
            row.strategy = strategy
        if note is not None:
            row.note = note
        row.updated_at = datetime.now(timezone.utc)
        session.add(row)
        session.commit()
        session.refresh(row)
        return row
